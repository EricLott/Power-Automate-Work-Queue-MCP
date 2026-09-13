"""Opt-in synthetic proof that a disabled queue refuses acquisition.

Default mode performs validation only. ``--execute`` seeds one synthetic item,
temporarily registers the existing policy with ``Enabled=false``, checks the
public PrepareAcquire result and native state, then restores the policy. It
does not acquire, complete, or create business records.
"""
import argparse
import json
import subprocess
import uuid
from pathlib import Path

from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding

FLOW_IDS = ("a9c6e175-d6f6-50a7-860c-8fdb91da396e", "5391db37-d88c-57c5-839a-d66c26ffd46a", "d6228ad8-9758-567d-a1a3-2d5c97ab4c73", "6a491be2-4f32-549d-8afb-92d556e5c89b", "014c3583-22a5-5146-bf25-94768d689092", "656a2463-6fd0-5892-b382-3fc8babdc8ed", "a0fed279-6860-5897-912d-ccfabee2de0d")


def validate(binding, ledger):
    origin, organization = _validate_binding(binding)
    queue_key = ledger.get("queueKey")
    if not isinstance(queue_key, str) or not queue_key.startswith("qmcp-proof-") or queue_key not in binding.get("queueKeys", []):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    try:
        uuid.UUID(ledger["queue"])
    except (KeyError, ValueError, TypeError):
        raise ValueError("NATIVE_QUEUE_ID_REQUIRED")
    return origin, organization, queue_key


def policies_equal(left, right):
    return {k:v for k,v in left.items() if k != "Revision"} == {k:v for k,v in right.items() if k != "Revision"}

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
    output = Path(args.output)
    evidence = {"classification": "synthetic-native-queue-pause", "organizationId": organization, "queueKey": queue, "completed": False, "tenantCalls": False}
    if not args.execute:
        print(json.dumps({"ready": True, "writes": False, "tenantCalls": False, "queueKey": queue}, indent=2))
        return
    if output.exists():
        raise ValueError("EVIDENCE_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    evidence["tenantCalls"] = True
    command = _cli_command()
    def call(method, relative, body=None):
        return _cli_request(command, origin, method, relative, body, runner=subprocess.run)
    def save(**values):
        evidence.update(values)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    changed = False
    original = None
    try:
        who = call("GET", "WhoAmI")
        if str(who.get("OrganizationId", "")).lower() != organization.lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        for flow in FLOW_IDS:
            row = call("GET", "workflows(" + flow + ")?$select=statecode")
            if row.get("statecode") != 0:
                raise ValueError("FLOWS_MUST_BE_DRAFT")
        rows = call("GET", "qmcp_wqdefinitions?$select=qmcp_document,versionnumber&$filter=qmcp_key eq '" + queue + "'&$top=2").get("value")
        if not isinstance(rows, list) or len(rows) != 1:
            raise ValueError("POLICY_NOT_UNIQUE")
        original = json.loads(rows[0]["qmcp_document"])
        version = rows[0]["versionnumber"]
        if original.get("NativeQueueId", "").lower() != ledger["queue"].lower():
            raise ValueError("NATIVE_QUEUE_MISMATCH")
        if not original.get("Enabled"):
            raise ValueError("QUEUE_ALREADY_PAUSED")
        save(originalPolicy=original, originalVersion=version)
        payload = {"envelopeVersion": "1.0", "contract": "mail.v1", "correlationId": str(uuid.uuid4()), "deduplicationKey": "queue-pause-proof-" + str(uuid.uuid4()), "source": {"kind": "synthetic"}, "payload": {"subject": "Synthetic queue pause proof", "senderAddress": "guard@example.invalid", "bodyText": "Please restore the office printer."}}
        enqueue_id = str(uuid.uuid4())
        save(seedRequestId=enqueue_id, seedEnvelope=payload)
        enqueued = call("POST", "qmcp_WQ_Enqueue", {"QueueKey": queue, "RequestId": enqueue_id, "DataJson": json.dumps(payload, separators=(",", ":"))})
        item_id = json.loads(enqueued["ResultJson"])["ItemId"]
        save(seedRequestId=enqueue_id, itemId=item_id)
        native_before = call("GET", "workqueueitems(" + item_id + ")?$select=workqueueitemid,uniqueidbyqueue,statecode,statuscode")
        if native_before.get("statecode") != 0:
            raise ValueError("SEEDED_ITEM_NOT_QUEUED")
        paused = dict(original); paused["Enabled"] = False
        register_id = str(uuid.uuid4())
        save(pauseRequestId=register_id)
        changed = True
        reg = call("POST", "qmcp_WQ_RegisterQueue", {"QueueKey": queue, "RequestId": register_id, "ExpectedVersion": str(version), "DataJson": json.dumps(paused, separators=(",", ":"))})
        changed = True
        save(pauseRequestId=register_id, pauseResult=json.loads(reg["ResultJson"]))
        acquire_id = str(uuid.uuid4())
        save(acquireRequestId=acquire_id)
        acquire = call("POST", "qmcp_WQ_PrepareAcquire", {"QueueKey": queue, "RequestId": acquire_id, "DataJson": "{}"})
        outcome = json.loads(acquire["ResultJson"])
        native_after = call("GET", "workqueueitems(" + item_id + ")?$select=workqueueitemid,uniqueidbyqueue,statecode,statuscode")
        if outcome.get("Outcome") != "QueuePaused" or native_after != native_before:
            raise ValueError("QUEUE_PAUSE_ASSERTION_FAILED")
        save(acquireRequestId=acquire_id, acquireOutcome=outcome, nativeBefore=native_before, nativeAfter=native_after, nativeRowUnchanged=True, seededItemLeftQueued=True)
    finally:
        if changed and original is not None:
            rows = call("GET", "qmcp_wqdefinitions?$select=qmcp_document,versionnumber&$filter=qmcp_key eq '" + queue + "'&$top=2").get("value", [])
            if len(rows) != 1:
                save(completed=False, restoreError="POLICY_NOT_UNIQUE")
            else:
                current = json.loads(rows[0]["qmcp_document"])
                if not policies_equal(current, paused) and not policies_equal(current, original):
                    save(restoreError="CONCURRENT_POLICY_CHANGE")
                    raise ValueError("CONCURRENT_POLICY_CHANGE")
                restore_id = str(uuid.uuid4())
                save(restoreRequestId=restore_id)
                call("POST", "qmcp_WQ_RegisterQueue", {"QueueKey": queue, "RequestId": restore_id, "ExpectedVersion": str(rows[0]["versionnumber"]), "DataJson": json.dumps(original, separators=(",", ":"))})
                verified = call("GET", "qmcp_wqdefinitions?$select=qmcp_document,versionnumber&$filter=qmcp_key eq '" + queue + "'&$top=2")["value"]
                if len(verified) != 1 or not policies_equal(json.loads(verified[0]["qmcp_document"]), original):
                    raise ValueError("RESTORE_READBACK_FAILED")
                save(policyRestored=True, restoredPolicy=json.loads(verified[0]["qmcp_document"]), restoredVersion=verified[0]["versionnumber"])
        if evidence.get("acquireOutcome", {}).get("Outcome") == "QueuePaused" and evidence.get("policyRestored"):
            save(completed=True)
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(str(error))
