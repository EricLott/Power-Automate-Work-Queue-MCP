"""Prove sender claim and controlled failure for one retained synthetic event.

The proof is opt-in and synthetic-only.  It reuses the single pending event
whose destination is the retained synthetic outbox proof sink, claims it with
the public sender operation, records a controlled non-acceptance, and verifies
that the event remains Pending for later retry.  No connector or recipient is
contacted.
"""
import argparse
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from bootstrap_tenant import _cli_command, _cli_request
from generate_sources import uid
from probe_tenant_metadata import _validate_binding


def validate(binding, ledger):
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
    return origin, organization, queue


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--fixture-ledger", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    ledger = json.loads(Path(args.fixture_ledger).read_text(encoding="utf-8-sig"))
    origin, organization, queue = validate(binding, ledger)
    if not args.execute:
        print(json.dumps({"ready": True, "tenantCalls": False, "writes": False, "queueKey": queue}, indent=2))
        return

    output = Path(args.output)
    if output.exists():
        raise ValueError("EVIDENCE_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    proof_id = str(uuid.uuid4())
    evidence = {
        "classification": "synthetic-development-outbox-coordination",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "organizationId": organization,
        "queueKey": queue,
        "proofId": proof_id,
        "tenantCalls": True,
        "writesPerformed": True,
        "externalDestinationsUsed": False,
        "completed": False,
    }
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    command = _cli_command()

    def save(**values):
        evidence.update(values)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def call(method, path, body=None):
        return _cli_request(command, origin, method, path, body, runner=subprocess.run)

    def api(operation, label, data=None):
        body = {
            "QueueKey": queue,
            "RequestId": str(uuid.uuid5(uuid.UUID(proof_id), label)),
            "DataJson": json.dumps(data or {}, separators=(",", ":")),
        }
        return json.loads(call("POST", "qmcp_WQ_" + operation, body)["ResultJson"])

    def query_events():
        rows = call(
            "GET",
            "qmcp_wqevents?$select=qmcp_key,qmcp_document&$filter=qmcp_queuekey eq '" + queue + "'&$top=100",
        ).get("value", [])
        result = []
        for row in rows:
            document = json.loads(row.get("qmcp_document", "{}"))
            result.append({"key": row.get("qmcp_key"), "document": document})
        return result

    def item_state(item_id):
        return call("GET", "workqueueitems(" + item_id + ")?$select=statecode,statuscode")

    try:
        who = call("GET", "WhoAmI")
        if str(who.get("OrganizationId", "")).lower() != organization.lower() or str(who.get("UserId", "")).lower() != ledger["user"].lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        for flow_name in ("ProcessOne", "OnQueueChanged", "SweepQueue", "Intake", "Watchdog", "TestCoordinator", "EmailSender"):
            flow_id = uid("flow:" + flow_name)
            if call("GET", "workflows(" + flow_id + ")?$select=statecode").get("statecode") != 0:
                raise ValueError("FLOWS_MUST_BE_DRAFT")
        pending = [
            event for event in query_events()
            if event["document"].get("State") == "Pending"
            and str(event["document"].get("Destination", "")).startswith("qmcp-synthetic")
        ]
        if len(pending) != 1:
            raise ValueError("EXPECTED_ONE_SYNTHETIC_PENDING_EVENT")
        event = pending[0]
        event_document = event["document"]
        item_id = event_document.get("ItemId")
        if not item_id:
            raise ValueError("EVENT_ITEM_MISSING")
        native_before = item_state(item_id)
        claimed = api("ClaimEvent", "claim")
        claimed_event = claimed.get("Event") or {}
        if claimed.get("Outcome") != "Claimed" or claimed_event.get("Id") != event_document.get("Id"):
            raise ValueError("EVENT_NOT_CLAIMED")
        failed = api(
            "FinishEvent",
            "finish-failure",
            {
                "eventId": claimed_event["Id"],
                "leaseToken": claimed_event["LeaseToken"],
                "accepted": False,
                "code": "SYNTHETIC_MAIL_OFFLINE",
            },
        )
        after_events = query_events()
        matching = [row for row in after_events if row["document"].get("Id") == event_document.get("Id")]
        native_after = item_state(item_id)
        if failed.get("Outcome") != "Pending" or len(matching) != 1:
            raise ValueError("EVENT_FAILURE_NOT_RETAINED")
        final_event = matching[0]["document"]
        if final_event.get("State") != "Pending" or final_event.get("ErrorCode") != "SYNTHETIC_MAIL_OFFLINE" or final_event.get("Tries") != int(event_document.get("Tries", 0)) + 1:
            raise ValueError("EVENT_RETRY_STATE_INVALID")
        if native_after != native_before:
            raise ValueError("NATIVE_ITEM_CHANGED")
        save(
            eventIdRecorded=True,
            destination=event_document.get("Destination"),
            initialState=event_document.get("State"),
            claimOutcome=claimed.get("Outcome"),
            finishOutcome=failed.get("Outcome"),
            finalState=final_event.get("State"),
            finalTries=final_event.get("Tries"),
            finalErrorCode=final_event.get("ErrorCode"),
            nativeItemUnchanged=True,
            limitation="This proves durable claim and retry-state preservation for one synthetic event; connector acceptance, recipient delivery, concurrent sender contention, and a complete Dataverse outage remain separate boundaries.",
            completed=True,
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        save(error=str(error) if str(error).isupper() else "OUTBOX_COORDINATION_PROOF_FAILED", completed=False)
        raise
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not evidence.get("completed"):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise SystemExit(1)
