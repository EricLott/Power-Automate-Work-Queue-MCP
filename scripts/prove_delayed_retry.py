"""Opt-in synthetic proof of delayed retry eligibility and later completion.

Uses the queued item left by the queue-pause proof. Stage mode schedules a
technical retry and records the native future delay. ``--finish`` resumes only
after the caller has waited externally; it never sleeps or treats a transport
error as proof that an item was ineligible.
"""
import argparse
import json
import subprocess
import uuid
from pathlib import Path

from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding


def validate(binding, ledger):
    origin, organization = _validate_binding(binding)
    queue = ledger.get("queueKey")
    item = ledger.get("itemId")
    if not isinstance(queue, str) or not queue.startswith("qmcp-proof-") or queue not in binding.get("queueKeys", []):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    if not isinstance(item, str):
        raise ValueError("SEEDED_ITEM_REQUIRED")
    try:
        uuid.UUID(item)
    except ValueError:
        raise ValueError("SEEDED_ITEM_INVALID")
    return origin, organization, queue, item


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--fixture-ledger", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--finish", action="store_true")
    args = parser.parse_args(argv)
    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    ledger = json.loads(Path(args.fixture_ledger).read_text(encoding="utf-8-sig"))
    origin, organization, queue, item = validate(binding, ledger)
    output = Path(args.output)
    if not args.execute and not args.finish:
        print(json.dumps({"ready": True, "writes": False, "tenantCalls": False, "queueKey": queue, "itemId": item}, indent=2))
        return
    if args.finish:
        if not output.is_file():
            raise ValueError("STAGE_EVIDENCE_REQUIRED")
        evidence = json.loads(output.read_text(encoding="utf-8"))
        if evidence.get("organizationId") != organization or evidence.get("queueKey") != queue or evidence.get("itemId") != item or evidence.get("stage") != "retry-scheduled":
            raise ValueError("STAGE_EVIDENCE_MISMATCH")
    else:
        if output.exists():
            raise ValueError("EVIDENCE_EXISTS")
        evidence = {"classification": "synthetic-native-delayed-retry", "organizationId": organization, "queueKey": queue, "itemId": item, "completed": False, "tenantCalls": True}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    command = _cli_command()
    def call(method, path, body=None):
        return _cli_request(command, origin, method, path, body, runner=subprocess.run)
    def save(**values):
        evidence.update(values)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    def request(op, label, data=None, owned=None):
        rid = evidence.setdefault("requests", {}).setdefault(label, str(uuid.uuid4()))
        body = {"QueueKey": queue, "RequestId": rid, "DataJson": json.dumps(data or {}, separators=(",", ":"))}
        if owned:
            body.update({key: owned[key] for key in ("ItemId", "AttemptId", "Generation")})
        save(requests=evidence["requests"])
        return json.loads(call("POST", "qmcp_WQ_" + op, body)["ResultJson"])
    if args.finish:
        try:
            native = call("POST", "workqueues(" + ledger["queue"] + ")/Microsoft.Dynamics.CRM.Dequeue", {})
        except ValueError as error:
            save(finishOutcome="TransportFailure", completed=False, error="NATIVE_DEQUEUE_FAILED")
            raise
        if not native.get("workqueueitemid"):
            save(finishOutcome="NotDue", completed=False, retryable=True)
            raise SystemExit(1)
        if native["workqueueitemid"].lower() != item.lower():
            save(finishOutcome="WrongItem", completed=False)
            raise ValueError("UNEXPECTED_NATIVE_ITEM")
        acquired = request("ResolveAcquire", "early-prepare")
        if acquired.get("Outcome") != "Acquired" or acquired.get("ItemId", "").lower() != item.lower():
            raise ValueError("ACQUIRE_NOT_RESOLVED")
        record_id = str(uuid.uuid4())
        call("POST", "qmcp_emailrequests", {"qmcp_emailrequestid": record_id, "qmcp_name": "Synthetic delayed retry proof", "qmcp_key": acquired["BusinessKey"], "qmcp_queuekey": queue, "qmcp_document": json.dumps({"testRun": "", "sourceKey": acquired["SourceKey"], "contentHash": acquired["ContentHash"]})})
        completed = request("Complete", "finish-complete", {"table": "qmcp_emailrequest", "recordId": record_id}, acquired)
        if completed.get("Outcome") != "Processed":
            raise ValueError("COMPLETION_NOT_PROCESSED")
        save(finishOutcome="Completed", acquiredItemId=item, recordId=record_id, completed=True)
    else:
        native = call("GET", "workqueueitems(" + item + ")?$select=workqueueitemid,uniqueidbyqueue,statecode,statuscode,delayuntil,input")
        if native.get("statecode") != 0:
            raise ValueError("SEEDED_ITEM_NOT_QUEUED")
        prepared = request("PrepareAcquire", "prepare")
        if prepared.get("Outcome") != "Prepared":
            raise ValueError("ACQUIRE_NOT_PREPARED")
        claimed = call("POST", "workqueues(" + ledger["queue"] + ")/Microsoft.Dynamics.CRM.Dequeue", {})
        if claimed.get("workqueueitemid", "").lower() != item.lower():
            raise ValueError("NATIVE_CLAIM_FAILED")
        acquired = request("ResolveAcquire", "prepare")
        if acquired.get("Outcome") != "Acquired":
            raise ValueError("ACQUIRE_NOT_RESOLVED")
        failed = request("Fail", "fail", {"category": "Technical", "code": "SYNTHETIC_DELAYED_RETRY", "effect": "None"}, acquired)
        if failed.get("Outcome") != "RetryScheduled":
            raise ValueError("RETRY_NOT_SCHEDULED")
        after = call("GET", "workqueueitems(" + item + ")?$select=statecode,statuscode,delayuntil")
        if after.get("statecode") != 0 or not after.get("delayuntil"):
            raise ValueError("DELAYED_QUEUE_STATE_INVALID")
        early_prepared = request("PrepareAcquire", "early-prepare")
        if early_prepared.get("Outcome") != "Prepared":
            raise ValueError("EARLY_CHECK_NOT_PREPARED")
        early_claimed = call("POST", "workqueues(" + ledger["queue"] + ")/Microsoft.Dynamics.CRM.Dequeue", {})
        if early_claimed.get("workqueueitemid"):
            raise ValueError("EARLY_CLAIM")
        early_resolved = request("ResolveAcquire", "early-prepare")
        if early_resolved.get("Outcome") != "Pending":
            raise ValueError("EARLY_RESOLVE_NOT_PENDING")
        save(stage="retry-scheduled", attemptId=acquired.get("AttemptId"), delayUntil=after["delayuntil"], nativeState=after.get("statecode"), earlyClaimed=False, earlyResolveOutcome=early_resolved.get("Outcome"), earlyClaimNotProven=False)
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(str(error))
