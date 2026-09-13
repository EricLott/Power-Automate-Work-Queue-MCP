"""Opt-in native Work Queue pause proof; dry-run performs no tenant calls."""
import argparse, json, subprocess, uuid
from pathlib import Path
from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding

FLOW_IDS=("a9c6e175-d6f6-50a7-860c-8fdb91da396e","5391db37-d88c-57c5-839a-d66c26ffd46a","d6228ad8-9758-567d-a1a3-2d5c97ab4c73","6a491be2-4f32-549d-8afb-92d556e5c89b","014c3583-22a5-5146-bf25-94768d689092","656a2463-6fd0-5892-b382-3fc8babdc8ed","a0fed279-6860-5897-912d-ccfabee2de0d")

def validate(binding, fixture):
    origin, organization=_validate_binding(binding); queue=fixture.get("queueKey"); item=fixture.get("itemId"); native_queue=fixture.get("queue")
    if not isinstance(queue,str) or not queue.startswith("qmcp-proof-") or queue not in binding.get("queueKeys",[]): raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    for value,code in ((item,"SEEDED_ITEM_REQUIRED"),(native_queue,"NATIVE_QUEUE_ID_REQUIRED")):
        try: uuid.UUID(value)
        except (ValueError,TypeError): raise ValueError(code)
    return origin,organization,queue,native_queue,item

def is_paused_error(error, native_queue):
    if error.get("code") != "0x80048d0b": return False
    try: detail = json.loads(error.get("message", ""))
    except (ValueError, TypeError): return False
    return isinstance(detail, dict) and detail.get("errorCode") == "RecordNotActive" and detail.get("message") == "Work queue " + native_queue + " is not active. It is in Paused status."


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--binding",required=True); p.add_argument("--fixture-ledger",required=True); p.add_argument("--output",required=True); p.add_argument("--execute",action="store_true"); a=p.parse_args(argv)
    binding=json.loads(Path(a.binding).read_text(encoding="utf-8-sig")); fixture=json.loads(Path(a.fixture_ledger).read_text(encoding="utf-8-sig")); origin,org,queue,native_queue,item=validate(binding,fixture); out=Path(a.output)
    if not a.execute: print(json.dumps({"ready":True,"writes":False,"tenantCalls":False,"queueKey":queue,"itemId":item},indent=2)); return
    if out.exists(): raise ValueError("EVIDENCE_EXISTS")
    evidence={"classification":"synthetic-native-queue-pause","organizationId":org,"queueKey":queue,"nativeQueueId":native_queue,"itemId":item,"completed":False,"tenantCalls":True}; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    cmd=_cli_command()
    def runner(args, **kwargs):
        if "--method" in args and args[args.index("--method") + 1] == "PATCH":
            observed = evidence.get("currentQueue") or evidence.get("queueBefore") or {}
            etag = observed.get("@odata.etag")
            if not etag: raise ValueError("NATIVE_QUEUE_ETAG_REQUIRED")
            args = list(args) + ["--header", "If-Match: " + etag]
        result = subprocess.run(args, **kwargs)
        if result.returncode:
            try: error = json.loads(result.stdout or "{}").get("error", {})
            except (ValueError, AttributeError): error = {}
            save(lastError={k: str(error[k])[:2000] for k in ("code", "message") if k in error})
        return result
    def call(method,path,body=None): return _cli_request(cmd,origin,method,path,body,runner=runner)
    def save(**values): evidence.update(values); out.write_text(json.dumps(evidence,indent=2,sort_keys=True),encoding="utf-8")
    changed=False
    try:
        who=call("GET","WhoAmI")
        if str(who.get("OrganizationId","")).lower()!=org.lower(): raise ValueError("ENVIRONMENT_MISMATCH")
        for flow in FLOW_IDS:
            if call("GET","workflows("+flow+")?$select=statecode").get("statecode")!=0: raise ValueError("FLOWS_MUST_BE_DRAFT")
        queue_row=call("GET","workqueues("+native_queue+")?$select=statecode,statuscode")
        if queue_row.get("statecode")!=0 or queue_row.get("statuscode")!=1: raise ValueError("NATIVE_QUEUE_NOT_ACTIVE")
        if not queue_row.get("@odata.etag"): raise ValueError("NATIVE_QUEUE_ETAG_REQUIRED")
        policy_rows=call("GET","qmcp_wqdefinitions?$select=qmcp_document,versionnumber&$filter=qmcp_key eq '"+queue+"'&$top=2").get("value")
        if not isinstance(policy_rows,list) or len(policy_rows)!=1: raise ValueError("FRAMEWORK_POLICY_NOT_UNIQUE")
        policy=json.loads(policy_rows[0]["qmcp_document"])
        if not policy.get("Enabled") or str(policy.get("NativeQueueId","")).lower()!=native_queue.lower(): raise ValueError("FRAMEWORK_QUEUE_BINDING_INVALID")
        items=call("GET","workqueueitems?$select=workqueueitemid,uniqueidbyqueue,statecode,statuscode&$filter=_workqueueid_value eq "+native_queue+" and statecode eq 0&$top=2").get("value")
        if not isinstance(items,list) or len(items)!=1 or items[0].get("workqueueitemid","").lower()!=item.lower(): raise ValueError("SEEDED_ITEM_NOT_SOLE_ELIGIBLE")
        item_before=call("GET","workqueueitems("+item+")?$select=workqueueitemid,uniqueidbyqueue,statecode,statuscode")
        if not item_before.get("@odata.etag"): raise ValueError("NATIVE_ITEM_ETAG_REQUIRED")
        save(queueBefore=queue_row,itemBefore=item_before)
        prep_id=str(uuid.uuid4()); save(prepareRequestId=prep_id)
        prepared=json.loads(call("POST","qmcp_WQ_PrepareAcquire",{"QueueKey":queue,"RequestId":prep_id,"DataJson":"{}"})["ResultJson"])
        if prepared.get("Outcome")!="Prepared" or str(prepared.get("NativeQueueId","")).lower()!=native_queue.lower(): raise ValueError("ACQUIRE_NOT_PREPARED")
        pause_id=str(uuid.uuid4()); changed=True; save(pauseOperationId=pause_id)
        call("PATCH","workqueues("+native_queue+")",{"statecode":1,"statuscode":3})
        paused=call("GET","workqueues("+native_queue+")?$select=statecode,statuscode")
        if paused.get("statecode")!=1 or paused.get("statuscode")!=3: raise ValueError("NATIVE_PAUSE_NOT_OBSERVED")
        save(pausedQueue=paused)
        try: dequeue=call("POST","workqueues("+native_queue+")/Microsoft.Dynamics.CRM.Dequeue",{}); dequeue_error=None
        except ValueError:
            if not is_paused_error(evidence.get("lastError", {}), native_queue): raise ValueError("NATIVE_PAUSE_DEQUEUE_UNVERIFIED")
            dequeue={}; save(dequeueRejection="RecordNotActive:Paused")
        resolved=json.loads(call("POST","qmcp_WQ_ResolveAcquire",{"QueueKey":queue,"RequestId":prep_id,"DataJson":"{}"})["ResultJson"])
        attempts=call("GET","qmcp_wqattempts?$select=qmcp_wqattemptid&$filter=qmcp_itemid eq '"+item+"'&$top=2").get("value")
        if not isinstance(attempts,list): raise ValueError("ATTEMPT_QUERY_INVALID")
        item_after=call("GET","workqueueitems("+item+")?$select=workqueueitemid,uniqueidbyqueue,statecode,statuscode")
        if dequeue.get("workqueueitemid") or resolved.get("Outcome")=="Acquired" or attempts or item_after != item_before: raise ValueError("PAUSE_ACQUISITION_ASSERTION_FAILED")
        save(pausedQueue=paused,dequeueResult=dequeue,resolveOutcome=resolved,nativeItemAfter=item_after,attemptCount=len(attempts),seededItemUnchanged=True)
    finally:
        if changed:
            current=call("GET","workqueues("+native_queue+")?$select=statecode,statuscode")
            if current.get("statecode")!=1 or current.get("statuscode")!=3: save(completed=False,restoreRefused="NATIVE_QUEUE_CHANGED_CONCURRENTLY")
            else:
                save(currentQueue=current)
                rid=str(uuid.uuid4()); save(restoreOperationId=rid); call("PATCH","workqueues("+native_queue+")",{"statecode":0,"statuscode":1}); restored=call("GET","workqueues("+native_queue+")?$select=statecode,statuscode"); save(restoredQueue=restored,policyRestored=restored.get("statecode")==0 and restored.get("statuscode")==1)
        if evidence.get("policyRestored") and evidence.get("resolveOutcome",{}).get("Outcome")=="Pending" and evidence.get("seededItemUnchanged"): save(completed=True)
    if not evidence["completed"]: raise ValueError("NATIVE_PAUSE_PROOF_INCOMPLETE")
    print(json.dumps(evidence,indent=2,sort_keys=True))

if __name__=="__main__":
    try: main()
    except (OSError,KeyError,TypeError,ValueError) as error: raise SystemExit(str(error))
