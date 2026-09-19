"""Run a bounded synthetic Dataverse capacity profile.

This is an opt-in development-tenant observation, not a service-limit or
production-capacity claim. It processes sequential synthetic items through the
installed queue APIs, counts every Web API request made by the harness, and
records native final states plus throttling/error observations.
"""
import argparse
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding


def validate(binding, ledger, items):
    origin, organization = _validate_binding(binding)
    queue = ledger.get("queueKey")
    if not isinstance(queue, str) or not queue.startswith("qmcp-proof-"):
        raise ValueError("SYNTHETIC_QUEUE_REQUIRED")
    if queue not in binding.get("queueKeys", []):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    for key in ("queue", "team", "user"):
        try:
            uuid.UUID(ledger[key])
        except (KeyError, TypeError, ValueError):
            raise ValueError("FIXTURE_ID_INVALID")
    if not isinstance(items, int) or not 1 <= items <= 25:
        raise ValueError("ITEM_COUNT_OUT_OF_RANGE")
    return origin, organization, queue, ledger["queue"], ledger["team"], ledger["user"]


def parse_result(response):
    try:
        return json.loads(response["ResultJson"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("RESULT_JSON_INVALID")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--fixture-ledger", required=True)
    parser.add_argument("--items", type=int, default=5)
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    ledger = json.loads(Path(args.fixture_ledger).read_text(encoding="utf-8-sig"))
    origin, organization, queue, native_queue, team, expected_user = validate(binding, ledger, args.items)
    output = Path(args.output)
    if not args.execute:
        print(json.dumps({"ready": True, "writes": False, "tenantCalls": False, "queueKey": queue, "items": args.items}, indent=2))
        return
    if output.exists():
        raise ValueError("EVIDENCE_EXISTS")
    evidence = {
        "classification": "synthetic-development-tenant-capacity-profile",
        "organizationId": organization,
        "environmentUrl": origin,
        "queueKey": queue,
        "requestedItems": args.items,
        "startedAtUtc": datetime.now(timezone.utc).isoformat(),
        "completed": False,
        "tenantCalls": True,
        "requestUsage": {"total": 0, "byMethod": {}, "byRoute": {}},
        "items": [],
        "errors": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    command = _cli_command()

    def call(method, route, body=None):
        usage = evidence["requestUsage"]
        usage["total"] += 1
        usage["byMethod"][method] = usage["byMethod"].get(method, 0) + 1
        usage["byRoute"][route.split("?")[0]] = usage["byRoute"].get(route.split("?")[0], 0) + 1
        try:
            return _cli_request(command, origin, method, route, body, runner=subprocess.run)
        except ValueError as error:
            evidence["errors"].append({"route": route.split("?")[0], "code": str(error)})
            raise

    def save():
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")

    def request(operation, request_id, data=None, owned=None):
        body = {"QueueKey": queue, "RequestId": request_id, "DataJson": json.dumps(data or {}, separators=(",", ":"))}
        if owned:
            body.update({key: owned[key] for key in ("ItemId", "AttemptId", "Generation")})
        return parse_result(call("POST", "qmcp_WQ_" + operation, body))

    try:
        identity = call("GET", "WhoAmI")
        if str(identity.get("OrganizationId", "")).lower() != organization.lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        if str(identity.get("UserId", "")).lower() != expected_user.lower():
            raise ValueError("FIXTURE_USER_MISMATCH")
        existing = call("GET", "workqueueitems?$select=workqueueitemid,statecode,statuscode&$filter=_workqueueid_value eq " + native_queue + " and (statecode eq 0 or statecode eq 1)&$top=100").get("value", [])
        if existing:
            raise ValueError("QUEUE_NOT_IDLE")
        started = time.perf_counter()
        for index in range(args.items):
            item_started = time.perf_counter()
            suffix = str(uuid.uuid4())
            enqueue_request = str(uuid.uuid4())
            payload = {
                "envelopeVersion": "1.0", "contract": "mail.v1", "correlationId": "tenant-capacity-" + suffix,
                "deduplicationKey": "tenant-capacity-" + suffix, "source": {"kind": "synthetic", "profile": "tenant-capacity"},
                "payload": {"subject": "Synthetic tenant capacity profile", "senderAddress": "synthetic@example.invalid", "bodyText": "Synthetic bounded capacity profile; no mailbox content."},
            }
            enqueued = request("Enqueue", enqueue_request, payload)
            if enqueued.get("Outcome") != "Enqueued":
                raise ValueError("ENQUEUE_NOT_CONFIRMED")
            item_id = enqueued.get("ItemId")
            prepare_request = str(uuid.uuid4())
            prepared = request("PrepareAcquire", prepare_request)
            if prepared.get("Outcome") != "Prepared":
                raise ValueError("ACQUIRE_NOT_PREPARED")
            native = call("POST", "workqueues(" + native_queue + ")/Microsoft.Dynamics.CRM.Dequeue", {})
            if str(native.get("workqueueitemid", "")).lower() != str(item_id).lower():
                raise ValueError("UNEXPECTED_NATIVE_ITEM")
            acquired = request("ResolveAcquire", prepare_request)
            if acquired.get("Outcome") != "Acquired" or str(acquired.get("ItemId", "")).lower() != str(item_id).lower():
                raise ValueError("ACQUIRE_NOT_RESOLVED")
            record_id = str(uuid.uuid4())
            call("POST", "qmcp_emailrequests", {
                "qmcp_emailrequestid": record_id,
                "qmcp_name": "Synthetic tenant capacity profile",
                "qmcp_key": acquired["BusinessKey"],
                "qmcp_queuekey": queue,
                "qmcp_document": json.dumps({"sourceKey": acquired["SourceKey"], "contentHash": acquired["ContentHash"]}),
                "ownerid@odata.bind": "/teams(" + team + ")",
            })
            completed = request("Complete", str(uuid.uuid4()), {"table": "qmcp_emailrequest", "recordId": record_id}, acquired)
            if completed.get("Outcome") != "Processed":
                raise ValueError("COMPLETION_NOT_PROCESSED")
            after = call("GET", "workqueueitems(" + item_id + ")?$select=statecode,statuscode,requeuecount,delayuntil")
            if after.get("statecode") != 2:
                raise ValueError("NATIVE_FINAL_STATE_INVALID")
            evidence["items"].append({
                "index": index,
                "itemId": item_id,
                "attemptId": acquired.get("AttemptId"),
                "recordId": record_id,
                "nativeState": after.get("statecode"),
                "statusCode": after.get("statuscode"),
                "requeueCount": after.get("requeuecount"),
                "elapsedSeconds": round(time.perf_counter() - item_started, 6),
            })
            save()
        evidence["elapsedSeconds"] = round(time.perf_counter() - started, 6)
        evidence["observations"] = {
            "itemsProcessed": len(evidence["items"]),
            "itemsPerSecond": round(len(evidence["items"]) / evidence["elapsedSeconds"], 3) if evidence["elapsedSeconds"] else None,
            "observedRequestCount": evidence["requestUsage"]["total"],
            "observedRequestsPerItem": round(evidence["requestUsage"]["total"] / args.items, 3),
            "retryCount": sum(item.get("requeueCount") or 0 for item in evidence["items"]),
            "throttlingObserved": any(error.get("code") in {"DATAVERSE_CLI_FAILED", "DATAVERSE_CLI_TIMEOUT"} for error in evidence["errors"]),
            "errorCount": len(evidence["errors"]),
        }
        evidence["limits"] = {
            "requestedItemMaximum": 25,
            "profileShape": "sequential enqueue/acquire/complete",
            "serviceLimitClaim": False,
            "productionCapacityClaim": False,
            "requestBudgetClaim": False,
            "promptOrSenderCalls": 0,
        }
        evidence["completed"] = True
    except (OSError, KeyError, TypeError, ValueError) as error:
        evidence["error"] = str(error)
        evidence["finishedAtUtc"] = datetime.now(timezone.utc).isoformat()
        save()
        raise
    evidence["finishedAtUtc"] = datetime.now(timezone.utc).isoformat()
    evidence["elapsedSeconds"] = round(time.perf_counter() - started, 6)
    evidence["completed"] = True
    save()
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(str(error))
