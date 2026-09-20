"""Prove recovery after a synthetic business write and before completion.

The proof deliberately abandons an acquired attempt after creating one
synthetic target row. It waits for the short development lease, recovers the
expired attempt into review, requests a guarded retry, reacquires the same
item, looks up the existing target by its alternate source/business key, and
completes without creating a second target. Queue policy is restored in a
finally block and no sender or mailbox flow is activated.
"""
import argparse
import datetime
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding


FLOW_IDS = (
    "a9c6e175-d6f6-50a7-860c-8fdb91da396e",
    "5391db37-d88c-57c5-839a-d66c26ffd46a",
    "d6228ad8-9758-567d-a1a3-2d5c97ab4c73",
    "6a491be2-4f32-549d-8afb-92d556e5c89b",
    "014c3583-22a5-5146-bf25-94768d689092",
    "656a2463-6fd0-5892-b382-3fc8babdc8ed",
    "a0fed279-6860-5897-912d-ccfabee2de0d",
)


def _write(path, evidence):
    Path(path).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--fixture-ledger", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    origin, organization = _validate_binding(binding)
    fixture = json.loads(Path(args.fixture_ledger).read_text(encoding="utf-8-sig"))
    queue_key = fixture["queueKey"]
    native_queue = fixture["queue"]
    team = fixture["team"]
    user = fixture["user"]
    if queue_key not in binding.get("queueKeys", []) or not queue_key.startswith("qmcp-proof-"):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    for value in (native_queue, team, user):
        uuid.UUID(str(value))
    if not args.execute:
        print(json.dumps({"ready": True, "writes": False, "queueKey": queue_key}, indent=2))
        return

    output = Path(args.output)
    if output.exists():
        raise ValueError("EVIDENCE_EXISTS")
    proof_id = str(uuid.uuid4())
    target_id = str(uuid.uuid5(uuid.UUID(proof_id), "business"))
    evidence = {
        "classification": "synthetic-post-write-recovery-before-complete",
        "organizationId": organization,
        "queueKey": queue_key,
        "proofId": proof_id,
        "targetRecordId": target_id,
        "completed": False,
        "tenantCalls": True,
        "externalDestinationsUsed": False,
        "requests": {},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(evidence, stream, indent=2)

    command = _cli_command()

    def save(**values):
        evidence.update(values)
        _write(output, evidence)

    def call(method, path, body=None):
        return _cli_request(command, origin, method, path, body, runner=subprocess.run)

    def request(operation, label, data=None, owned=None, item=None, version=None):
        request_id = str(uuid.uuid5(uuid.UUID(proof_id), label))
        evidence["requests"][label] = request_id
        body = {
            "QueueKey": queue_key,
            "RequestId": request_id,
            "DataJson": json.dumps(data or {}, separators=(",", ":")),
        }
        if owned:
            body.update({key: owned[key] for key in ("ItemId", "AttemptId", "Generation")})
        if item is not None:
            body["ItemId"] = item
        if version is not None:
            body["ExpectedVersion"] = str(version)
        save(requests=evidence["requests"])
        return json.loads(call("POST", "qmcp_WQ_" + operation, body)["ResultJson"])

    def policy():
        rows = call(
            "GET",
            "qmcp_wqdefinitions?$select=qmcp_document,versionnumber&$filter=qmcp_key eq '"
            + queue_key
            + "'&$top=2",
        ).get("value", [])
        if len(rows) != 1:
            raise ValueError("POLICY_NOT_UNIQUE")
        return json.loads(rows[0]["qmcp_document"]), rows[0]["versionnumber"]

    # Add ItemId support locally without weakening the generic request helper.
    def status_request(item_id, label):
        request_id = str(uuid.uuid5(uuid.UUID(proof_id), label))
        evidence["requests"][label] = request_id
        body = {"QueueKey": queue_key, "RequestId": request_id, "ItemId": item_id, "DataJson": "{}"}
        save(requests=evidence["requests"])
        return json.loads(call("POST", "qmcp_WQ_GetItemStatus", body)["ResultJson"])

    original_policy = None
    policy_changed = False
    acquired = None
    current_acquired = None
    try:
        who = call("GET", "WhoAmI")
        if who.get("OrganizationId", "").lower() != organization.lower() or who.get("UserId", "").lower() != user.lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        for flow_id in FLOW_IDS:
            if call("GET", "workflows(" + flow_id + ")?$select=statecode").get("statecode") != 0:
                raise ValueError("FLOWS_MUST_BE_DRAFT")

        original_policy, original_version = policy()
        short_policy = dict(original_policy)
        # Keep the first wait bounded while leaving enough time for the
        # second acquisition's source-key lookup and Complete call.
        short_policy["LeaseSeconds"] = 20
        short_policy["DeadlineSeconds"] = 120
        short_policy["Destinations"] = []
        policy_changed = True
        if request("RegisterQueue", "policy-short", short_policy, version=original_version).get("Outcome") not in ("Registered", "Updated"):
            raise ValueError("POLICY_UPDATE_FAILED")
        effective_policy, _ = policy()

        envelope = {
            "envelopeVersion": "1.0",
            "contract": "mail.v1",
            "correlationId": proof_id,
            "deduplicationKey": proof_id,
            "source": {"kind": "synthetic"},
            "payload": {
                "subject": "Synthetic post-write recovery proof",
                "senderAddress": "synthetic@example.invalid",
                "bodyText": "Synthetic recovery validation only.",
            },
        }
        enqueued = request("Enqueue", "enqueue", envelope)
        item_id = enqueued.get("ItemId")
        if enqueued.get("Outcome") != "Enqueued" or not item_id:
            raise ValueError("ENQUEUE_FAILED")
        save(itemId=item_id, effectiveLeaseSeconds=effective_policy.get("LeaseSeconds"))

        prepared = request("PrepareAcquire", "prepare", {"flowId": "post-write-recovery-proof", "runId": proof_id})
        if prepared.get("Outcome") != "Prepared":
            raise ValueError("PREPARE_FAILED")
        claimed = call("POST", "workqueues(" + native_queue + ")/Microsoft.Dynamics.CRM.Dequeue", {})
        if str(claimed.get("workqueueitemid", "")).lower() != str(item_id).lower():
            raise ValueError("NATIVE_CLAIM_FAILED")
        acquired = request("ResolveAcquire", "prepare")
        if acquired.get("Outcome") != "Acquired" or acquired.get("ItemId") != item_id:
            raise ValueError("RESOLVE_ACQUIRE_FAILED")
        save(firstAttemptId=acquired["AttemptId"], firstGeneration=acquired["Generation"], firstLeaseExpires=acquired["LeaseExpires"])

        call(
            "POST",
            "qmcp_emailrequests",
            {
                "qmcp_emailrequestid": target_id,
                "qmcp_name": "Synthetic post-write recovery proof",
                "qmcp_key": acquired["BusinessKey"],
                "qmcp_queuekey": queue_key,
                "qmcp_document": json.dumps({"sourceKey": acquired["SourceKey"], "proofId": proof_id}),
                "ownerid@odata.bind": "/teams(" + team + ")",
            },
        )
        existing = call(
            "GET",
            "qmcp_emailrequests?$select=qmcp_emailrequestid,qmcp_key&$filter=qmcp_key eq '"
            + acquired["BusinessKey"]
            + "'&$top=10",
        ).get("value", [])
        if len(existing) != 1 or existing[0].get("qmcp_emailrequestid", "").lower() != target_id.lower():
            raise ValueError("INITIAL_TARGET_NOT_UNIQUE")
        save(businessWriteCompleted=True, businessRowsBeforeRecovery=len(existing), completionOmitted=True)

        expires = datetime.datetime.fromisoformat(acquired["LeaseExpires"].replace("Z", "+00:00"))
        wait_seconds = max(0.0, (expires - datetime.datetime.now(datetime.timezone.utc)).total_seconds()) + 1.0
        if wait_seconds > 40:
            raise ValueError("LEASE_TOO_LONG_FOR_BOUNDED_PROOF")
        time.sleep(wait_seconds)
        recovered = request("RecoverExpiredAttempt", "recover", {}, acquired)
        if recovered.get("Outcome") != "ReviewRequired":
            raise ValueError("RECOVERY_NOT_REVIEWED")
        reviewed = status_request(item_id, "status-review")
        if not reviewed.get("ReviewRequired") or reviewed.get("ActiveAttempt"):
            raise ValueError("REVIEW_STATE_INVALID")
        save(recoveryOutcome=recovered, reviewedStatus=reviewed)

        retry = request(
            "RequestRetry",
            "retry",
            {"reason": "Synthetic source-key reconciliation after abandoned completion", "reconciliation": "VerifiedSafe"},
            item=item_id,
            version=reviewed["Version"],
        )
        if retry.get("Outcome") != "RetryScheduled":
            raise ValueError("RETRY_NOT_SCHEDULED")
        prepared_again = request("PrepareAcquire", "prepare-again", {"flowId": "post-write-recovery-proof", "runId": proof_id})
        if prepared_again.get("Outcome") != "Prepared":
            raise ValueError("SECOND_PREPARE_FAILED")
        claimed_again = call("POST", "workqueues(" + native_queue + ")/Microsoft.Dynamics.CRM.Dequeue", {})
        if str(claimed_again.get("workqueueitemid", "")).lower() != str(item_id).lower():
            raise ValueError("SECOND_NATIVE_CLAIM_FAILED")
        current_acquired = request("ResolveAcquire", "prepare-again")
        if current_acquired.get("Outcome") != "Acquired" or current_acquired.get("ItemId") != item_id:
            raise ValueError("SECOND_RESOLVE_FAILED")
        if current_acquired["Generation"] <= acquired["Generation"]:
            raise ValueError("GENERATION_NOT_ADVANCED")

        existing_after = call(
            "GET",
            "qmcp_emailrequests?$select=qmcp_emailrequestid,qmcp_key&$filter=qmcp_key eq '"
            + current_acquired["BusinessKey"]
            + "'&$top=10",
        ).get("value", [])
        if len(existing_after) != 1 or existing_after[0].get("qmcp_emailrequestid", "").lower() != target_id.lower():
            raise ValueError("TARGET_NOT_REUSED")
        completed = request(
            "Complete",
            "complete",
            {"table": "qmcp_emailrequest", "recordId": target_id},
            current_acquired,
        )
        if completed.get("Outcome") != "Processed":
            raise ValueError("COMPLETION_FAILED")
        final_status = status_request(item_id, "status-final")
        if final_status.get("Outcome") != "Processed" or final_status.get("Output", {}).get("recordId", "").lower() != target_id.lower():
            raise ValueError("FINAL_OUTPUT_NOT_VERIFIED")
        final_rows = call(
            "GET",
            "qmcp_emailrequests?$select=qmcp_emailrequestid,qmcp_key&$filter=qmcp_key eq '"
            + current_acquired["BusinessKey"]
            + "'&$top=10",
        ).get("value", [])
        if len(final_rows) != 1:
            raise ValueError("DUPLICATE_TARGET_CREATED")
        save(
            secondAttemptId=current_acquired["AttemptId"],
            secondGeneration=current_acquired["Generation"],
            retryOutcome=retry,
            targetRowsAfterRecovery=len(final_rows),
            completionOutcome=completed,
            finalStatus=final_status,
            completed=True,
        )
    except Exception as error:
        code = str(error) if isinstance(error, ValueError) and str(error).isupper() else "PROOF_INCONCLUSIVE"
        save(error=code, completed=False)
    finally:
        if policy_changed and original_policy is not None:
            try:
                current_policy, current_version = policy()
                restored = request("RegisterQueue", "restore-policy", original_policy, version=current_version)
                restored_policy, _ = policy()
                left = {key: value for key, value in restored_policy.items() if key != "Revision"}
                right = {key: value for key, value in original_policy.items() if key != "Revision"}
                save(policyRestoreOutcome=restored, policyRestored=left == right)
                if left != right:
                    save(completed=False, error="POLICY_RESTORE_FAILED")
            except Exception:
                save(completed=False, policyRestored=False, error="POLICY_RESTORE_FAILED")
        print(json.dumps(evidence, indent=2, sort_keys=True))

    if not evidence.get("completed") or evidence.get("policyRestored") is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(str(error))
