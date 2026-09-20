"""Restore and reconcile a retained synthetic item after an interrupted probe."""
import argparse
import json
import subprocess
import uuid
from pathlib import Path

from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--fixture-ledger", required=True)
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-short-lease", type=int, default=1)
    parser.add_argument("--expected-short-deadline", type=int, default=2)
    parser.add_argument("--original-lease", type=int, default=120)
    parser.add_argument("--original-deadline", type=int, default=1800)
    args = parser.parse_args(argv)
    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    ledger = json.loads(Path(args.fixture_ledger).read_text(encoding="utf-8-sig"))
    origin, organization = _validate_binding(binding)
    queue = ledger["queueKey"]
    if queue not in binding.get("queueKeys", []):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    if not args.execute:
        print(json.dumps({"ready": True, "tenantCalls": False, "writes": False, "queueKey": queue}, indent=2))
        return
    output = Path(args.output)
    if output.exists():
        raise ValueError("EVIDENCE_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = {"classification": "synthetic-inconclusive-probe-recovery", "organizationId": organization, "queueKey": queue, "itemId": args.item_id, "runId": args.run_id, "completed": False, "tenantCalls": True, "policyRestored": False, "itemReconciled": False}
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    command = _cli_command()

    def save(**values):
        evidence.update(values)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def call(method, path, body=None):
        return _cli_request(command, origin, method, path, body, runner=subprocess.run)

    def api(operation, label, data=None, item=None, owned=None):
        body = {"QueueKey": queue, "RequestId": str(uuid.uuid5(uuid.UUID(args.run_id), label)), "DataJson": json.dumps(data or {}, separators=(",", ":"))}
        if item:
            body["ItemId"] = item
        if owned:
            body.update({key: owned[key] for key in ("ItemId", "AttemptId", "Generation")})
        return json.loads(call("POST", "qmcp_WQ_" + operation, body)["ResultJson"])

    try:
        who = call("GET", "WhoAmI")
        if str(who.get("OrganizationId", "")).lower() != organization.lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        rows = call("GET", "qmcp_wqdefinitions?$select=qmcp_document,versionnumber&$filter=qmcp_key eq '" + queue + "'&$top=2").get("value")
        if not isinstance(rows, list) or len(rows) != 1:
            raise ValueError("POLICY_NOT_UNIQUE")
        current = json.loads(rows[0]["qmcp_document"])
        current_is_short = current.get("LeaseSeconds") == args.expected_short_lease and current.get("DeadlineSeconds") == args.expected_short_deadline
        current_is_original = current.get("LeaseSeconds") == args.original_lease and current.get("DeadlineSeconds") == args.original_deadline
        if not current_is_short and not current_is_original:
            raise ValueError("POLICY_STATE_UNEXPECTED")
        if current_is_short:
            restored_policy = dict(current)
            restored_policy["LeaseSeconds"] = args.original_lease
            restored_policy["DeadlineSeconds"] = args.original_deadline
            restored = call("POST", "qmcp_WQ_RegisterQueue", {"QueueKey": queue, "RequestId": str(uuid.uuid5(uuid.UUID(args.run_id), "recovery-restore-policy")), "ExpectedVersion": str(rows[0]["versionnumber"]), "DataJson": json.dumps(restored_policy, separators=(",", ":"))})
            restore_outcome = json.loads(restored["ResultJson"]).get("Outcome")
        else:
            restore_outcome = "AlreadyRestored"
        verified = call("GET", "qmcp_wqdefinitions?$select=qmcp_document,versionnumber&$filter=qmcp_key eq '" + queue + "'&$top=2")["value"]
        if len(verified) != 1:
            raise ValueError("POLICY_RESTORE_READBACK_FAILED")
        verified_policy = json.loads(verified[0]["qmcp_document"])
        if verified_policy.get("LeaseSeconds") != args.original_lease or verified_policy.get("DeadlineSeconds") != args.original_deadline:
            raise ValueError("POLICY_RESTORE_READBACK_FAILED")
        save(policyRestored=True, restoreOutcome=restore_outcome)
        native = call("GET", "workqueueitems(" + args.item_id + ")?$select=workqueueitemid,statecode,statuscode")
        if native.get("statecode") != 0:
            raise ValueError("ITEM_NOT_QUEUED")
        prepared = api("PrepareAcquire", "recovery-prepare")
        if prepared.get("Outcome") != "Prepared":
            raise ValueError("RECONCILE_PREPARE_FAILED")
        claimed = call("POST", "workqueues(" + ledger["queue"] + ")/Microsoft.Dynamics.CRM.Dequeue", {})
        if str(claimed.get("workqueueitemid", "")).lower() != args.item_id.lower():
            raise ValueError("RECONCILE_NATIVE_CLAIM_FAILED")
        acquired = api("ResolveAcquire", "recovery-prepare")
        if acquired.get("Outcome") != "Acquired":
            raise ValueError("RECONCILE_RESOLVE_FAILED")
        failed = api("Fail", "recovery-fail", {"category": "Unknown", "code": "SYNTHETIC_INCONCLUSIVE_RECONCILE", "effect": "Unknown"}, owned=acquired)
        if failed.get("Outcome") != "ReviewRequired":
            raise ValueError("RECONCILE_FAIL_FAILED")
        final = call("GET", "workqueueitems(" + args.item_id + ")?$select=workqueueitemid,statecode,statuscode")
        run = api("GetTestRun", "recovery-run", item=args.run_id)
        if final.get("statecode") != 4 or not final.get("statuscode") or run.get("State") != "Inconclusive":
            raise ValueError("RECONCILE_READBACK_FAILED")
        save(itemReconciled=True, finalNativeState=final.get("statecode"), finalRunState=run.get("State"), failOutcome=failed.get("Outcome"), completed=True)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        save(error=str(error) if str(error).isupper() else "RECOVERY_FAILED", completed=False)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not evidence.get("completed") or not evidence.get("policyRestored") or not evidence.get("itemReconciled"):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise SystemExit(1)
