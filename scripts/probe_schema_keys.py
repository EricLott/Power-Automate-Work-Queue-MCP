"""Read-only Dataverse schema and alternate-key activation probe.

This utility verifies the organization binding, reads the installed framework
tables and their alternate-key index state, and writes only a redacted report.
It never sends POST, PATCH or DELETE requests.
"""
import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from bootstrap_tenant import _cli_command, _cli_request
    from probe_tenant_metadata import _validate_binding
except ModuleNotFoundError:  # pragma: no cover - direct script path above handles this
    from scripts.bootstrap_tenant import _cli_command, _cli_request
    from scripts.probe_tenant_metadata import _validate_binding


def _write(path, report):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def probe(binding, output_path, runner=None):
    origin, expected = _validate_binding(binding)
    registration_path = Path(__file__).resolve().parents[1] / "config" / "registration.json"
    registration = json.loads(registration_path.read_text(encoding="utf-8"))
    tables = sorted({entry["table"] for entry in registration["guardSteps"]})
    command = _cli_command()

    def get(relative):
        return _cli_request(command, origin, "GET", relative, solution="WQCore",
                            runner=runner or subprocess.run)

    who = get("WhoAmI")
    actual = str(uuid.UUID(str(who["OrganizationId"]))).lower()
    if actual != expected:
        raise ValueError("ENVIRONMENT_MISMATCH")

    records = []
    for table in tables:
        metadata = get(
            "EntityDefinitions(LogicalName='" + table + "')"
            "?$select=LogicalName,EntitySetName,PrimaryIdAttribute"
        )
        keys = get(
            "EntityDefinitions(LogicalName='" + table + "')/Keys"
            "?$select=SchemaName,LogicalName,EntityKeyIndexStatus"
        ).get("value", [])
        records.append({
            "logicalName": metadata.get("LogicalName"),
            "entitySetName": metadata.get("EntitySetName"),
            "primaryIdAttribute": metadata.get("PrimaryIdAttribute"),
            "keys": [
                {
                    "schemaName": row.get("SchemaName"),
                    "logicalName": row.get("LogicalName"),
                    "indexStatus": row.get("EntityKeyIndexStatus"),
                }
                for row in keys
            ],
        })

    active = sum(
        1 for row in records
        if len(row["keys"]) == 1 and row["keys"][0]["indexStatus"] == "Active"
    )
    report = {
        "classification": "read-only-tenant-schema-key-probe",
        "organizationId": expected,
        "environmentUrl": origin,
        "tablesRequested": len(tables),
        "tablesObserved": len(records),
        "tablesWithExactlyOneActiveKey": active,
        "allExpectedKeysActive": active == len(tables),
        "tables": records,
        "writesPerformed": False,
        "limitations": [
            "Metadata reads do not prove write permissions, transactions, connector activation, or production compatibility.",
            "This probe records the installed development tenant only.",
            "Local framework limits remain separate from native Dataverse payload and metadata limits.",
        ],
    }
    _write(output_path, report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--dataverse-cli", action="store_true")
    args = parser.parse_args()
    if not args.dataverse_cli:
        raise SystemExit("DATAVERSE_CLI_REQUIRED")
    try:
        result = probe(json.loads(Path(args.binding).read_text(encoding="utf-8-sig")), args.output)
        print(json.dumps(result, indent=2))
    except (ValueError, KeyError, OSError, json.JSONDecodeError):
        raise SystemExit("TENANT_SCHEMA_KEY_PROBE_FAILED")
