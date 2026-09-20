"""Prove that the installed TestCoordinator advances one synthetic run autonomously.

The proof temporarily binds and activates only ProcessOne, SweepQueue and
TestCoordinator against the allowlisted synthetic queue. It starts one known
synthetic service case, observes the independent ProcessOne/coordinator receipts,
and requires a Passed run with coordinator-owned cleanup. Intake, event wake-up,
Watchdog and EmailSender remain Draft. Every changed flow is restored in
``finally``.
"""
import argparse
import copy
import json
import re
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from bootstrap_tenant import _cli_command, _cli_request
from generate_sources import uid
from probe_tenant_metadata import _validate_binding


MODEL_ID = "a1afa5d4-7a44-4c31-9cd2-e852a78431fa"
FLOW_NAMES = ("ProcessOne", "SweepQueue", "TestCoordinator")


def validate(binding, ledger):
    origin, organization = _validate_binding(binding)
    queue = ledger.get("queueKey")
    if not isinstance(queue, str) or not queue.startswith("qmcp-proof-"):
        raise ValueError("SYNTHETIC_QUEUE_REQUIRED")
    if queue not in binding.get("queueKeys", []):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    for key in ("queue", "user"):
        try:
            uuid.UUID(ledger[key])
        except (KeyError, TypeError, ValueError):
            raise ValueError("FIXTURE_ID_INVALID")
    return origin, organization, queue


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


def repair_coordinator_cleanup(temporary):
    """Temporarily align a stale installed coordinator with the checked-in source."""
    installed = temporary["properties"]["definition"]["actions"]
    installed_advance = installed.get("Advance", {}).get("actions", {})
    if "CleanupIfPassed" in installed_advance:
        return False
    source_path = Path(__file__).resolve().parents[1] / "templates" / "flows" / "TestCoordinator.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source_advance = source["properties"]["definition"]["actions"]["Advance"]["actions"]
    installed_advance["RequestIds"]["inputs"] = copy.deepcopy(source_advance["RequestIds"]["inputs"])
    installed_advance["CleanupIfPassed"] = copy.deepcopy(source_advance["CleanupIfPassed"])
    return True


def decode_result(row):
    try:
        document = json.loads(row.get("qmcp_document", "{}"))
        result = json.loads(document.get("Result", "{}")) if isinstance(document.get("Result"), str) else document.get("Result", {})
        return document, result if isinstance(result, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}, {}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--fixture-ledger", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=210)
    parser.add_argument("--model-id", default=MODEL_ID)
    args = parser.parse_args(argv)

    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    ledger = json.loads(Path(args.fixture_ledger).read_text(encoding="utf-8-sig"))
    origin, organization, queue = validate(binding, ledger)
    uuid.UUID(args.model_id)
    if not 120 <= args.wait_seconds <= 300:
        raise ValueError("WAIT_BOUND_INVALID")
    if not args.execute:
        print(json.dumps({"ready": True, "tenantCalls": False, "writes": False, "queueKey": queue, "flows": FLOW_NAMES}, indent=2))
        return

    output = Path(args.output)
    if output.exists():
        raise ValueError("EVIDENCE_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    proof_id = str(uuid.uuid4())
    evidence = {
        "classification": "synthetic-development-coordinator-autonomy",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "organizationId": organization,
        "queueKey": queue,
        "proofId": proof_id,
        "modelId": args.model_id,
        "flows": list(FLOW_NAMES),
        "tenantCalls": True,
        "writesPerformed": False,
        "externalDestinationsUsed": False,
        "completed": False,
        "flowsRestored": False,
        "definitionRepaired": False,
    }
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    command = _cli_command()
    originals = {}
    configured = []

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

    def flow_path(name):
        return "workflows(" + uid("flow:" + name) + ")"

    def flow_parameters(clientdata):
        return json.loads(clientdata)["properties"]["definition"]["parameters"]

    def configure(name):
        evidence["writesPerformed"] = True
        path = flow_path(name)
        original = call("GET", path + "?$select=workflowid,name,statecode,statuscode,clientdata")
        if original.get("workflowid", "").lower() != uid("flow:" + name).lower() or original.get("name") != name:
            raise ValueError("WORKFLOW_ID_MISMATCH")
        if original.get("statecode") != 0:
            raise ValueError("FLOWS_MUST_BE_DRAFT")
        originals[name] = original
        temporary = json.loads(original["clientdata"])
        normalize_hosts(temporary)
        if name == "TestCoordinator":
            evidence["definitionRepaired"] = repair_coordinator_cleanup(temporary)
        parameters = temporary["properties"]["definition"]["parameters"]
        if name in ("ProcessOne", "SweepQueue"):
            parameters["qmcp_QueueKey"]["defaultValue"] = queue
            parameters["qmcp_NativeQueueId"]["defaultValue"] = ledger["queue"]
        if name == "ProcessOne":
            parameters["qmcp_PromptModelId"]["defaultValue"] = args.model_id
        call("PATCH", path, {"statecode": 0})
        call("PATCH", path, {"clientdata": json.dumps(temporary, separators=(",", ":"))})
        configured_data = call("GET", path + "?$select=statecode,clientdata")
        configured_params = flow_parameters(configured_data["clientdata"])
        if name in ("ProcessOne", "SweepQueue"):
            if configured_params["qmcp_QueueKey"]["defaultValue"] != queue or configured_params["qmcp_NativeQueueId"]["defaultValue"].lower() != ledger["queue"].lower():
                raise ValueError("WORKFLOW_BINDING_NOT_CONFIRMED")
        if name == "ProcessOne" and configured_params["qmcp_PromptModelId"]["defaultValue"].lower() != args.model_id.lower():
            raise ValueError("PROMPT_MODEL_NOT_CONFIRMED")
        call("PATCH", path, {"statecode": 1})
        active = call("GET", path + "?$select=statecode,statuscode")
        if active.get("statecode") != 1:
            raise ValueError("WORKFLOW_NOT_ACTIVE")
        configured.append(name)

    def restore():
        errors = []
        for name in reversed(tuple(originals)):
            try:
                path = flow_path(name)
                original = originals[name]
                call("PATCH", path, {"statecode": 0})
                call("PATCH", path, {"clientdata": original["clientdata"]})
                restored = call("GET", path + "?$select=statecode,clientdata")
                if restored.get("statecode") != 0 or restored.get("clientdata") != original.get("clientdata"):
                    raise ValueError("FLOW_RESTORE_MISMATCH")
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                errors.append(str(error) if str(error).isupper() else "FLOW_RESTORE_FAILED")
        save(flowsRestored=not errors, finalFlowStates={name: "Draft" for name in originals}, restoreErrors=errors)

    try:
        who = call("GET", "WhoAmI")
        if str(who.get("OrganizationId", "")).lower() != organization.lower() or str(who.get("UserId", "")).lower() != ledger["user"].lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        active_items = call("GET", "workqueueitems?$select=workqueueitemid,statecode,statuscode&$filter=_workqueueid_value eq " + ledger["queue"] + " and (statecode eq 0 or statecode eq 1)&$top=2").get("value", [])
        if active_items:
            raise ValueError("SYNTHETIC_QUEUE_NOT_IDLE")
        for name in FLOW_NAMES:
            configure(name)
        started = api("StartTestRun", "start", {"cases": [{
            "Id": "coordinator-autonomy",
            "Input": {
                "envelopeVersion": "1.0", "contract": "mail.v1", "correlationId": proof_id,
                "deduplicationKey": proof_id, "source": {"kind": "synthetic"},
                "payload": {"subject": "Printer is offline", "senderAddress": "alex@example.invalid", "bodyText": "Please restore the printer in the west office. It stopped working this morning."},
            },
            "Expected": {"contact": "alex@example.invalid", "category": "service"},
            "ExpectedOutcome": "Processed", "ExpectedAttemptCount": 1,
        }]})
        run_id = started["RunId"]
        save(runId=run_id, startOutcome=started.get("Outcome"), activatedFlows=configured)
        deadline = time.monotonic() + args.wait_seconds
        observed = None
        while time.monotonic() < deadline:
            run = api("GetTestRun", "get-run-" + str(int(time.monotonic())), item=run_id)
            commands = call("GET", "qmcp_wqcommands?$select=qmcp_document,createdon&$filter=qmcp_queuekey eq '" + queue + "'&$top=100").get("value", [])
            receipts = []
            for row in commands:
                document, result = decode_result(row)
                if document.get("Operation") in ("AdvanceTestRun", "CleanupTestRun") and result.get("Id") == run_id:
                    receipts.append({"operation": document.get("Operation"), "created": row.get("createdon"), "outcome": result.get("State", result.get("Outcome"))})
            terminal = run.get("State") in {"Passed", "Failed", "Inconclusive", "Cancelled"}
            cleanup_complete = run.get("State") == "Passed" and bool(run.get("Results")) and all(
                result.get("Cleanup") == "Completed" for result in run.get("Results", [])
            )
            if terminal and (run.get("State") != "Passed" or cleanup_complete):
                observed = {"run": {"State": run.get("State"), "Results": run.get("Results")}, "receipts": receipts}
                break
            time.sleep(5)
        if observed is None:
            raise ValueError("COORDINATOR_CLEANUP_NOT_OBSERVED")
        save(observation=observed, completed=observed["run"]["State"] == "Passed", limitation="Synthetic autonomous ProcessOne/SweepQueue/TestCoordinator proof only; mailbox intake, event wake-up, EmailSender, separate identity and managed release remain separate gates.")
        if not evidence["completed"]:
            raise ValueError("COORDINATOR_PROOF_FAILED")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        save(error=str(error) if re.fullmatch(r"[A-Z_]+", str(error)) else "COORDINATOR_PROOF_FAILED", completed=False)
        raise
    finally:
        try:
            restore()
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            save(restoreErrors=[str(error) if str(error).isupper() else "FLOW_RESTORE_FAILED"], flowsRestored=False, completed=False)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not evidence.get("completed") or not evidence.get("flowsRestored"):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise SystemExit(1)
