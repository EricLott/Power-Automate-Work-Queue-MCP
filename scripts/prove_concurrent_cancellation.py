"""Probe native Dataverse concurrency at the active test-cancellation boundary.

The proof creates one synthetic active worker attempt, dispatches cancellation
and the worker's terminal failure concurrently, records the exact serialized
outcomes, and then reconciles the fixture. A serialized pair is evidence about
ordering only; native concurrency is verified only when the losing transaction
returns a structured VERSION_CONFLICT and the winner's state is preserved.
"""
import argparse
import datetime
import json
import re
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
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
        uuid.UUID(str(queue_id))
    except (TypeError, ValueError, AttributeError):
        raise ValueError("QUEUE_ID_INVALID")
    return origin, organization, queue, str(queue_id)


def fault_from_stdout(stdout):
    """Extract an inner Dataverse/plugin fault without retaining raw payloads."""
    if "VERSION_CONFLICT" in safe_fault_markers(stdout):
        return "VERSION_CONFLICT"
    try:
        outer = json.loads(stdout or "")
        message = outer.get("error", {}).get("message") if isinstance(outer, dict) else None
        nested = json.loads(message) if isinstance(message, str) else {}
        if isinstance(nested, dict):
            error = nested.get("error", nested)
            if isinstance(error, dict):
                for key in ("code", "errorCode", "message"):
                    value = error.get(key)
                    if isinstance(value, str) and "VERSION_CONFLICT" in value:
                        return "VERSION_CONFLICT"
        if isinstance(message, str) and "VERSION_CONFLICT" in message:
            return "VERSION_CONFLICT"
    except (TypeError, ValueError, AttributeError):
        pass
    return None


def safe_fault_markers(stdout):
    """Return only known diagnostic tokens from a failed CLI response."""
    text = stdout or ""
    patterns = (
        r"-2147088254",  # Dataverse ConcurrencyVersionMismatch
        r"ConcurrencyVersionMismatch",
        r"VERSION_CONFLICT",
        r"RUNTIME_FAILURE",
        r"DATAVERSE_CLI_(?:FAILED|INVALID_RESPONSE|TIMEOUT)",
        r"HTTP_STATUS_[45][0-9]{2}",
    )
    return sorted({match.group(0) for pattern in patterns for match in re.finditer(pattern, text, re.IGNORECASE)})


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
        "classification": "synthetic-development-native-concurrent-cancellation",
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
    reconciliation = []

    def save(**values):
        evidence.update(values)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")

    def call(method, path, body=None):
        return _cli_request(command, origin, method, path, body, runner=subprocess.run)

    def request(operation, label, data=None, item_id=None, owned=None, request_id=None):
        request_id = request_id or str(uuid.uuid5(uuid.UUID(proof_id), label))
        body = {"QueueKey": queue, "RequestId": request_id, "DataJson": json.dumps(data or {}, separators=(",", ":"))}
        if item_id is not None:
            body["ItemId"] = item_id
        if owned:
            body.update({key: owned[key] for key in ("ItemId", "AttemptId", "Generation")})
        return json.loads(call("POST", "qmcp_WQ_" + operation, body)["ResultJson"])

    def run_race(operations):
        """Dispatch independent CLI processes after one shared barrier."""
        gate = threading.Barrier(len(operations))

        def one(operation, label, data=None, item_id=None, owned=None):
            request_id = str(uuid.uuid5(uuid.UUID(proof_id), label))
            body = {"QueueKey": queue, "RequestId": request_id, "DataJson": json.dumps(data or {}, separators=(",", ":"))}
            if item_id is not None:
                body["ItemId"] = item_id
            if owned:
                body.update({key: owned[key] for key in ("ItemId", "AttemptId", "Generation")})

            capture = {}

            def runner(*argv, **kwargs):
                result = subprocess.run(*argv, **kwargs)
                capture["markers"] = safe_fault_markers((result.stdout or "") + "\n" + (result.stderr or ""))
                if result.returncode:
                    capture["fault"] = fault_from_stdout((result.stdout or "") + "\n" + (result.stderr or ""))
                else:
                    capture["fault"] = None
                return result

            gate.wait(timeout=30)
            started = time.monotonic()
            try:
                value = json.loads(_cli_request(command, origin, "POST", "qmcp_WQ_" + operation, body, runner=runner)["ResultJson"])
                return {"label": label, "requestId": request_id, "outcome": "succeeded", "result": value,
                        "elapsedMs": round((time.monotonic() - started) * 1000, 1),
                        "faultMarkers": capture.get("markers", [])}
            except ValueError as error:
                return {"label": label, "requestId": request_id, "outcome": "failed",
                        "fault": capture.get("fault") or str(error),
                        "faultMarkers": capture.get("markers", []),
                        "elapsedMs": round((time.monotonic() - started) * 1000, 1)}

        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(one, *operation) for operation in operations]
            return [future.result() for future in futures]

    def status(item_id):
        return request("GetItemStatus", "status-" + item_id, item_id=item_id)

    try:
        identity = call("GET", "WhoAmI")
        if str(identity.get("OrganizationId", "")).lower() != organization.lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        active = call("GET", "workqueueitems?$select=workqueueitemid&$filter=_workqueueid_value eq " + queue_id + " and statecode eq 0")
        if active.get("value"):
            raise ValueError("SYNTHETIC_QUEUE_NOT_IDLE")

        envelope = {
            "envelopeVersion": "1.0", "contract": "mail.v1", "correlationId": proof_id,
            "deduplicationKey": proof_id, "source": {"kind": "synthetic"},
            "payload": {"subject": "Synthetic concurrent cancellation", "senderAddress": "synthetic@example.invalid",
                        "bodyText": "No external action is required."},
        }
        started = request("StartTestRun", "start", {"cases": [{"Id": "concurrent-cancellation", "Input": envelope,
            "Expected": {}, "ExpectedOutcome": "Exception", "ExpectedErrorCode": "SYNTHETIC_CONCURRENT_CANCEL"}]})
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
        if acquired.get("Outcome") != "Acquired":
            raise ValueError("ACQUIRE_NOT_RESOLVED")
        save(runId=run_id, itemId=item_id, attemptId=acquired["AttemptId"], generation=acquired["Generation"],
             nativeBeforeRace=call("GET", "workqueueitems(" + item_id + ")?$select=statecode,statuscode"))

        race = run_race([
            ("CancelTestRun", "race-cancel", None, run_id, None),
            ("Fail", "race-fail", {"category": "Technical", "code": "SYNTHETIC_CONCURRENT_CANCEL", "effect": "None"}, None, acquired),
        ])
        save(race=race)

        # Reconcile regardless of ordering. A fresh cancellation request makes
        # the durable test result terminal; the owned failure then closes any
        # surviving active attempt without permitting a retry after cancellation.
        try:
            request("CancelTestRun", "reconcile-cancel", item_id=run_id)
            reconciliation.append("cancel")
        except ValueError as error:
            reconciliation.append("cancel-failed:" + str(error))
        try:
            request("Fail", "reconcile-fail", {"category": "Technical", "code": "SYNTHETIC_CONCURRENT_CANCEL", "effect": "None"}, owned=acquired)
            reconciliation.append("fail")
        except ValueError as error:
            reconciliation.append("fail-failed:" + str(error))

        after = {
            "run": request("GetTestRun", "run-after-reconcile", item_id=run_id),
            "status": status(item_id),
            "native": call("GET", "workqueueitems(" + item_id + ")?$select=statecode,statuscode"),
        }
        native_conflict = any(result.get("fault") == "VERSION_CONFLICT" for result in race)
        winner_count = sum(result.get("outcome") == "succeeded" for result in race)
        terminal = after["run"].get("State") == "Cancelled" and after["status"].get("Outcome") == "Exception" and after["status"].get("ReviewRequired") is True
        save(nativeConcurrencyVerified=native_conflict and winner_count == 1, serializedWithoutConflict=not native_conflict,
             winnerCount=winner_count, afterReconciliation=after, reconciliation=reconciliation,
             completed=True)
        if not terminal:
            raise ValueError("CONCURRENT_CANCELLATION_RECONCILIATION_FAILED")
    except (OSError, KeyError, TypeError, ValueError) as error:
        save(error=str(error) if str(error).isupper() else "CONCURRENT_CANCELLATION_PROOF_FAILED", completed=False,
             reconciliation=reconciliation)
        raise
    finally:
        if run_id and acquired and evidence.get("completed") is not True:
            try:
                request("CancelTestRun", "cleanup-cancel", item_id=run_id)
                request("Fail", "cleanup-fail", {"category": "Technical", "code": "SYNTHETIC_CONCURRENT_CANCEL_CLEANUP", "effect": "None"}, owned=acquired)
                save(cleanup="cancelled-and-failed")
            except Exception:
                save(cleanup="incomplete")
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError):
        raise SystemExit(1)
