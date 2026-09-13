"""Read-only proof that a Dataverse caller-object identity resolves as expected."""
import argparse
import json
import subprocess
import sys
import urllib.parse
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from bootstrap_tenant import _cli_command, _cli_request
    from probe_tenant_metadata import _validate_binding
except ModuleNotFoundError:  # pragma: no cover - direct script path above handles this
    from scripts.bootstrap_tenant import _cli_command, _cli_request
    from scripts.probe_tenant_metadata import _validate_binding


def _guid(value, label):
    try:
        return str(uuid.UUID(str(value))).lower()
    except (ValueError, TypeError, AttributeError):
        raise ValueError(label + "_INVALID_UUID") from None


def _write_new(path, evidence):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(evidence, stream, indent=2)


def probe(binding, caller_object_id, expected_user_id, output_path, runner=None,
          execute=False):
    """Run the identity check, or return a no-call plan when ``execute`` is false."""
    origin, organization = _validate_binding(binding)
    caller = _guid(caller_object_id, "CALLER_OBJECT")
    expected_user = _guid(expected_user_id, "EXPECTED_USER")
    if not execute:
        return {"ready": True, "writes": False, "tenantCalls": False,
                "organizationId": organization, "callerObjectId": caller,
                "expectedUserId": expected_user}

    evidence = {
        "completed": False,
        "classification": "read-only-effective-identity",
        "organizationId": organization,
        "callerObjectId": caller,
        "expectedUserId": expected_user,
        "writesPerformed": False,
    }
    _write_new(output_path, evidence)
    command = _cli_command()

    def invoke(relative, impersonate=False):
        def with_caller(args, **kwargs):
            # CallerObjectId is a Dataverse request header, appended without
            # exposing or handling an access token in this script.
            if impersonate:
                args = list(args) + ["--header", "CallerObjectId: " + caller]
            return (runner or subprocess.run)(args, **kwargs)
        return _cli_request(command, origin, "GET", relative,
                            runner=with_caller)

    def save(**values):
        evidence.update(values)
        Path(output_path).write_text(json.dumps(evidence, indent=2) + "\n",
                                     encoding="utf-8")

    who = invoke("WhoAmI")
    actual_org = _guid(who.get("OrganizationId"), "WHOAMI_ORGANIZATION")
    operator = _guid(who.get("UserId"), "WHOAMI_USER")
    if actual_org != organization:
        raise ValueError("ENVIRONMENT_MISMATCH")
    if operator == expected_user:
        raise ValueError("CALLER_DID_NOT_DIFFER")
    save(whoAmI={"organizationId": actual_org, "operatorUserId": operator})

    fetch = ("<fetch top='2'><entity name='systemuser'>"
             "<attribute name='systemuserid'/><attribute name='azureactivedirectoryobjectid'/>"
             "<filter><condition attribute='systemuserid' operator='eq' value='" +
             expected_user + "'/></filter></entity></fetch>")
    relative = "systemusers?fetchXml=" + urllib.parse.quote(fetch, safe="")
    rows = invoke(relative).get("value")
    if not isinstance(rows, list) or len(rows) != 1:
        raise ValueError("EXPECTED_USER_NOT_UNIQUE")
    row = rows[0]
    row_user = _guid(row.get("systemuserid"), "EXPECTED_USER")
    if row_user != expected_user:
        raise ValueError("EXPECTED_USER_MISMATCH")
    aad = row.get("azureactivedirectoryobjectid")
    if not isinstance(aad, str) or not aad.strip() or aad.lower() != caller:
        raise ValueError("EXPECTED_USER_MAPPING_MISSING")
    control_fetch = ("<fetch top='2'><entity name='systemuser'><attribute name='systemuserid'/>"
                     "<filter><condition attribute='systemuserid' operator='eq-userid'/>"
                     "</filter></entity></fetch>")
    control_path = "systemusers?fetchXml=" + urllib.parse.quote(control_fetch, safe="")
    control_rows = invoke(control_path).get("value")
    if not isinstance(control_rows, list) or len(control_rows) != 1 or _guid(control_rows[0].get("systemuserid"), "WHOAMI_USER") != operator:
        raise ValueError("OPERATOR_IDENTITY_CONTROL_FAILED")
    impersonated_rows = invoke(control_path, impersonate=True).get("value")
    if not isinstance(impersonated_rows, list) or len(impersonated_rows) != 1:
        raise ValueError("IMPERSONATED_USER_NOT_UNIQUE")
    impersonated_user = _guid(impersonated_rows[0].get("systemuserid"), "IMPERSONATED_USER")
    if impersonated_user != expected_user or impersonated_user == operator:
        raise ValueError("IMPERSONATED_IDENTITY_MISMATCH")
    save(impersonatedUser={"systemUserId": impersonated_user,
                           "azureActiveDirectoryObjectId": aad}, completed=True)
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--caller-object-id", required=True)
    parser.add_argument("--expected-user-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        result = probe(json.loads(Path(args.binding).read_text(encoding="utf-8-sig")),
                       args.caller_object_id, args.expected_user_id, args.output,
                       execute=args.execute)
        print(json.dumps(result, indent=2))
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        raise SystemExit(str(error))
