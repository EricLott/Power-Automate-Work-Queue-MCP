"""Opt-in isolated native connector experiment; never invokes business logic."""
import argparse
import datetime
import hashlib
import json
import subprocess
import time
import uuid
from pathlib import Path

from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding
from prove_acquisition_identity import FLOW_IDS

QUEUE = "d14ec06b-3109-57e6-b18e-43763044a876"
ITEM = "15acd185-a46c-59ba-a0da-61047e214964"
CASES = ("available", "empty", "paused")


def paused_result(value):
    if value.get("actionStatus") != "Failed": return False
    body = value.get("body")
    if not isinstance(body, dict): return False
    error = body.get("error", body)
    if not isinstance(error, dict): return False
    message = error.get("message")
    try: detail = json.loads(message) if isinstance(message, str) else error
    except ValueError: return False
    return (isinstance(detail, dict) and detail.get("errorCode") == "RecordNotActive" and
            detail.get("message") == "Work queue " + QUEUE + " is not active. It is in Paused status.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("binding", "output-dir", "run-id"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    origin, organization = _validate_binding(binding)
    if not args.run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in args.run_id):
        raise ValueError("RUN_ID_INVALID")
    output = Path(args.output_dir)
    if output.exists(): raise ValueError("EVIDENCE_RUN_EXISTS")
    flow_id = str(uuid.uuid5(uuid.UUID(QUEUE), args.run_id + "|flow"))
    notes = {case: str(uuid.uuid5(uuid.UUID(QUEUE), args.run_id + "|" + case)) for case in CASES}
    if not args.execute:
        print(json.dumps({"ready": True, "writes": False, "flowId": flow_id, "noteIds": notes}))
        return
    from generate_native_connector_probe import generate
    data = generate(QUEUE, args.run_id, notes)
    output.mkdir(parents=True)
    evidence = {"classification": "isolated-native-connector", "completed": False, "organizationId": organization,
                "queueId": QUEUE, "itemId": ITEM, "flowId": flow_id, "noteIds": notes, "runId": args.run_id}
    def save(**values):
        evidence.update(values)
        (output / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    save()
    command = _cli_command()
    def call(method, path, body=None):
        return _cli_request(command, origin, method, path, body, runner=subprocess.run)
    def rows(path):
        result = call("GET", path)
        if not isinstance(result.get("value"), list) or result.get("@odata.nextLink"):
            raise ValueError("EVIDENCE_COLLECTION_INVALID")
        return result["value"]
    def queue(): return call("GET", "workqueues(" + QUEUE + ")?$select=name,statecode,statuscode")
    def item(): return call("GET", "workqueueitems(" + ITEM + ")?$select=name,input,statecode,statuscode,expirydate")
    flow_path = "workflows(" + flow_id + ")"
    flow_written = False
    try:
        who = call("GET", "WhoAmI")
        if str(who.get("OrganizationId", "")).lower() != organization.lower(): raise ValueError("ENVIRONMENT_MISMATCH")
        for flow in FLOW_IDS:
            if call("GET", "workflows(" + flow + ")?$select=statecode").get("statecode") != 0:
                raise ValueError("RUNTIME_FLOWS_MUST_BE_DRAFT")
        original_queue, original_item = queue(), item()
        if original_queue.get("name") != "qmcp empty native dequeue probe" or (original_queue.get("statecode"), original_queue.get("statuscode")) != (0, 1):
            raise ValueError("PROBE_QUEUE_INVALID")
        if original_item.get("name") != "qmcp synthetic native probe" or original_item.get("input") != "{}" or (original_item.get("statecode"), original_item.get("statuscode")) != (0, 0) or original_item.get("expirydate") is not None:
            raise ValueError("PROBE_ITEM_INVALID")
        if rows("qmcp_wqqueuebindings?$select=qmcp_key&$filter=qmcp_key eq '" + QUEUE + "'"):
            raise ValueError("PROBE_MUST_BE_UNREGISTERED")
        native_rows = rows("workqueueitems?$select=workqueueitemid&$filter=_workqueueid_value eq " + QUEUE)
        if len(native_rows) != 1 or native_rows[0]["workqueueitemid"] != ITEM:
            raise ValueError("EXACT_PROBE_ITEM_REQUIRED")
        if rows("workflows?$select=workflowid&$filter=workflowid eq " + flow_id): raise ValueError("FLOW_ALREADY_EXISTS")
        for note_id in notes.values():
            if rows("annotations?$select=annotationid&$filter=annotationid eq " + note_id): raise ValueError("NOTE_ALREADY_EXISTS")
        save(originalQueue=original_queue, originalItem=original_item, actorId=who["UserId"], clientdataSha256=hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest())
        (output / "clientdata.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        # Persist planned IDs before creation. A failed create may have committed.
        flow_written = True
        call("POST", "workflows", {"workflowid": flow_id, "name": "qmcp Native Connector Proof " + args.run_id,
             "category": 5, "type": 1, "scope": 4, "primaryentity": "none", "clientdata": json.dumps(data)})
        call("PATCH", flow_path, {"statecode": 1, "statuscode": 2})
        if call("GET", flow_path + "?$select=statecode").get("statecode") != 1: raise ValueError("FLOW_NOT_ACTIVE")
        deadline = time.monotonic() + 240
        collected = {}
        while time.monotonic() < deadline:
            for case, note_id in notes.items():
                if case in collected: continue
                observed = rows("annotations?$select=annotationid,notetext,_createdby_value&$filter=annotationid eq " + note_id)
                if len(observed) > 1: raise ValueError("NOTE_NOT_UNIQUE")
                if observed:
                    collected[case] = observed[0]
                    save(observations=collected)
            if len(collected) == 3 and queue().get("statecode") == 0: break
            time.sleep(10)
        if len(collected) != 3: raise ValueError("CONNECTOR_EVIDENCE_TIMEOUT")
        decoded = {case: json.loads(row["notetext"]) for case, row in collected.items()}
        save(decoded=decoded, nativeAfter=item(), queueAfter=queue())
        # Result interpretation is reviewed against the saved action evidence.
        if any(value.get("runId") != args.run_id or value.get("case") != case or not value.get("flowRunId") for case, value in decoded.items()): raise ValueError("NOTE_RUN_MISMATCH")
        if len({value["flowRunId"] for value in decoded.values()}) != 1: raise ValueError("MULTIPLE_FLOW_RUNS")
        if any(row.get("_createdby_value") != who["UserId"] for row in collected.values()): raise ValueError("NOTE_ACTOR_MISMATCH")
        if decoded["available"].get("actionStatus") != "Succeeded" or decoded["available"].get("body", {}).get("workqueueitemid") != ITEM:
            raise ValueError("AVAILABLE_RESULT_INVALID")
        if decoded["empty"].get("actionStatus") != "Succeeded" or decoded["empty"].get("body") not in (None, {}, ""):
            raise ValueError("EMPTY_RESULT_INVALID")
        if not paused_result(decoded["paused"]):
            raise ValueError("PAUSED_RESULT_INVALID")
        if evidence["nativeAfter"].get("statecode") != 1 or evidence["queueAfter"].get("statecode") != 0:
            raise ValueError("FINAL_NATIVE_STATE_INVALID")
        save(matrixVerified=True)
    except Exception as error:
        save(error=str(error) if isinstance(error, ValueError) and str(error).isupper() else "PROOF_INCONCLUSIVE")
        raise
    finally:
        if flow_written:
            restoration_errors = []
            for name, path, body in (
                ("flow", flow_path, {"statecode": 0, "statuscode": 1}),
                ("queue", "workqueues(" + QUEUE + ")", {"statecode": 0, "statuscode": 1}),
                ("item", "workqueueitems(" + ITEM + ")", {"statecode": 0, "statuscode": 0})):
                try:
                    if name == "item" and call("GET", path + "?$select=statecode").get("statecode") == 1:
                        # Native immediate reset from Processing is rejected.
                        # End this isolated probe attempt before resetting it.
                        call("PATCH", path, {"statecode": 4, "statuscode": 4})
                    call("PATCH", path, body)
                    restored = call("GET", path + "?$select=statecode,statuscode")
                    if any(restored.get(key) != value for key, value in body.items()): raise ValueError("RESTORE_MISMATCH")
                except Exception: restoration_errors.append(name)
            save(restorationErrors=restoration_errors)
            if restoration_errors: raise ValueError("PROBE_RESTORATION_FAILED")
    save(completed=True, recordedAtUtc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    print(json.dumps({"completed": True, "flowId": flow_id, "noteIds": notes}))


if __name__ == "__main__":
    main()
