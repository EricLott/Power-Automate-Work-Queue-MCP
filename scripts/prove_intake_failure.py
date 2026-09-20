"""Prove pre-enqueue intake failure recording and deduplication.

The proof is opt-in and synthetic-only.  It reports an intake failure before
any queue item exists, repeats the same logical report with a new command
request, and verifies one redacted failure row plus one durable notification
event.  It never invokes a mailbox, queue worker, sender, or external target.
"""
import argparse
import hashlib
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
    source = "synthetic-intake-proof/" + proof_id
    correlation = "synthetic-intake-correlation/" + proof_id
    code = "SYNTHETIC_INTAKE_FAILURE"
    failure_id = hashlib.sha256((queue + "|" + source + "|" + correlation + "|" + code).encode()).hexdigest()
    event_id = hashlib.sha256((queue + "||" + failure_id + "|IntakeFailure").encode()).hexdigest()
    evidence = {
        "classification": "synthetic-development-intake-failure",
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

    def report(label):
        body = {
            "QueueKey": queue,
            "RequestId": str(uuid.uuid5(uuid.UUID(proof_id), label)),
            "DataJson": json.dumps({"source": source, "correlationId": correlation, "code": code}, separators=(",", ":")),
        }
        return json.loads(call("POST", "qmcp_WQ_ReportIntakeFailure", body)["ResultJson"])

    def get_rows(entity, key):
        return call("GET", entity + "?$select=qmcp_key,qmcp_document,versionnumber&$filter=qmcp_key eq '" + key + "'&$top=2").get("value", [])

    try:
        who = call("GET", "WhoAmI")
        if str(who.get("OrganizationId", "")).lower() != organization.lower() or str(who.get("UserId", "")).lower() != ledger["user"].lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        for flow_name in ("ProcessOne", "OnQueueChanged", "SweepQueue", "Intake", "Watchdog", "TestCoordinator", "EmailSender"):
            flow_id = uid("flow:" + flow_name)
            if call("GET", "workflows(" + flow_id + ")?$select=statecode").get("statecode") != 0:
                raise ValueError("FLOWS_MUST_BE_DRAFT")
        native_items = call(
            "GET",
            "workqueueitems?$select=workqueueitemid&$filter=_workqueueid_value eq " + ledger["queue"] + "&$top=1",
        ).get("value", [])
        first = report("report-first")
        second = report("report-second")
        failures = get_rows("qmcp_wqintakefailures", failure_id)
        events = get_rows("qmcp_wqevents", event_id)
        native_items_after = call(
            "GET",
            "workqueueitems?$select=workqueueitemid&$filter=_workqueueid_value eq " + ledger["queue"] + "&$top=1",
        ).get("value", [])
        if first.get("Outcome") != "Recorded" or second != first:
            raise ValueError("REPORT_REPLAY_NOT_STABLE")
        if len(failures) != 1:
            raise ValueError("REPORT_NOT_DEDUPLICATED")
        failure_document = json.loads(failures[0].get("qmcp_document", "{}"))
        if failure_document.get("SourceHash") != hashlib.sha256(source.encode()).hexdigest():
            raise ValueError("SOURCE_HASH_NOT_RECORDED")
        destinations = failure_document.get("Destinations") or []
        expected_events = 1 if destinations else 0
        if len(events) != expected_events:
            raise ValueError("EVENT_DEDUPLICATION_NOT_CONFIRMED")
        if [row.get("workqueueitemid") for row in native_items_after] != [row.get("workqueueitemid") for row in native_items]:
            raise ValueError("NATIVE_QUEUE_CHANGED")
        if source in failures[0].get("qmcp_document", "") or any(source in event.get("qmcp_document", "") for event in events):
            raise ValueError("SOURCE_REFERENCE_LEAKED")
        save(
            nativeItemCountBeforeReport=len(native_items),
            nativeQueueUnchanged=True,
            firstOutcome=first.get("Outcome"),
            secondOutcome=second.get("Outcome"),
            failureRowCount=len(failures),
            eventRowCount=len(events),
            notificationDestinationsConfigured=len(destinations),
            sourceReferenceStored=False,
            failureIdRecorded=True,
            notificationEventChecked=True,
            limitation="This proves the framework path while Dataverse is available; native flow alerts remain the fallback when Dataverse itself is unavailable, and no sender or recipient delivery is claimed.",
            completed=True,
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        save(error=str(error) if str(error).isupper() else "INTAKE_FAILURE_PROOF_FAILED", completed=False)
        raise
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not evidence.get("completed"):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise SystemExit(1)
