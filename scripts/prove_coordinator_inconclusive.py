"""Prove an installed coordinator preserves an expired test as Inconclusive.

The probe uses only the isolated synthetic development queue.  It temporarily
shortens that queue's observation deadline, activates TestCoordinator alone,
waits for the scheduled coordinator pass, independently checks that the test
item stayed queued without attempts or business output, then reconciles the
synthetic item to review and restores the original queue policy and Draft flow.
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


FLOW_NAME = "TestCoordinator"


def policies_equal(left, right):
    return {k: v for k, v in left.items() if k != "Revision"} == {k: v for k, v in right.items() if k != "Revision"}


def validate(binding, ledger, lease_seconds, deadline_seconds, wait_seconds):
    origin, organization = _validate_binding(binding)
    queue = ledger.get("queueKey")
    if not isinstance(queue, str) or not queue.startswith("qmcp-proof-") or queue not in binding.get("queueKeys", []):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    for key in ("queue", "user"):
        try:
            uuid.UUID(ledger[key])
        except (KeyError, TypeError, ValueError):
            raise ValueError("FIXTURE_ID_INVALID")
    if not 1 <= lease_seconds <= 5 or not lease_seconds < deadline_seconds <= 10:
        raise ValueError("DEADLINE_BOUND_INVALID")
    if not 120 <= wait_seconds <= 300:
        raise ValueError("WAIT_BOUND_INVALID")
    return origin, organization, queue


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--fixture-ledger", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--lease-seconds", type=int, default=1)
    parser.add_argument("--deadline-seconds", type=int, default=2)
    parser.add_argument("--wait-seconds", type=int, default=210)
    args = parser.parse_args(argv)

    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    ledger = json.loads(Path(args.fixture_ledger).read_text(encoding="utf-8-sig"))
    origin, organization, queue = validate(binding, ledger, args.lease_seconds, args.deadline_seconds, args.wait_seconds)
    if not args.execute:
        print(json.dumps({"ready": True, "tenantCalls": False, "writes": False, "queueKey": queue, "flow": FLOW_NAME}, indent=2))
        return

    output = Path(args.output)
    if output.exists():
        raise ValueError("EVIDENCE_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    proof_id = str(uuid.uuid4())
    evidence = {
        "classification": "live-synthetic-coordinator-inconclusive",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "organizationId": organization,
        "queueKey": queue,
        "proofId": proof_id,
        "flow": FLOW_NAME,
        "deadlineSeconds": args.deadline_seconds,
        "leaseSeconds": args.lease_seconds,
        "tenantCalls": True,
        "writesPerformed": False,
        "externalDestinationsUsed": False,
        "completed": False,
        "flowRestored": False,
        "policyRestored": False,
    }
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    command = _cli_command()
    original_policy = None
    policy_version = None
    policy_changed = False
    flow_original = None
    run_id = None
    item_id = None
    acquired = None
    terminal = False

    def save(**values):
        evidence.update(values)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def call(method, path, body=None):
        return _cli_request(command, origin, method, path, body, runner=subprocess.run)

    def api(operation, label, data=None, item=None, owned=None):
        body = {
            "QueueKey": queue,
            "RequestId": str(uuid.uuid5(uuid.UUID(proof_id), label)),
            "DataJson": json.dumps(data or {}, separators=(",", ":")),
        }
        if item:
            body["ItemId"] = item
        if owned:
            body.update({key: owned[key] for key in ("ItemId", "AttemptId", "Generation")})
        response = call("POST", "qmcp_WQ_" + operation, body)
        return json.loads(response["ResultJson"])

    def policy():
        rows = call("GET", "qmcp_wqdefinitions?$select=qmcp_document,versionnumber&$filter=qmcp_key eq '" + queue + "'&$top=2").get("value")
        if not isinstance(rows, list) or len(rows) != 1:
            raise ValueError("POLICY_NOT_UNIQUE")
        return json.loads(rows[0]["qmcp_document"]), rows[0]["versionnumber"]

    def flow_path():
        return "workflows(" + uid("flow:" + FLOW_NAME) + ")"

    def reconcile_item():
        nonlocal acquired
        if not item_id:
            return
        native = call("GET", "workqueueitems(" + item_id + ")?$select=workqueueitemid,statecode,statuscode")
        if native.get("statecode") != 0:
            return
        prepared = api("PrepareAcquire", "reconcile-prepare")
        if prepared.get("Outcome") != "Prepared":
            raise ValueError("RECONCILE_PREPARE_FAILED")
        claimed = call("POST", "workqueues(" + ledger["queue"] + ")/Microsoft.Dynamics.CRM.Dequeue", {})
        if str(claimed.get("workqueueitemid", "")).lower() != item_id.lower():
            raise ValueError("RECONCILE_NATIVE_CLAIM_FAILED")
        acquired = api("ResolveAcquire", "reconcile-prepare")
        if acquired.get("Outcome") != "Acquired":
            raise ValueError("RECONCILE_RESOLVE_FAILED")
        failed = api("Fail", "reconcile-fail", {"category": "Technical", "code": "SYNTHETIC_INCONCLUSIVE_RECONCILE", "effect": "None"}, owned=acquired)
        if failed.get("Outcome") != "ReviewRequired":
            raise ValueError("RECONCILE_FAIL_FAILED")
        save(reconciliationOutcome=failed.get("Outcome"), reconciliationCompleted=True)

    try:
        who = call("GET", "WhoAmI")
        if str(who.get("OrganizationId", "")).lower() != organization.lower() or str(who.get("UserId", "")).lower() != str(ledger["user"]).lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        active_items = call("GET", "workqueueitems?$select=workqueueitemid,statecode,statuscode&$filter=_workqueueid_value eq " + ledger["queue"] + " and (statecode eq 0 or statecode eq 1)&$top=2").get("value", [])
        if active_items:
            raise ValueError("SYNTHETIC_QUEUE_NOT_IDLE")
        original_policy, policy_version = policy()
        if original_policy.get("NativeQueueId", "").lower() != ledger["queue"].lower() or not original_policy.get("Enabled"):
            raise ValueError("POLICY_NOT_READY")
        if original_policy.get("DeadlineSeconds") == args.deadline_seconds and original_policy.get("LeaseSeconds") == args.lease_seconds:
            raise ValueError("DEADLINE_ALREADY_SHORT")
        flow_original = call("GET", flow_path() + "?$select=workflowid,name,statecode,statuscode,clientdata")
        if flow_original.get("name") != FLOW_NAME or flow_original.get("statecode") != 0:
            raise ValueError("FLOW_NOT_DRAFT")
        save(originalDeadlineSeconds=original_policy.get("DeadlineSeconds"), originalPolicyRevision=original_policy.get("Revision"), originalFlowState="Draft")
        shortened = dict(original_policy)
        shortened["LeaseSeconds"] = args.lease_seconds
        shortened["DeadlineSeconds"] = args.deadline_seconds
        register = call("POST", "qmcp_WQ_RegisterQueue", {"QueueKey": queue, "RequestId": str(uuid.uuid5(uuid.UUID(proof_id), "shorten-policy")), "ExpectedVersion": str(policy_version), "DataJson": json.dumps(shortened, separators=(",", ":"))})
        policy_changed = True
        save(policyChangeOutcome=json.loads(register["ResultJson"]).get("Outcome"), shortenedLeaseSeconds=args.lease_seconds, shortenedDeadlineSeconds=args.deadline_seconds)
        bound = policy()[0]
        if bound.get("LeaseSeconds") != args.lease_seconds or bound.get("DeadlineSeconds") != args.deadline_seconds:
            raise ValueError("DEADLINE_BINDING_NOT_CONFIRMED")
        call("PATCH", flow_path(), {"statecode": 1})
        active_flow = call("GET", flow_path() + "?$select=statecode,statuscode")
        if active_flow.get("statecode") != 1:
            raise ValueError("FLOW_NOT_ACTIVE")
        save(flowActivated=True)
        started = api("StartTestRun", "start", {"cases": [{
            "Id": "coordinator-inconclusive",
            "Input": {
                "envelopeVersion": "1.0", "contract": "mail.v1", "correlationId": proof_id,
                "deduplicationKey": proof_id, "source": {"kind": "synthetic"},
                "payload": {"subject": "Synthetic inconclusive deadline", "senderAddress": "deadline@example.invalid", "bodyText": "Please retain this bounded synthetic deadline case."},
            },
            "Expected": {}, "ExpectedOutcome": "Exception", "ExpectedAttemptCount": 0,
        }]})
        run_id = started["RunId"]
        run = api("GetTestRun", "run-after-start", item=run_id)
        if not run.get("Results") or not run["Results"][0].get("ItemId"):
            raise ValueError("TEST_ITEM_NOT_CREATED")
        item_id = run["Results"][0]["ItemId"]
        save(runId=run_id, itemId=item_id, startOutcome=started.get("Outcome"))
        deadline = time.monotonic() + args.wait_seconds
        while time.monotonic() < deadline:
            run = api("GetTestRun", "observe-" + str(int(time.monotonic())), item=run_id)
            if run.get("State") in {"Passed", "Failed", "Inconclusive", "Cancelled"}:
                terminal = True
                break
            time.sleep(5)
        if not terminal:
            raise ValueError("INCONCLUSIVE_RUN_NOT_TERMINAL")
        native = call("GET", "workqueueitems(" + item_id + ")?$select=workqueueitemid,statecode,statuscode,input")
        attempts = call("GET", "qmcp_wqattempts?$select=qmcp_wqattemptid&$filter=qmcp_itemid eq '" + item_id + "'").get("value")
        business = call("GET", "qmcp_emailrequests?$select=qmcp_emailrequestid,qmcp_testrun&$filter=qmcp_testrun eq '" + run_id + "'&$top=20").get("value")
        commands = call("GET", "qmcp_wqcommands?$select=qmcp_document&$filter=qmcp_queuekey eq '" + queue + "'&$top=100").get("value")
        cleanup_receipts = []
        for row in commands if isinstance(commands, list) else []:
            try:
                document = json.loads(row.get("qmcp_document", "{}"))
            except (TypeError, ValueError):
                continue
            if document.get("Operation") == "CleanupTestRun" and document.get("ItemId") == run_id:
                cleanup_receipts.append(document)
        if run.get("State") != "Inconclusive" or not isinstance(run.get("Results"), list) or not run["Results"] or run["Results"][0].get("State") != "Inconclusive" or native.get("statecode") != 0 or native.get("statuscode") != 0 or attempts or business or cleanup_receipts:
            raise ValueError("INCONCLUSIVE_ASSERTION_FAILED")
        save(runState=run.get("State"), resultState=run["Results"][0].get("State"), nativeState=native.get("statecode"), nativeStatus=native.get("statuscode"), attemptCount=len(attempts or []), businessRecordCount=len(business or []), cleanupReceiptCount=len(cleanup_receipts), evidenceRetained=True)
        reconcile_item()
        evidence["completed"] = True
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        save(error=str(error) if re.fullmatch(r"[A-Z_]+", str(error)) else "INCONCLUSIVE_PROOF_FAILED", completed=False)
    finally:
        if run_id and not terminal:
            try:
                api("CancelTestRun", "cleanup-cancel", item=run_id)
            except Exception:
                save(cleanupCancel="failed")
        if flow_original is not None:
            try:
                call("PATCH", flow_path(), {"statecode": 0})
                restored_flow = call("GET", flow_path() + "?$select=statecode,clientdata")
                if restored_flow.get("statecode") != 0 or restored_flow.get("clientdata") != flow_original.get("clientdata"):
                    raise ValueError("FLOW_RESTORE_MISMATCH")
                save(flowRestored=True)
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                save(flowRestoreError=str(error) if str(error).isupper() else "FLOW_RESTORE_FAILED", flowRestored=False, completed=False)
        if policy_changed and original_policy is not None:
            try:
                current, version = policy()
                if not policies_equal(current, original_policy) and not policies_equal(current, {**original_policy, "DeadlineSeconds": args.deadline_seconds}):
                    raise ValueError("CONCURRENT_POLICY_CHANGE")
                restored = call("POST", "qmcp_WQ_RegisterQueue", {"QueueKey": queue, "RequestId": str(uuid.uuid5(uuid.UUID(proof_id), "restore-policy")), "ExpectedVersion": str(version), "DataJson": json.dumps(original_policy, separators=(",", ":"))})
                restored_policy, _ = policy()
                if not policies_equal(restored_policy, original_policy):
                    raise ValueError("POLICY_RESTORE_FAILED")
                save(policyRestored=True, restoreOutcome=json.loads(restored["ResultJson"]).get("Outcome"))
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                save(policyRestoreError=str(error) if str(error).isupper() else "POLICY_RESTORE_FAILED", policyRestored=False, completed=False)
        save(flowRestored=evidence.get("flowRestored", False), policyRestored=evidence.get("policyRestored", False))
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not evidence.get("completed") or not evidence.get("flowRestored") or not evidence.get("policyRestored"):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise SystemExit(1)
