"""Run the reviewed synthetic reference cases through the installed worker.

The probe temporarily binds and activates only ProcessOne, SweepQueue and
TestCoordinator against an allowlisted synthetic queue.  It delegates the
independent native/business assertions to ``prove_reference_quality`` and
cleans successful test-owned output only after those assertions pass.  Every
changed flow is restored to its exact original clientdata and Draft state.
"""
import argparse
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
from prove_coordinator_autonomy import normalize_hosts, repair_coordinator_cleanup
from prove_reference_quality import load_cases, observe


FLOW_NAMES = ("ProcessOne", "SweepQueue", "TestCoordinator")


def validate(binding, ledger, cases):
    origin, organization = _validate_binding(binding)
    queue = ledger.get("queueKey")
    if not isinstance(queue, str) or not queue.startswith("qmcp-proof-"):
        raise ValueError("SYNTHETIC_QUEUE_REQUIRED")
    if queue not in binding.get("queueKeys", []):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    try:
        uuid.UUID(ledger["queue"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("NATIVE_QUEUE_ID_REQUIRED")
    if not isinstance(cases, list) or not cases or len(cases) > 20:
        raise ValueError("FIXTURE_CASES_INVALID")
    return origin, organization, queue


def flow_path(name):
    return "workflows(" + uid("flow:" + name) + ")"


def flow_parameters(clientdata):
    return json.loads(clientdata)["properties"]["definition"]["parameters"]


def suspend_automatic_cleanup(temporary):
    actions = temporary["properties"]["definition"]["actions"]
    advance = actions.get("Advance", {}).get("actions", {})
    return advance.pop("CleanupIfPassed", None) is not None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--fixture-ledger", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=300)
    parser.add_argument("--model-id", required=True)
    args = parser.parse_args(argv)

    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    ledger = json.loads(Path(args.fixture_ledger).read_text(encoding="utf-8-sig"))
    cases = load_cases(args.cases)
    origin, organization, queue = validate(binding, ledger, cases)
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
    manifest = json.loads(Path(args.cases).read_text(encoding="utf-8-sig"))
    evidence = {
        "classification": "live-synthetic-reference-quality-autonomous",
        "organizationId": organization,
        "queueKey": queue,
        "proofId": proof_id,
        "modelId": args.model_id,
        "promptVersion": manifest.get("promptVersion", "mail-extraction-v1.1"),
        "caseCount": len(cases),
        "flows": list(FLOW_NAMES),
        "tenantCalls": True,
        "writesPerformed": False,
        "externalDestinationsUsed": False,
        "complete": False,
        "flowsRestored": False,
    }
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    command = _cli_command()
    originals = {}

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
            evidence["automaticCleanupSuspended"] = suspend_automatic_cleanup(temporary)
        parameters = temporary["properties"]["definition"]["parameters"]
        if name in ("ProcessOne", "SweepQueue"):
            parameters["qmcp_QueueKey"]["defaultValue"] = queue
            parameters["qmcp_NativeQueueId"]["defaultValue"] = ledger["queue"]
        if name == "ProcessOne":
            parameters["qmcp_PromptModelId"]["defaultValue"] = args.model_id
        call("PATCH", path, {"statecode": 0})
        call("PATCH", path, {"clientdata": json.dumps(temporary, separators=(",", ":"))})
        confirmed = call("GET", path + "?$select=statecode,clientdata")
        confirmed_parameters = flow_parameters(confirmed["clientdata"])
        if name in ("ProcessOne", "SweepQueue") and (
            confirmed_parameters["qmcp_QueueKey"]["defaultValue"] != queue
            or confirmed_parameters["qmcp_NativeQueueId"]["defaultValue"].lower() != ledger["queue"].lower()
        ):
            raise ValueError("WORKFLOW_BINDING_NOT_CONFIRMED")
        if name == "ProcessOne" and confirmed_parameters["qmcp_PromptModelId"]["defaultValue"].lower() != args.model_id.lower():
            raise ValueError("PROMPT_MODEL_NOT_CONFIRMED")
        call("PATCH", path, {"statecode": 1})
        active = call("GET", path + "?$select=statecode,statuscode")
        if active.get("statecode") != 1:
            raise ValueError("WORKFLOW_NOT_ACTIVE")

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
        if str(who.get("OrganizationId", "")).lower() != organization.lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        active_items = call(
            "GET",
            "workqueueitems?$select=workqueueitemid,statecode,statuscode&$filter=_workqueueid_value eq "
            + ledger["queue"]
            + " and (statecode eq 0 or statecode eq 1)&$top=2",
        ).get("value", [])
        if active_items:
            raise ValueError("SYNTHETIC_QUEUE_NOT_IDLE")
        for name in FLOW_NAMES:
            configure(name)
        started = api("StartTestRun", "start", {"cases": cases})
        run_id = started["RunId"]
        save(runId=run_id, startOutcome=started.get("Outcome"), activatedFlows=list(originals))
        deadline = time.monotonic() + args.wait_seconds
        terminal_state = None
        while time.monotonic() < deadline:
            run = api("GetTestRun", "observe-" + str(int(time.monotonic())), item=run_id)
            terminal_state = run.get("State")
            save(lastRunState=terminal_state)
            if terminal_state in {"Passed", "Failed", "Inconclusive", "Cancelled"}:
                break
            time.sleep(5)
        if terminal_state not in {"Passed", "Failed", "Inconclusive", "Cancelled"}:
            raise ValueError("REFERENCE_RUN_NOT_TERMINAL")

        observed = observe(call, evidence, cases, run_id, queue, ledger["queue"])
        if not observed.get("complete"):
            raise ValueError("REFERENCE_QUALITY_PROOF_FAILED")
        cleanup = api("CleanupTestRun", "cleanup", item=run_id)
        evidence["cleanup"] = {"outcome": cleanup.get("Outcome"), "state": cleanup.get("State"), "resultCount": len(cleanup.get("Results", [])) if isinstance(cleanup.get("Results"), list) else None}
        remaining = call(
            "GET",
            "qmcp_emailrequests?$select=qmcp_emailrequestid,qmcp_testrun&$filter=qmcp_testrun eq '" + run_id + "'&$top=20",
        ).get("value")
        if not isinstance(remaining, list):
            raise ValueError("CLEANUP_QUERY_INVALID")
        evidence["cleanup"]["remainingTestRunRecords"] = len(remaining)
        if cleanup.get("Outcome") != "Passed" or remaining:
            raise ValueError("CLEANUP_NOT_CONFIRMED")
        evidence["complete"] = True
        evidence["limitation"] = "Bounded six-case synthetic installed worker proof; mailbox intake, event wake-up, notification delivery, restricted identity and managed release remain separate gates."
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        save(error=str(error) if re.fullmatch(r"[A-Z_]+", str(error)) else "REFERENCE_QUALITY_PROOF_FAILED", complete=False)
        raise
    finally:
        try:
            restore()
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            save(restoreErrors=[str(error) if str(error).isupper() else "FLOW_RESTORE_FAILED"], flowsRestored=False, complete=False)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not evidence.get("complete") or not evidence.get("flowsRestored"):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise SystemExit(1)
