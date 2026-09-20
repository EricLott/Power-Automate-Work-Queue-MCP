"""Run a bounded Watchdog recurrence against a fresh synthetic retention fixture."""
import argparse
import json
import subprocess
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path

from bootstrap_tenant import _cli_command, _cli_request
from generate_sources import uid
from probe_tenant_metadata import _validate_binding


def validate(binding, ledger):
    origin, organization = _validate_binding(binding)
    queue = ledger.get("queueKey")
    if not isinstance(queue, str) or not queue.startswith("qmcp-proof-") or queue not in binding.get("queueKeys", []):
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
    output = Path(args.output)
    if not args.execute:
        print(json.dumps({"ready": True, "tenantCalls": False, "writes": False, "queueKey": queue}, indent=2))
        return
    if output.exists():
        raise ValueError("EVIDENCE_EXISTS")

    proof_id = str(uuid.uuid4())
    workflow_id = uid("flow:Watchdog")
    workflow_path = "workflows(" + workflow_id + ")"
    evidence = {
        "classification": "synthetic-development-scheduled-retention",
        "organizationId": organization,
        "queueKey": queue,
        "proofId": proof_id,
        "workflow": "Watchdog",
        "startedAtUtc": datetime.now(timezone.utc).isoformat(),
        "tenantCalls": True,
        "writesPerformed": True,
        "externalDestinationsUsed": False,
        "completed": False,
        "workflowRestored": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    command = _cli_command()
    original = None

    def save(**values):
        evidence.update(values)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")

    def call(method, path, body=None):
        return _cli_request(command, origin, method, path, body, runner=subprocess.run)

    def api(operation, label, data=None, owned=None):
        body = {
            "QueueKey": queue,
            "RequestId": str(uuid.uuid5(uuid.UUID(proof_id), label)),
            "DataJson": json.dumps(data or {}, separators=(",", ":")),
        }
        if owned:
            body.update({key: owned[key] for key in ("ItemId", "AttemptId", "Generation")})
        return json.loads(call("POST", "qmcp_WQ_" + operation, body)["ResultJson"])

    def acquire(label):
        prepared = api("PrepareAcquire", label, {"flowId": "retention-scheduler", "runId": proof_id})
        if prepared.get("Outcome") != "Prepared":
            raise ValueError("RETENTION_ACQUIRE_NOT_PREPARED")
        native = call("POST", "workqueues(" + ledger["queue"] + ")/Microsoft.Dynamics.CRM.Dequeue", {})
        resolved = api("ResolveAcquire", label)
        if resolved.get("Outcome") != "Acquired":
            raise ValueError("RETENTION_ACQUIRE_NOT_RESOLVED")
        return native, resolved

    def normalize_hosts(value):
        if isinstance(value, dict):
            host = value.get("host")
            if isinstance(host, dict) and "connectionReferenceName" in host:
                host["connectionName"] = host.pop("connectionReferenceName")
            for child in value.values():
                normalize_hosts(child)
        elif isinstance(value, list):
            for child in value:
                normalize_hosts(child)

    def workflow_parameters(clientdata):
        data = json.loads(clientdata)
        parameters = data["properties"]["definition"]["parameters"]
        return parameters

    def configure_workflow():
        nonlocal original
        original = call("GET", workflow_path + "?$select=workflowid,name,statecode,statuscode,clientdata")
        if original.get("workflowid", "").lower() != workflow_id.lower() or original.get("name") != "Watchdog":
            raise ValueError("WORKFLOW_ID_MISMATCH")
        original_data = json.loads(original["clientdata"])
        normalize_hosts(original_data)
        temporary = json.loads(json.dumps(original_data))
        parameters = temporary["properties"]["definition"]["parameters"]
        parameters["qmcp_QueueKey"]["defaultValue"] = queue
        parameters["qmcp_NativeQueueId"]["defaultValue"] = ledger["queue"]
        call("PATCH", workflow_path, {"statecode": 0})
        call("PATCH", workflow_path, {"clientdata": json.dumps(temporary, separators=(",", ":"))})
        configured = call("GET", workflow_path + "?$select=statecode,clientdata")
        configured_parameters = workflow_parameters(configured["clientdata"])
        if configured_parameters["qmcp_QueueKey"]["defaultValue"] != queue or configured_parameters["qmcp_NativeQueueId"]["defaultValue"].lower() != ledger["queue"].lower():
            raise ValueError("WORKFLOW_BINDING_NOT_CONFIRMED")
        call("PATCH", workflow_path, {"statecode": 1})
        active = call("GET", workflow_path + "?$select=statecode,statuscode")
        if active.get("statecode") != 1:
            raise ValueError("WORKFLOW_NOT_ACTIVE")
        save(workflowActivated=True)

    def restore_workflow():
        if original is None:
            return
        original_data = json.loads(original["clientdata"])
        normalize_hosts(original_data)
        call("PATCH", workflow_path, {"statecode": 0})
        call("PATCH", workflow_path, {"clientdata": json.dumps(original_data, separators=(",", ":"))})
        restored = call("GET", workflow_path + "?$select=statecode,clientdata")
        if restored.get("statecode") != 0:
            raise ValueError("WORKFLOW_RESTORE_FAILED")
        parameters = workflow_parameters(restored["clientdata"])
        expected = workflow_parameters(json.dumps(original_data, separators=(",", ":")))
        if parameters != expected:
            raise ValueError("WORKFLOW_PARAMETERS_NOT_RESTORED")
        save(workflowRestored=True, finalWorkflowState="Draft")

    try:
        who = call("GET", "WhoAmI")
        if str(who.get("OrganizationId", "")).lower() != organization.lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        fixture = api("SeedRetentionFixture", "seed", {"fixtureId": proof_id, "ageDays": 366})
        save(seed={key: fixture[key] for key in ("Outcome", "FixtureId", "CreatedOn", "RedactionItemId", "ProtectedItemId", "ReceiptKey", "TestRunId")})
        first_native, first = acquire("retention-acquire-1")
        redaction_id = fixture["RedactionItemId"]
        protected_id = fixture["ProtectedItemId"]
        if first["ItemId"] == redaction_id:
            first_result = api("Complete", "redaction-complete-1", {"table": "qmcp_synthetic", "recordId": str(uuid.uuid5(uuid.UUID(proof_id), "redaction-output"))}, first)
        elif first["ItemId"] == protected_id:
            first_result = api("Fail", "protected-fail-1", {"category": "Business", "code": "SYNTHETIC_REVIEW_REQUIRED"}, first)
        else:
            raise ValueError("RETENTION_UNEXPECTED_ITEM")
        _, second = acquire("retention-acquire-2")
        if second["ItemId"] == redaction_id:
            second_result = api("Complete", "redaction-complete-2", {"table": "qmcp_synthetic", "recordId": str(uuid.uuid5(uuid.UUID(proof_id), "redaction-output"))}, second)
        elif second["ItemId"] == protected_id:
            second_result = api("Fail", "protected-fail-2", {"category": "Business", "code": "SYNTHETIC_REVIEW_REQUIRED"}, second)
        else:
            raise ValueError("RETENTION_UNEXPECTED_ITEM")
        save(finalized=True, finalStates={"redaction": first_result if first["ItemId"] == redaction_id else second_result, "protected": first_result if first["ItemId"] == protected_id else second_result})
        configure_workflow()
        deadline = time.monotonic() + 150
        observed = None
        while time.monotonic() < deadline:
            commands = call("GET", "qmcp_wqcommands?$select=qmcp_key,qmcp_document&$filter=qmcp_queuekey eq '" + queue + "'&$top=100").get("value", [])
            receipts = []
            for row in commands:
                document = json.loads(row.get("qmcp_document", "{}"))
                if document.get("Operation") not in {"RunMaintenance", "ApplyRetention"}:
                    continue
                result = document.get("Result", "{}")
                if isinstance(result, str):
                    try:
                        result = json.loads(result)
                    except (TypeError, ValueError):
                        result = {}
                receipts.append({"operation": document.get("Operation"), "outcome": result.get("Outcome"), "changed": result.get("Changed"), "inputsRedacted": result.get("InputsRedacted"), "receiptsRedacted": result.get("ReceiptsRedacted"), "evidenceRowsPurged": result.get("EvidenceRowsPurged"), "protectedRows": result.get("ProtectedRows")})
            redaction = call("GET", "workqueueitems(" + redaction_id + ")?$select=input,statecode,statuscode,createdon")
            protected = call("GET", "workqueueitems(" + protected_id + ")?$select=input,statecode,statuscode,createdon")
            runs = call("GET", "qmcp_wqtestruns?$select=qmcp_key&$filter=qmcp_key eq '" + fixture["TestRunId"] + "'&$top=2").get("value", [])
            applied = next((r for r in receipts if r.get("operation") == "ApplyRetention" and r.get("outcome") == "RetentionApplied" and r.get("inputsRedacted") == 1 and r.get("receiptsRedacted") == 1 and r.get("evidenceRowsPurged") == 3 and (r.get("protectedRows") or 0) >= 1), None)
            if applied and redaction.get("input") == "{}" and protected.get("input") != "{}" and not runs:
                observed = {"receipts": receipts, "retention": applied, "redaction": {"statecode": redaction.get("statecode"), "statuscode": redaction.get("statuscode"), "inputRedacted": True}, "protected": {"statecode": protected.get("statecode"), "statuscode": protected.get("statuscode"), "inputPreserved": True}, "testRunPresentAfterRetention": False}
                break
            time.sleep(5)
        if observed is None:
            raise ValueError("SCHEDULED_RETENTION_NOT_OBSERVED")
        save(observations=observed, completed=True, limitation="Synthetic scheduled Watchdog execution is proven; storage cost, managed-release compatibility, and broader scheduler behavior remain separate gates.")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        save(error=str(error) if str(error).isupper() else "SCHEDULED_RETENTION_PROOF_FAILED", completed=False)
        raise
    finally:
        try:
            restore_workflow()
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            save(restoreError=str(error) if str(error).isupper() else "WORKFLOW_RESTORE_FAILED", completed=False)
            raise
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise SystemExit(1)
