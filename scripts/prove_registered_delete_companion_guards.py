"""Prove registered native Delete and companion-table write guards.

The proof reuses a known synthetic item and companion row, so denied writes do
not create additional retained fixtures. It requires exact LIFECYCLE_BYPASS
responses and independent readback after every attempt.
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


def exact_denial(result):
    try:
        return result.returncode != 0 and json.loads(result.stdout).get("error", {}).get("message") == "LIFECYCLE_BYPASS"
    except (AttributeError, TypeError, ValueError):
        return False


def digest(value):
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("binding", "caller-object-id", "expected-user-id", "queue-id", "item-id", "companion-id", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    origin, organization = _validate_binding(binding)
    caller = str(uuid.UUID(args.caller_object_id))
    expected_user = str(uuid.UUID(args.expected_user_id))
    queue_id = str(uuid.UUID(args.queue_id))
    item_id = str(uuid.UUID(args.item_id))
    companion_id = str(uuid.UUID(args.companion_id))
    if not args.execute:
        print(json.dumps({"ready": True, "writes": False, "tenantCalls": False, "queueId": queue_id, "itemId": item_id}, indent=2))
        return

    output = Path(args.output)
    if output.exists():
        raise ValueError("EVIDENCE_EXISTS")
    evidence = {
        "classification": "synthetic-registered-delete-companion-guards",
        "organizationId": organization,
        "queueId": queue_id,
        "itemId": item_id,
        "companionId": companion_id,
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

    def snapshot():
        native = call("GET", "workqueueitems(" + item_id + ")?$select=workqueueitemid,statecode,statuscode,_workqueueid_value")
        companion = call("GET", "qmcp_wqitemcontexts(" + companion_id + ")?$select=qmcp_wqitemcontextid,qmcp_itemid,qmcp_document")
        return {
            "native": {
                "id": native.get("workqueueitemid"),
                "statecode": native.get("statecode"),
                "statuscode": native.get("statuscode"),
                "queueId": native.get("_workqueueid_value"),
                "etag": native.get("@odata.etag"),
            },
            "companion": {
                "id": companion.get("qmcp_wqitemcontextid"),
                "itemId": companion.get("qmcp_itemid"),
                "documentSha256": digest(companion.get("qmcp_document")),
                "document": companion.get("qmcp_document"),
                "etag": companion.get("@odata.etag"),
            },
        }

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

    binding_rows = call("GET", "qmcp_wqqueuebindings?$select=qmcp_key&$filter=qmcp_key eq '" + queue_id + "'&$top=2").get("value", [])
    if len(binding_rows) != 1:
        raise ValueError("REGISTERED_QUEUE_BINDING_NOT_UNIQUE")
    native_queue = call("GET", "workqueues(" + queue_id + ")?$select=statecode")
    if native_queue.get("statecode") != 0:
        raise ValueError("REGISTERED_QUEUE_NOT_ACTIVE")

    before = snapshot()
    if before["native"]["id"].lower() != item_id.lower() or before["native"]["queueId"].lower() != queue_id.lower():
        raise ValueError("RETAINED_ITEM_BINDING_INVALID")
    if before["companion"]["id"].lower() != companion_id.lower() or before["companion"]["itemId"].lower() != item_id.lower():
        raise ValueError("RETAINED_COMPANION_BINDING_INVALID")
    evidence["before"] = {key: {inner: value for inner, value in row.items() if inner != "document"} for key, row in before.items()}
    save()

    def deny(label, method, path, body=None):
        state = {}
        try:
            call(method, path, body, impersonate=True, capture=state)
        except ValueError:
            if not state.get("exactDenial"):
                raise ValueError("EXPECTED_GUARD_FAULT_MISSING")
        else:
            raise ValueError("UNEXPECTED_DIRECT_WRITE_SUCCESS")
        after = snapshot()
        comparable_before = {key: {inner: value for inner, value in row.items() if inner != "document"} for key, row in before.items()}
        comparable_after = {key: {inner: value for inner, value in row.items() if inner != "document"} for key, row in after.items()}
        if comparable_after != comparable_before:
            raise ValueError("DENIED_WRITE_CHANGED_ROW")
        evidence["cases"].append({"case": label, "error": "LIFECYCLE_BYPASS", "after": comparable_after})
        save()

    deny("registered-delete", "DELETE", "workqueueitems(" + item_id + ")")
    deny("companion-update", "PATCH", "qmcp_wqitemcontexts(" + companion_id + ")", {"qmcp_document": before["companion"]["document"]})
    deny("companion-delete", "DELETE", "qmcp_wqitemcontexts(" + companion_id + ")")

    direct_create_id = str(uuid.uuid4())
    deny(
        "companion-create",
        "POST",
        "qmcp_wqitemcontexts",
        {
            "qmcp_wqitemcontextid": direct_create_id,
            "qmcp_itemid": item_id,
            "qmcp_name": "qmcp denied companion create proof",
            "qmcp_key": direct_create_id,
            "qmcp_document": "{}",
        },
    )
    created_rows = call("GET", "qmcp_wqitemcontexts?$select=qmcp_wqitemcontextid&$filter=qmcp_wqitemcontextid eq " + direct_create_id + "&$top=2").get("value", [])
    if not isinstance(created_rows, list) or created_rows:
        raise ValueError("DENIED_CREATE_LEFT_ROW")
    evidence["directCreateIdAbsent"] = True
    evidence["completed"] = True
    save()
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(str(error))
