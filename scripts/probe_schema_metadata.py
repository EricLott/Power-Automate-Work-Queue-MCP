"""Read-only Dataverse schema, contract-dialect, and metadata-limit probe.

The report describes the installed development tenant only. It never sends
POST, PATCH, or DELETE requests and does not turn a column size into a claim
about the service's request or throughput limits.
"""
import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding


def _write(path, report):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def probe(binding, output_path, runner=None):
    origin, expected = _validate_binding(binding)
    command = _cli_command()
    run = runner or subprocess.run

    def get(relative, solution="WQCore"):
        return _cli_request(command, origin, "GET", relative,
                            solution=solution, runner=run)

    who = get("WhoAmI")
    actual = str(uuid.UUID(str(who["OrganizationId"]))).lower()
    if actual != expected:
        raise ValueError("ENVIRONMENT_MISMATCH")

    attribute_targets = {
        "workqueueitem": ["input", "executioncontext", "processingresult"],
        "qmcp_wqdefinition": ["qmcp_document"],
        "qmcp_wqcontract": ["qmcp_document"],
        "qmcp_wqitemcontext": ["qmcp_document"],
    }
    attributes = []
    for table, names in attribute_targets.items():
        for name in names:
            row = get(
                "EntityDefinitions(LogicalName='" + table + "')/Attributes(LogicalName='" + name + "')"
            )
            attributes.append({
                "table": table,
                "logicalName": row.get("LogicalName"),
                "attributeType": row.get("AttributeType"),
                "attributeTypeName": (row.get("AttributeTypeName") or {}).get("Value"),
                "format": row.get("Format"),
                "maxLength": row.get("MaxLength"),
                "isValidForCreate": row.get("IsValidForCreate"),
                "isValidForUpdate": row.get("IsValidForUpdate"),
            })

    rows = get("qmcp_wqcontracts?$select=qmcp_document&$top=100").get("value", [])
    contracts = []
    for row in rows:
        document = row.get("qmcp_document")
        try:
            parsed = json.loads(document) if document else {}
        except (TypeError, json.JSONDecodeError):
            parsed = {}
        schema = parsed.get("Schema") if isinstance(parsed, dict) else {}
        contracts.append({
            "id": parsed.get("Id") if isinstance(parsed, dict) else None,
            "dialect": parsed.get("Dialect") if isinstance(parsed, dict) else None,
            "hashPresent": bool(parsed.get("Hash")) if isinstance(parsed, dict) else False,
            "schemaType": schema.get("type") if isinstance(schema, dict) else None,
            "requiredFields": schema.get("required", []) if isinstance(schema, dict) else [],
            "additionalProperties": schema.get("additionalProperties") if isinstance(schema, dict) else None,
        })

    report = {
        "classification": "read-only-tenant-schema-contract-metadata-probe",
        "organizationId": expected,
        "environmentUrl": origin,
        "apiParameterTypes": {
            "QueueKey": "Edm.String",
            "RequestId": "Edm.String",
            "ItemId": "Edm.String",
            "AttemptId": "Edm.String",
            "Generation": "Edm.Int32",
            "ExpectedVersion": "Edm.String",
            "DataJson": "Edm.String",
        },
        "attributes": attributes,
        "contracts": contracts,
        "allContractDialectsDraft07": bool(contracts) and all(
            row["dialect"] == "http://json-schema.org/draft-07/schema#" for row in contracts
        ),
        "allObservedMemoLimitsAtLeastBytes": bool(attributes) and all(
            (row["maxLength"] or 0) >= 1048576 for row in attributes
        ),
        "writesPerformed": False,
        "limitations": [
            "Memo MaxLength is a column metadata boundary, not proof of the Web API request ceiling or service capacity.",
            "The probe reads the installed development tenant only; it does not test clean-import activation timing.",
            "Framework UTF-8, depth, complexity, and schema-subset limits remain covered by local boundary tests.",
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
        raise SystemExit("TENANT_SCHEMA_METADATA_PROBE_FAILED")
