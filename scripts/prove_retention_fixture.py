"""Run the bounded synthetic aged-row retention proof on an authorized tenant."""
import argparse
import json
import subprocess
import uuid
from pathlib import Path

from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding


def validate(binding, ledger):
    origin, organization = _validate_binding(binding)
    queue = ledger.get("queueKey")
    if not isinstance(queue, str) or not queue.startswith("qmcp-proof-") or queue not in binding.get("queueKeys", []):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
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
    evidence = {
        "classification": "synthetic-development-aged-retention",
        "organizationId": organization,
        "queueKey": queue,
        "proofId": proof_id,
        "startedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "tenantCalls": True,
        "writesPerformed": True,
        "externalDestinationsUsed": False,
        "completed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")

    command = _cli_command()

    def save(**values):
        evidence.update(values)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")

    def call(method, path, body=None):
        return _cli_request(command, origin, method, path, body, runner=subprocess.run)

    def api(operation, label, data=None, item_id=None, owned=None):
        body = {"QueueKey": queue, "RequestId": str(uuid.uuid5(uuid.UUID(proof_id), label)), "DataJson": json.dumps(data or {}, separators=(",", ":"))}
        if item_id is not None:
            body["ItemId"] = item_id
        if owned is not None:
            for key in ("ItemId", "AttemptId", "Generation"):
                body[key] = owned[key]
        return json.loads(call("POST", "qmcp_WQ_" + operation, body)["ResultJson"])

    def acquire(label):
        prepared = api("PrepareAcquire", label, {"flowId": "retention-fixture", "runId": proof_id})
        if prepared.get("Outcome") != "Prepared":
            raise ValueError("RETENTION_ACQUIRE_NOT_PREPARED")
        native = call("POST", "workqueues(" + ledger["queue"] + ")/Microsoft.Dynamics.CRM.Dequeue", {})
        resolved = api("ResolveAcquire", label)
        return {"prepared": prepared, "native": native, "resolved": resolved}

    try:
        who = call("GET", "WhoAmI")
        if str(who.get("OrganizationId", "")).lower() != organization.lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        fixture = api("SeedRetentionFixture", "seed", {"fixtureId": proof_id, "ageDays": 366})
        save(seed={key: fixture[key] for key in ("Outcome", "FixtureId", "CreatedOn", "RedactionItemId", "ProtectedItemId", "ReceiptKey", "TestRunId")})
        first = acquire("retention-acquire-1")["resolved"]
        if first.get("Outcome") != "Acquired" or first.get("ItemId") not in {fixture["RedactionItemId"], fixture["ProtectedItemId"]}:
            raise ValueError("RETENTION_FIRST_ACQUIRE_FAILED")
        if first["ItemId"] == fixture["RedactionItemId"]:
            completed = api("Complete", "redaction-complete", {"table": "qmcp_synthetic", "recordId": str(uuid.uuid5(uuid.UUID(proof_id), "redaction-output"))}, owned=first)
            first_result = completed
        else:
            first_result = api("Fail", "protected-fail", {"category": "Business", "code": "SYNTHETIC_REVIEW_REQUIRED"}, owned=first)
        second = acquire("retention-acquire-2")["resolved"]
        if second.get("Outcome") != "Acquired" or second.get("ItemId") != (fixture["ProtectedItemId"] if first["ItemId"] == fixture["RedactionItemId"] else fixture["RedactionItemId"]):
            raise ValueError("RETENTION_SECOND_ACQUIRE_FAILED")
        if second["ItemId"] == fixture["RedactionItemId"]:
            second_result = api("Complete", "redaction-complete-2", {"table": "qmcp_synthetic", "recordId": str(uuid.uuid5(uuid.UUID(proof_id), "redaction-output"))}, owned=second)
        else:
            second_result = api("Fail", "protected-fail-2", {"category": "Business", "code": "SYNTHETIC_REVIEW_REQUIRED"}, owned=second)
        completed = first_result if first["ItemId"] == fixture["RedactionItemId"] else second_result
        failed = first_result if first["ItemId"] == fixture["ProtectedItemId"] else second_result
        save(finalize=[
            {"Outcome": completed.get("Outcome"), "FixtureId": proof_id, "FinalizedItemId": completed.get("ItemId"), "FinalizedStatus": "Processed", "RedactionItemId": fixture["RedactionItemId"], "ProtectedItemId": fixture["ProtectedItemId"]},
            {"Outcome": failed.get("Outcome"), "FixtureId": proof_id, "FinalizedItemId": failed.get("ItemId"), "FinalizedStatus": "Exception", "RedactionItemId": fixture["RedactionItemId"], "ProtectedItemId": fixture["ProtectedItemId"]},
        ])
        applied = api("ApplyRetention", "apply")
        save(retention={key: applied.get(key) for key in ("Outcome", "InputsRedacted", "ReceiptsRedacted", "AttemptsPurged", "ErrorsPurged", "EvidenceRowsPurged", "ProtectedRows", "ReplayWindowDays")})

        redaction = call("GET", "workqueueitems(" + fixture["RedactionItemId"] + ")?$select=input,statecode,statuscode,createdon")
        protected = call("GET", "workqueueitems(" + fixture["ProtectedItemId"] + ")?$select=input,statecode,statuscode,createdon")
        status = api("GetItemStatus", "status", {}, fixture["ProtectedItemId"])
        commands = call("GET", "qmcp_wqcommands?$select=qmcp_key,qmcp_document&$filter=qmcp_key eq '" + fixture["ReceiptKey"] + "'&$top=2").get("value", [])
        runs = call("GET", "qmcp_wqtestruns?$select=qmcp_key&$filter=qmcp_key eq '" + fixture["TestRunId"] + "'&$top=2").get("value", [])
        command_outcome = ""
        if len(commands) == 1:
            command_outcome = json.loads(commands[0].get("qmcp_document", "{}" )).get("Result", "")
            try:
                command_outcome = json.loads(command_outcome).get("Outcome", "")
            except (TypeError, ValueError):
                command_outcome = ""
        observations = {
            "redaction": {"statecode": redaction.get("statecode"), "statuscode": redaction.get("statuscode"), "inputRedacted": redaction.get("input") == "{}", "createdOn": redaction.get("createdon")},
            "protected": {"statecode": protected.get("statecode"), "statuscode": protected.get("statuscode"), "inputPreserved": protected.get("input") != "{}", "createdOn": protected.get("createdon")},
            "statusReviewRequired": status.get("ReviewRequired"),
            "receipt": {"rowPresent": len(commands) == 1, "outcome": command_outcome},
            "evidence": {"testRunPresentAfterRetention": len(runs) == 1},
        }
        save(observations=observations)
        if (applied.get("Outcome") != "RetentionApplied" or applied.get("InputsRedacted") != 1 or applied.get("ReceiptsRedacted") != 1 or applied.get("EvidenceRowsPurged") != 3 or applied.get("ProtectedRows", 0) < 1 or not observations["redaction"]["inputRedacted"] or not observations["protected"]["inputPreserved"] or observations["receipt"]["outcome"] != "ReplayExpired" or observations["evidence"]["testRunPresentAfterRetention"]):
            raise ValueError("RETENTION_PROOF_FAILED")
        save(completed=True, limitation="Synthetic redaction/protection and terminal evidence cleanup are proven; scheduler execution, storage cost, and managed-release compatibility remain separate gates.")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        save(error=str(error) if str(error).isupper() else "RETENTION_PROOF_FAILED", completed=False)
        raise
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise SystemExit(1)
