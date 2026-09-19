"""Prove cancellation while a synthetic test fixture has an active worker attempt.

The proof uses only the explicitly bound development queue. It cancels a run after
native acquisition, verifies the active attempt is left in place, then records a
synthetic worker failure to prove cancellation prevents automatic retry.
"""
import argparse
import datetime
import json
import subprocess
import uuid
from pathlib import Path

from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding


def validate(binding, ledger):
    origin, organization = _validate_binding(binding)
    queue = ledger.get("queueKey")
    queue_id = ledger.get("queue")
    if not isinstance(queue, str) or not queue.startswith("qmcp-proof-") or queue not in binding.get("queueKeys", []):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    try:
        uuid.UUID(queue_id)
    except (TypeError, ValueError, AttributeError):
        raise ValueError("QUEUE_ID_INVALID")
    return origin, organization, queue, queue_id


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--fixture-ledger", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    ledger = json.loads(Path(args.fixture_ledger).read_text(encoding="utf-8-sig"))
    origin, organization, queue, queue_id = validate(binding, ledger)
    output = Path(args.output)
    if not args.execute:
        print(json.dumps({"ready": True, "writes": False, "tenantCalls": False, "queueKey": queue}, indent=2))
        return
    if output.exists():
        raise ValueError("EVIDENCE_EXISTS")
    proof_id = str(uuid.uuid4())
    evidence = {
        "classification": "synthetic-development-active-worker-cancellation",
        "organizationId": organization,
        "queueKey": queue,
        "proofId": proof_id,
        "startedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "completed": False,
        "tenantCalls": True,
        "writesPerformed": True,
        "externalDestinationsUsed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    command = _cli_command()
    run_id = None
    acquired = None
    cancellation_completed = False

    def save(**values):
        evidence.update(values)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")

    def call(method, path, body=None):
        return _cli_request(command, origin, method, path, body, runner=subprocess.run)

    def request(operation, label, data=None, item_id=None, owned=None):
        request_id = evidence.setdefault("requests", {}).setdefault(label, str(uuid.uuid5(uuid.UUID(proof_id), label)))
        body = {"QueueKey": queue, "RequestId": request_id, "DataJson": json.dumps(data or {}, separators=(",", ":"))}
        if item_id is not None:
            body["ItemId"] = item_id
        if owned:
            body.update({key: owned[key] for key in ("ItemId", "AttemptId", "Generation")})
        save(requests=evidence["requests"])
        return json.loads(call("POST", "qmcp_WQ_" + operation, body)["ResultJson"])

    def item_status(item_id):
        return request("GetItemStatus", "status-" + item_id, item_id=item_id)

    try:
        identity = call("GET", "WhoAmI")
        if identity.get("OrganizationId", "").lower() != organization.lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        active = call("GET", "workqueueitems?$select=workqueueitemid&$filter=_workqueueid_value eq " + queue_id + " and statecode eq 0")
        if active.get("value"):
            raise ValueError("SYNTHETIC_QUEUE_NOT_IDLE")
        envelope = {"envelopeVersion": "1.0", "contract": "mail.v1", "correlationId": proof_id, "deduplicationKey": proof_id,
                    "source": {"kind": "synthetic"}, "payload": {"subject": "Synthetic active cancellation", "senderAddress": "synthetic@example.invalid", "bodyText": "No external action is required."}}
        started = request("StartTestRun", "start", {"cases": [{"Id": "active-cancellation", "Input": envelope, "Expected": {}, "ExpectedOutcome": "Exception", "ExpectedErrorCode": "SYNTHETIC_ACTIVE_CANCEL"}]})
        run_id = started["RunId"]
        run = request("GetTestRun", "run-after-start", item_id=run_id)
        item_id = run["Results"][0]["ItemId"]
        prepared = request("PrepareAcquire", "prepare")
        if prepared.get("Outcome") != "Prepared":
            raise ValueError("ACQUIRE_NOT_PREPARED")
        claimed = call("POST", "workqueues(" + queue_id + ")/Microsoft.Dynamics.CRM.Dequeue", {})
        if claimed.get("workqueueitemid", "").lower() != item_id.lower():
            raise ValueError("NATIVE_CLAIM_FAILED")
        acquired = request("ResolveAcquire", "prepare")
        if acquired.get("Outcome") != "Acquired" or acquired.get("ItemId", "").lower() != item_id.lower():
            raise ValueError("ACQUIRE_NOT_RESOLVED")
        save(runId=run_id, itemId=item_id, attemptId=acquired["AttemptId"], generation=acquired["Generation"], nativeBeforeCancel=call("GET", "workqueueitems(" + item_id + ")?$select=statecode,statuscode"))
        cancelled = request("CancelTestRun", "cancel", item_id=run_id)
        replay = request("CancelTestRun", "cancel", item_id=run_id)
        cancellation_completed = True
        after_cancel = item_status(item_id)
        run_after_cancel = request("GetTestRun", "run-after-cancel", item_id=run_id)
        if cancelled != replay or run_after_cancel.get("State") != "Cancelled" or after_cancel.get("Outcome") != "Processing" or after_cancel.get("ActiveAttempt") != acquired["AttemptId"]:
            raise ValueError("ACTIVE_CANCELLATION_NOT_PERSISTED")
        failed = request("Fail", "fail-after-cancel", {"category": "Technical", "code": "SYNTHETIC_ACTIVE_CANCEL", "effect": "None"}, owned=acquired)
        after_fail = item_status(item_id)
        native_after = call("GET", "workqueueitems(" + item_id + ")?$select=statecode,statuscode,delayuntil")
        run_after_fail = request("GetTestRun", "run-after-fail", item_id=run_id)
        attempts = call("GET", "qmcp_wqattempts?$select=qmcp_wqattemptid,qmcp_document&$filter=qmcp_itemid eq '" + item_id + "'")
        if failed.get("Outcome") != "ReviewRequired" or after_fail.get("Outcome") != "Exception" or not after_fail.get("ReviewRequired") or run_after_fail.get("State") != "Cancelled" or run_after_fail["Results"][0]["State"] != "Cancelled":
            raise ValueError("ACTIVE_CANCELLATION_RECONCILIATION_FAILED")
        save(cancelReplayEqual=cancelled == replay, runState=run_after_fail.get("State"), resultStates=[r.get("State") for r in run_after_fail.get("Results", [])], statusAfterCancel=after_cancel, failureOutcome=failed.get("Outcome"), statusAfterFailure=after_fail, nativeAfterFailure=native_after, attemptRows=len(attempts.get("value", [])), completed=True)
    except (OSError, KeyError, TypeError, ValueError) as error:
        save(error=str(error) if str(error).isupper() else "ACTIVE_CANCELLATION_PROOF_FAILED", completed=False)
        raise
    finally:
        if run_id and acquired and not cancellation_completed:
            try:
                request("CancelTestRun", "cleanup-cancel", item_id=run_id)
                request("Fail", "cleanup-fail", {"category": "Technical", "code": "SYNTHETIC_ACTIVE_CANCEL_CLEANUP", "effect": "None"}, owned=acquired)
                save(cleanup="cancelled-and-failed")
            except Exception:
                save(cleanup="incomplete")
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError):
        raise SystemExit(1)
