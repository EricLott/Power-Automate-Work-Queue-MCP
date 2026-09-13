"""Opt-in proof that acquisition failures roll back the complete transaction."""
import argparse, datetime, hashlib, json, re, subprocess, time, uuid
from pathlib import Path

from bootstrap_tenant import _cli_command, _cli_request
from prove_acquisition_identity import FLOW_IDS
from probe_tenant_metadata import _validate_binding

RETAINED_ITEM = "e9c029c3-95e9-4e93-a07d-5d7688b31922"
FAULTS = ("after-native-claim", "after-attempt", "after-context", "after-intent", "before-receipt", "after-receipt")
PROOF_ERROR = "INJECTED_PROOF_FAILURE"

def collection(response):
    rows = response.get("value")
    if not isinstance(rows, list) or response.get("@odata.nextLink"):
        raise ValueError("EVIDENCE_COLLECTION_INVALID")
    return rows

def trace_evidence(rows):
    evidence = []
    for row in rows:
        lines = [line[:300] for line in str(row.get("messageblock", "")).splitlines()
                 if line.startswith("qmcp operation qmcp_WQ_AcceptAcquire;") or line.startswith("qmcp acquisition claim validated;")]
        for line in lines:
            if not re.search(r"transaction True(?:;|$)", line) or not re.search(r"depth [1-9][0-9]*(?:;|$)", line):
                raise ValueError("TRACE_TRANSACTION_INVALID")
        if lines:
            evidence.append({**{key: row.get(key) for key in ("correlationid", "depth", "typename", "createdon")}, "transactionLines": lines})
    all_lines = [line for row in evidence for line in row["transactionLines"]]
    if not any(line.startswith("qmcp operation") for line in all_lines) or not any(line.startswith("qmcp acquisition claim") for line in all_lines):
        raise ValueError("TRACE_TRANSACTION_FIELDS_MISSING")
    return evidence

def validate(binding, ledger):
    if binding.get("environmentClass") != "development" or not str(binding.get("environmentUrl", "")).startswith("https://"):
        raise ValueError("DEVELOPMENT_BINDING_REQUIRED")
    queue = ledger.get("queueKey")
    if not isinstance(queue, str) or not queue.startswith("qmcp-proof-") or queue not in binding.get("queueKeys", []):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    if str(ledger.get("queuedItemId", ledger.get("itemId", ""))).lower() != RETAINED_ITEM:
        raise ValueError("RETAINED_ITEM_REQUIRED")
    for key in ("queue", "team", "principal", "user"):
        try: uuid.UUID(str(ledger[key]))
        except (KeyError, TypeError, ValueError): raise ValueError("NATIVE_BINDING_ID_REQUIRED")
    try: origin, org = _validate_binding(binding)
    except KeyError: raise ValueError("ORGANIZATION_ID_REQUIRED")
    return origin, org, queue, str(ledger["queue"])

def fault_from_stdout(stdout):
    try:
        outer = json.loads(stdout or "")
        value = outer.get("error", {}).get("message") if isinstance(outer, dict) else None
        if value in (PROOF_ERROR, "ACQUISITION_HANDOFF_FAILED"): return value
        nested = json.loads(value) if isinstance(value, str) else {}
        value = nested.get("error", nested).get("message") if isinstance(nested, dict) else value
        wrapped = "Fail to update work queue item " + RETAINED_ITEM + " to Processing because: ACQUISITION_HANDOFF_FAILED. Fault ErrorCode: -2147220891"
        if isinstance(nested, dict) and nested.get("errorCode") == "InternalServerError" and value == wrapped:
            return "ACQUISITION_HANDOFF_FAILED"
        return value if value in (PROOF_ERROR, "ACQUISITION_HANDOFF_FAILED") else None
    except (TypeError, ValueError, AttributeError): return None

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("binding", "fixture-ledger", "output-dir", "run-id"): p.add_argument("--" + name, required=True)
    p.add_argument("--execute", action="store_true"); a = p.parse_args(argv)
    binding = json.loads(Path(a.binding).read_text(encoding="utf-8-sig")); ledger = json.loads(Path(a.fixture_ledger).read_text(encoding="utf-8-sig"))
    origin, org, queue, native_queue = validate(binding, ledger)
    if not a.run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in a.run_id): raise ValueError("RUN_ID_INVALID")
    output = Path(a.output_dir)
    if output.exists(): raise ValueError("EVIDENCE_RUN_EXISTS")
    if not a.execute:
        print(json.dumps({"ready": True, "writes": False, "tenantCalls": False, "queueKey": queue, "queuedItemId": RETAINED_ITEM, "faults": FAULTS}, indent=2)); return
    output.mkdir(parents=True, exist_ok=False)
    evidence = {"classification": "synthetic-transaction-boundaries", "organizationId": org, "queueKey": queue, "queuedItemId": RETAINED_ITEM, "runId": a.run_id, "completed": False, "tenantCalls": True, "faults": {}}
    ef = output / "evidence.json"
    def save(**values): evidence.update(values); ef.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    save()
    command = _cli_command(); state = {}
    def req(method, path, body=None):
        def runner(*args, **kwargs):
            result = subprocess.run(*args, **kwargs)
            if result.returncode:
                state["fault"] = fault_from_stdout(result.stdout)
                try:
                    message = json.loads(result.stdout).get("error", {}).get("message")
                    save(lastReportedFault=str(message)[:1000])
                except (ValueError, AttributeError): save(lastReportedFault="UNPARSEABLE_CLI_FAULT")
            return result
        return _cli_request(command, origin, method, path, body, runner=runner)
    def rid(label): return str(uuid.uuid5(uuid.UUID(str(ledger["queue"])), a.run_id + "|" + label))
    def api(name, request, data=None):
        body = {"QueueKey": queue, "RequestId": request, "DataJson": json.dumps(data or {}, separators=(",", ":"))}
        return json.loads(req("POST", "qmcp_WQ_" + name, body)["ResultJson"])
    def native_row():
        return req("GET", "workqueueitems(" + RETAINED_ITEM + ")?$select=workqueueitemid,statecode,statuscode,uniqueidbyqueue")
    def attempts(): return collection(req("GET", "qmcp_wqattempts?$select=qmcp_wqattemptid,qmcp_document&$filter=qmcp_itemid eq '" + RETAINED_ITEM + "'"))
    def context():
        rows = collection(req("GET", "qmcp_wqitemcontexts?$select=qmcp_document&$filter=qmcp_itemid eq '" + RETAINED_ITEM + "'"))
        if len(rows) != 1: raise ValueError("CONTEXT_NOT_UNIQUE")
        value = json.loads(rows[0]["qmcp_document"])
        if not isinstance(value, dict) or value.get("ItemId", "").lower() != RETAINED_ITEM:
            raise ValueError("CONTEXT_INVALID")
        return value
    def receipts(request):
        key = hashlib.sha256((str(ledger["user"]) + "|AcceptAcquire|" + request).encode()).hexdigest()
        return collection(req("GET", "qmcp_wqcommands?$select=qmcp_wqcommandid&$filter=qmcp_key eq '" + key + "'"))
    def case_traces(request, started):
        fields = "correlationid,depth,typename,messageblock,createdon"
        for attempt in range(6):
            seed = collection(req("GET", "plugintracelogs?$select=" + fields + "&$filter=createdon ge " + started + " and contains(messageblock,'" + request + "')&$top=50"))
            rows = []
            for correlation in {row.get("correlationid") for row in seed if row.get("correlationid")}:
                uuid.UUID(correlation)
                rows.extend(collection(req("GET", "plugintracelogs?$select=" + fields + "&$filter=correlationid eq " + correlation + "&$top=50")))
            if any("qmcp failure INJECTED_PROOF_FAILURE;" in str(row.get("messageblock", "")) for row in rows):
                return trace_evidence(rows)
            if attempt < 5: time.sleep(5)
        raise ValueError("INJECTED_TRACE_NOT_OBSERVED")
    try:
        who = req("GET", "WhoAmI")
        if str(who.get("OrganizationId", "")).lower() != org.lower() or str(who.get("UserId", "")).lower() != str(ledger["user"]).lower(): raise ValueError("ENVIRONMENT_MISMATCH")
        for flow in FLOW_IDS:
            if req("GET", "workflows(" + flow + ")?$select=statecode").get("statecode") != 0: raise ValueError("FLOWS_MUST_BE_DRAFT")
        rows = req("GET", "workqueueitems?$select=workqueueitemid,statecode,statuscode&$filter=_workqueueid_value eq " + native_queue + " and (statecode eq 0 or statecode eq 1)&$top=10").get("value", [])
        if len(rows) != 1 or str(rows[0].get("workqueueitemid", "")).lower() != RETAINED_ITEM or rows[0].get("statecode") != 0: raise ValueError("EXACT_SOLE_ACTIVE_ITEM_REQUIRED")
        policy = req("GET", "qmcp_wqdefinitions?$select=qmcp_document&$filter=qmcp_key eq '" + queue + "'&$top=2").get("value", [])
        if len(policy) != 1: raise ValueError("POLICY_NOT_UNIQUE")
        bound_policy = json.loads(policy[0]["qmcp_document"])
        if not bound_policy.get("Enabled") or bound_policy.get("NativeQueueId", "").lower() != native_queue.lower():
            raise ValueError("POLICY_BINDING_INVALID")
        original_principal = req("GET", "qmcp_wqprincipals(" + str(ledger["principal"]) + ")?$select=qmcp_document").get("qmcp_document")
        original_setting = req("GET", "organizations(" + org + ")?$select=plugintracelogsetting").get("plugintracelogsetting")
        if original_setting not in (0, 1, 2): raise ValueError("TRACE_SETTING_INVALID")
        profile = json.loads(original_principal)
        if profile.get("production", True) or "deployment" not in profile.get("roles", []) or profile.get("proofFault"):
            raise ValueError("PROOF_PROFILE_INVALID")
        save(originalPrincipal=original_principal, originalPluginTraceLogSetting=original_setting, requests={})
        baseline = {"native": native_row(), "context": context(), "attempts": attempts(), "receipts": receipts(rid("prepare"))}
        if baseline["attempts"] or baseline["receipts"] or baseline["context"].get("ActiveAttempt") or baseline["context"].get("AttemptCount") != 0:
            raise ValueError("FIXTURE_ALREADY_ACQUIRED")
        save(baseline=baseline)
        # Trace setting is a temporary diagnostic write and is always restored.
        req("PATCH", "organizations(" + org + ")", {"plugintracelogsetting": 2})
        prepare_id = rid("prepare")
        save(requests={"PrepareAcquire": prepare_id})
        prepared = api("PrepareAcquire", prepare_id, {"flowId": "transaction-proof", "runId": a.run_id})
        if prepared.get("Outcome") != "Prepared": raise ValueError("PREPARE_FAILED")
        for fault in FAULTS:
            expires = datetime.datetime.fromisoformat(prepared["Expires"].replace("Z", "+00:00"))
            remaining = (expires - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
            if remaining < 45:
                # Never replace a live intent. Let its bounded remainder expire
                # before preparing a new identity for the next independent case.
                if remaining > 0: time.sleep(remaining + 0.1)
                prepare_id = rid("prepare-" + fault)
                save(requests={**evidence["requests"], fault: prepare_id})
                prepared = api("PrepareAcquire", prepare_id, {"flowId": "transaction-proof", "runId": a.run_id})
                if prepared.get("Outcome") != "Prepared": raise ValueError("PREPARE_FAILED")
            save(activeFault=fault)
            # Replay the same prepared request: a new prepare would be rejected
            # while the previous lease is live and would change the proof cursor.
            api("PrepareAcquire", prepare_id, {"flowId": "transaction-proof", "runId": a.run_id})
            modified = json.loads(original_principal); modified["proofFault"] = fault
            started = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                req("PATCH", "qmcp_wqprincipals(" + str(ledger["principal"]) + ")", {"qmcp_document": json.dumps(modified)})
                state.clear(); error = None
                try: req("POST", "workqueues(" + native_queue + ")/Microsoft.Dynamics.CRM.Dequeue", {})
                except ValueError: error = state.get("fault") or "DATAVERSE_CLI_FAILED"
                if error not in (PROOF_ERROR, "ACQUISITION_HANDOFF_FAILED"): raise ValueError("INJECTED_FAILURE_NOT_OBSERVED")
            finally: req("PATCH", "qmcp_wqprincipals(" + str(ledger["principal"]) + ")", {"qmcp_document": original_principal})
            after = {"native": native_row(), "context": context(), "attempts": attempts(), "receipts": receipts(prepare_id)}
            if (not after["context"] or
                    (after["native"].get("statecode"), after["native"].get("statuscode")) !=
                    (baseline["native"].get("statecode"), baseline["native"].get("statuscode")) or
                    after["context"] != baseline["context"] or after["attempts"] or after["receipts"]):
                raise ValueError("TRANSACTION_ROLLBACK_ASSERTION_FAILED")
            pending = api("ResolveAcquire", prepare_id)
            if pending.get("Outcome") not in ("Pending", "Expired"): raise ValueError("RESOLVE_NOT_PENDING")
            observed_traces = case_traces(prepare_id, started)
            evidence["faults"][fault] = {"error": error, "injectedFaultVerified": True, "traces": observed_traces, "native": after["native"], "context": after["context"], "attemptCount": len(after["attempts"]), "acceptReceipts": len(after["receipts"]), "resolve": pending}
            save()
        evidence["traces"] = [row for case in evidence["faults"].values() for row in case["traces"]]
        correlations = {entry["correlationid"] for entry in evidence["traces"]}
        if len(correlations) < len(FAULTS): raise ValueError("TRACE_CASE_COVERAGE_MISSING")
        req("PATCH", "organizations(" + org + ")", {"plugintracelogsetting": original_setting})
        save(matrixVerified=True)
    except Exception as error:
        save(error=str(error) if isinstance(error, ValueError) and str(error).isupper() else "PROOF_INCONCLUSIVE")
        raise
    finally:
        restore_errors = []
        for name, path, body in (
            ("principal", "qmcp_wqprincipals(" + str(ledger["principal"]) + ")", {"qmcp_document": locals().get("original_principal")}),
            ("tracing", "organizations(" + org + ")", {"plugintracelogsetting": locals().get("original_setting")})):
            if list(body.values())[0] is None: continue
            try:
                req("PATCH", path, body)
                observed = req("GET", path + "?$select=" + next(iter(body)))
                if any(observed.get(key) != value for key, value in body.items()): raise ValueError("RESTORE_MISMATCH")
            except Exception: restore_errors.append(name)
        save(restorationErrors=restore_errors)
        if restore_errors: raise ValueError("PROOF_RESTORATION_FAILED")
    save(completed=True)
    print(json.dumps(evidence, indent=2, sort_keys=True))

if __name__ == "__main__":
    try: main()
    except (OSError, KeyError, TypeError, ValueError) as e: raise SystemExit(str(e))
