"""Prove that Watchdog quarantines a native Processing item with no context.

The proof is opt-in and synthetic-only.  It enqueues one synthetic item,
claims it through the documented native Dequeue action without creating a
framework acquisition intent, and invokes the installed RunMaintenance API.
The expected conservative result is native Exception with no business output.
No customer flow, mailbox, notification, or external destination is used.
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
        "classification": "synthetic-development-orphan-reconciliation",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "organizationId": organization,
        "queueKey": queue,
        "proofId": proof_id,
        "tenantCalls": True,
        "writesPerformed": True,
        "externalDestinationsUsed": False,
        "completed": False,
        "orphanCreated": False,
        "maintenanceObserved": False,
    }
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    command = _cli_command()

    def save(**values):
        evidence.update(values)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def call(method, path, body=None):
        return _cli_request(command, origin, method, path, body, runner=subprocess.run)

    def api(operation, label, data=None, item=None):
        body = {
            "QueueKey": queue,
            "RequestId": str(uuid.uuid5(uuid.UUID(proof_id), label)),
            "DataJson": json.dumps(data or {}, separators=(",", ":")),
        }
        if item:
            body["ItemId"] = item
        response = call("POST", "qmcp_WQ_" + operation, body)
        return json.loads(response["ResultJson"])

    def query_items():
        return call(
            "GET",
            "workqueueitems?$select=workqueueitemid,statecode,statuscode,input&$filter=_workqueueid_value eq "
            + ledger["queue"]
            + "&$top=100",
        ).get("value", [])

    def query_context(item):
        return call(
            "GET",
            "qmcp_wqitemcontexts?$select=qmcp_document&$filter=qmcp_itemid eq " + item + "&$top=2",
        ).get("value", [])

    def query_attempts(item):
        return call(
            "GET",
            "qmcp_wqattempts?$select=qmcp_document&$filter=qmcp_itemid eq " + item + "&$top=10",
        ).get("value", [])

    try:
        who = call("GET", "WhoAmI")
        if str(who.get("OrganizationId", "")).lower() != organization.lower() or str(who.get("UserId", "")).lower() != ledger["user"].lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        for flow_name in ("ProcessOne", "OnQueueChanged", "SweepQueue", "Intake", "Watchdog", "TestCoordinator", "EmailSender"):
            flow_id = uid("flow:" + flow_name)
            if call("GET", "workflows(" + flow_id + ")?$select=statecode").get("statecode") != 0:
                raise ValueError("FLOWS_MUST_BE_DRAFT")
        active = [row for row in query_items() if row.get("statecode") in (0, 1)]
        if active:
            raise ValueError("SYNTHETIC_QUEUE_NOT_IDLE")

        envelope = {
            "envelopeVersion": "1.0",
            "contract": "mail.v1",
            "correlationId": proof_id,
            "deduplicationKey": proof_id,
            "source": {"kind": "synthetic"},
            "payload": {
                "subject": "Synthetic orphan reconciliation proof",
                "senderAddress": "synthetic@example.invalid",
                "bodyText": "Synthetic watchdog validation only.",
            },
        }
        enqueued = api("Enqueue", "enqueue", envelope)
        item = enqueued.get("ItemId")
        if enqueued.get("Outcome") != "Enqueued" or not item:
            raise ValueError("ENQUEUE_NOT_CONFIRMED")
        dequeued = call("POST", "workqueues(" + ledger["queue"] + ")/Microsoft.Dynamics.CRM.Dequeue", {})
        if dequeued.get("workqueueitemid", "").lower() != item.lower():
            raise ValueError("UNEXPECTED_ITEM_DEQUEUED")
        native_before = call("GET", "workqueueitems(" + item + ")?$select=statecode,statuscode")
        if native_before.get("statecode") != 1 or query_context(item) or query_attempts(item):
            raise ValueError("ORPHAN_PRECONDITION_NOT_CONFIRMED")
        save(itemId=item, nativeBefore=native_before, orphanCreated=True)

        maintenance = api("RunMaintenance", "maintenance")
        native_after = call("GET", "workqueueitems(" + item + ")?$select=statecode,statuscode")
        contexts_after = query_context(item)
        attempts_after = query_attempts(item)
        save(
            maintenance={"outcome": maintenance.get("Outcome"), "changed": maintenance.get("Changed")},
            nativeAfter=native_after,
            contextCount=len(contexts_after),
            attemptCount=len(attempts_after),
            maintenanceObserved=True,
        )
        if maintenance.get("Outcome") != "Swept" or maintenance.get("Changed") != 1:
            raise ValueError("ORPHAN_NOT_SWEPT")
        if native_after.get("statecode") != 4 or native_after.get("statuscode") != 4:
            raise ValueError("ORPHAN_NOT_QUARANTINED")
        if len(contexts_after) != 1 or attempts_after:
            raise ValueError("ORPHAN_FRAMEWORK_STATE_INVALID")
        context = json.loads(contexts_after[0]["qmcp_document"])
        if context.get("ReviewRequired") is not True or context.get("ActiveAttempt"):
            raise ValueError("ORPHAN_REVIEW_STATE_INVALID")
        save(completed=True, limitation="This proves one native Processing item without framework context is quarantined as Exception; review metadata, bounded multi-page scans, separate identity, and managed-release behavior remain open.")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        save(error=str(error) if str(error).isupper() else "ORPHAN_RECONCILIATION_PROOF_FAILED", completed=False)
        raise
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not evidence.get("completed"):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise SystemExit(1)
