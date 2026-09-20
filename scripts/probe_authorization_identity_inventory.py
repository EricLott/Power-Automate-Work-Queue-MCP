"""Record the available WQ role assignments without mutating the tenant.

The probe is intentionally read-only. It reports role names and assignment
counts, plus redacted role summaries for explicitly supplied known identities;
it never publishes user names, object IDs, tokens, or credentials.
"""
import argparse
import json
import subprocess
import uuid
from collections import Counter
from pathlib import Path

from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--fixture-ledger", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--known-user-id", action="append", default=[])
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    ledger = json.loads(Path(args.fixture_ledger).read_text(encoding="utf-8-sig"))
    origin, organization = _validate_binding(binding)
    queue = ledger.get("queueKey")
    if not isinstance(queue, str) or queue not in binding.get("queueKeys", []):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    for value in args.known_user_id:
        uuid.UUID(value)
    if not args.execute:
        print(json.dumps({"ready": True, "tenantCalls": False, "writes": False, "queueKey": queue}, indent=2))
        return
    output = Path(args.output)
    if output.exists():
        raise ValueError("EVIDENCE_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "classification": "live-authorization-role-inventory",
        "date": "2026-09-20",
        "environment": "authorized-development-tenant",
        "organizationId": organization,
        "queueKey": queue,
        "tenantCalls": True,
        "writesPerformed": False,
        "completed": False,
    }
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    command = _cli_command()

    def save(**values):
        evidence.update(values)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def get(path):
        return _cli_request(command, origin, "GET", path, None, runner=subprocess.run)

    try:
        who = get("WhoAmI")
        if str(who.get("OrganizationId", "")).lower() != organization.lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        roles = get("roles?$select=roleid,name&$filter=startswith(name,'WQ')").get("value")
        if not isinstance(roles, list) or not roles:
            raise ValueError("WQ_ROLES_NOT_FOUND")
        role_names = {row["roleid"]: row["name"] for row in roles if row.get("roleid") and row.get("name")}
        if len(role_names) != len(roles):
            raise ValueError("WQ_ROLE_READBACK_INVALID")
        role_filter = " or ".join("roleid eq " + role_id for role_id in role_names)
        assignments = get("systemuserrolescollection?$select=systemuserid,roleid&$filter=" + role_filter).get("value")
        if not isinstance(assignments, list):
            raise ValueError("ROLE_ASSIGNMENT_READBACK_INVALID")
        counts = Counter(role_names[row["roleid"]] for row in assignments if row.get("roleid") in role_names)
        known = []
        for user_id in args.known_user_id:
            row = get("systemusers(" + user_id + ")?$select=systemuserid&$expand=systemuserroles_association($select=name)")
            if str(row.get("systemuserid", "")).lower() != user_id.lower():
                raise ValueError("KNOWN_IDENTITY_READBACK_FAILED")
            role_rows = row.get("systemuserroles_association")
            if not isinstance(role_rows, list):
                raise ValueError("KNOWN_IDENTITY_ROLE_READBACK_INVALID")
            known.append({"identityVerified": True, "roleNames": sorted(value["name"] for value in role_rows if value.get("name"))})
        unique_role_names = sorted(set(role_names.values()))
        save(
            wqRoleCount=len(role_names),
            wqRoleNames=sorted(role_names.values()),
            uniqueWqRoleCount=len(unique_role_names),
            uniqueWqRoleNames=unique_role_names,
            wqAssignmentCount=len(assignments),
            assignmentsByRole={name: counts.get(name, 0) for name in sorted(set(role_names.values()))},
            knownIdentities=known,
            noWqRoleAssignments=len(assignments) == 0,
            completed=True,
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        save(error=str(error) if str(error).isupper() else "ROLE_INVENTORY_FAILED", completed=False)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not evidence.get("completed"):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise SystemExit(1)
