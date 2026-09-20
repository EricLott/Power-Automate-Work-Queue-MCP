"""Prove registered companion Update/Delete guards across every configured table.

The probe uses one retained synthetic row per companion table. Every attempted
write is made under the verified distinct identity, requires the exact
``LIFECYCLE_BYPASS`` fault, and independently compares the row after the
attempt. No roles, queue policy, or business records are changed.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap_tenant import _cli_command, _cli_request
from probe_effective_identity import probe
from probe_tenant_metadata import _validate_binding
from prove_native_queue_pause import FLOW_IDS


COMPANIONS = (
    ("qmcp_wqdefinitions", "qmcp_wqdefinitionid"),
    ("qmcp_wqqueuebindings", "qmcp_wqqueuebindingid"),
    ("qmcp_wqcontracts", "qmcp_wqcontractid"),
    ("qmcp_wqitemcontexts", "qmcp_wqitemcontextid"),
    ("qmcp_wqattempts", "qmcp_wqattemptid"),
    ("qmcp_wqcommands", "qmcp_wqcommandid"),
    ("qmcp_wqevents", "qmcp_wqeventid"),
    ("qmcp_wqcursors", "qmcp_wqcursorid"),
    ("qmcp_wqintakefailures", "qmcp_wqintakefailureid"),
    ("qmcp_wqtestcases", "qmcp_wqtestcaseid"),
    ("qmcp_wqtestruns", "qmcp_wqtestrunid"),
    ("qmcp_wqtestresults", "qmcp_wqtestresultid"),
)


def digest(value):
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def exact_denial(result):
    try:
        return result.returncode != 0 and json.loads(result.stdout).get("error", {}).get("message") == "LIFECYCLE_BYPASS"
    except (AttributeError, TypeError, ValueError):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("binding", "caller-object-id", "expected-user-id", "queue-key", "native-queue-id", "native-item-id", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    origin, organization = _validate_binding(binding)
    caller = str(uuid.UUID(args.caller_object_id))
    expected_user = str(uuid.UUID(args.expected_user_id))
    queue = args.queue_key
    native_queue = str(uuid.UUID(args.native_queue_id))
    native_item = str(uuid.UUID(args.native_item_id))
    if not queue.startswith("qmcp-proof-") or queue not in binding.get("queueKeys", []):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    if not args.execute:
        print(json.dumps({"ready": True, "writes": False, "tenantCalls": False, "queueKey": queue, "companions": len(COMPANIONS)}, indent=2))
        return

    output = Path(args.output)
    if output.exists():
        raise ValueError("EVIDENCE_EXISTS")
    evidence = {
        "classification": "synthetic-registered-companion-update-delete-matrix",
        "organizationId": organization,
        "queueKey": queue,
        "nativeQueueId": native_queue,
        "nativeItemId": native_item,
        "completed": False,
        "tenantCalls": True,
        "businessDataChanged": False,
        "rolesChanged": False,
        "queuePolicyChanged": False,
        "cases": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)

    def save(**values):
        evidence.update(values)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    save()
    command = _cli_command()

    def call(method, path, body=None, impersonate=False, capture=None):
        def runner(cli_args, **kwargs):
            if impersonate:
                cli_args = cli_args + ["--header", "CallerObjectId: " + caller]
            result = subprocess.run(cli_args, **kwargs)
            if capture is not None:
                capture["exactDenial"] = exact_denial(result)
            return result
        return _cli_request(command, origin, method, path, body, runner=runner)

    identity = probe(binding, caller, expected_user, str(output) + ".identity.json", execute=True)
    if not identity.get("completed"):
        raise ValueError("IDENTITY_NOT_PROVEN")
    evidence["effectiveIdentityVerified"] = True

    who = call("GET", "WhoAmI")
    if str(who.get("OrganizationId", "")).lower() != organization.lower():
        raise ValueError("ENVIRONMENT_MISMATCH")
    for flow_id in FLOW_IDS:
        if call("GET", "workflows(" + flow_id + ")?$select=statecode").get("statecode") != 0:
            raise ValueError("FLOWS_MUST_BE_DRAFT")
    binding_rows = call("GET", "qmcp_wqqueuebindings?$select=qmcp_key&$filter=qmcp_key eq '" + native_queue + "'&$top=2").get("value", [])
    if len(binding_rows) != 1:
        raise ValueError("REGISTERED_QUEUE_BINDING_NOT_UNIQUE")
    if call("GET", "workqueues(" + native_queue + ")?$select=statecode").get("statecode") != 0:
        raise ValueError("REGISTERED_QUEUE_NOT_ACTIVE")

    def native_snapshot():
        row = call("GET", "workqueueitems(" + native_item + ")?$select=workqueueitemid,statecode,statuscode,_workqueueid_value")
        return {"id": row.get("workqueueitemid"), "state": row.get("statecode"), "status": row.get("statuscode"), "queue": row.get("_workqueueid_value"), "etag": row.get("@odata.etag")}

    native_before = native_snapshot()
    if native_before["id"].lower() != native_item.lower() or native_before["queue"].lower() != native_queue.lower():
        raise ValueError("NATIVE_ITEM_BINDING_INVALID")

    def companion_snapshot(collection, primary, row_id):
        row = call("GET", collection + "(" + row_id + ")?$select=" + primary + ",qmcp_key,qmcp_queuekey,qmcp_itemid,qmcp_document")
        return {"id": row.get(primary), "key": row.get("qmcp_key"), "queue": row.get("qmcp_queuekey"), "item": row.get("qmcp_itemid"), "documentSha256": digest(row.get("qmcp_document")), "document": row.get("qmcp_document") or "{}", "etag": row.get("@odata.etag")}

    rows = []
    for collection, primary in COMPANIONS:
        found = call("GET", collection + "?$select=" + primary + ",qmcp_key,qmcp_queuekey,qmcp_itemid,qmcp_document&$filter=qmcp_queuekey eq '" + queue + "'&$top=1").get("value", [])
        if len(found) != 1:
            raise ValueError("COMPANION_ROW_NOT_FOUND")
        row_id = found[0].get(primary)
        if not row_id:
            raise ValueError("COMPANION_ID_MISSING")
        rows.append((collection, primary, row_id, companion_snapshot(collection, primary, row_id)))

    evidence["before"] = {collection: {k: v for k, v in before.items() if k != "document"} for collection, _, _, before in rows}
    evidence["nativeBefore"] = native_before
    save()

    def deny(label, method, path, body, before, after_reader):
        state = {}
        try:
            call(method, path, body, impersonate=True, capture=state)
        except ValueError:
            if not state.get("exactDenial"):
                raise ValueError("EXPECTED_GUARD_FAULT_MISSING")
        else:
            raise ValueError("UNEXPECTED_DIRECT_WRITE_SUCCESS")
        after = after_reader()
        comparable_before = {k: v for k, v in before.items() if k != "document"}
        comparable_after = {k: v for k, v in after.items() if k != "document"}
        if comparable_after != comparable_before:
            raise ValueError("DENIED_WRITE_CHANGED_ROW")
        evidence["cases"].append({"case": label, "error": "LIFECYCLE_BYPASS", "unchanged": True})
        save()

    native_after = lambda: native_snapshot()
    deny("registered-native-delete", "DELETE", "workqueueitems(" + native_item + ")", None, native_before, native_after)
    for collection, primary, row_id, before in rows:
        snapshot = lambda collection=collection, primary=primary, row_id=row_id: companion_snapshot(collection, primary, row_id)
        deny(collection + "-update", "PATCH", collection + "(" + row_id + ")", {"qmcp_document": before["document"]}, before, snapshot)
        deny(collection + "-delete", "DELETE", collection + "(" + row_id + ")", None, before, snapshot)

    evidence["companionTables"] = len(COMPANIONS)
    evidence["denialCount"] = len(evidence["cases"])
    evidence["completed"] = True
    save()
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError):
        raise SystemExit(1)
