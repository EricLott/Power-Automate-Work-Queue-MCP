"""Opt-in synthetic proof of acquisition identity and replay safety.

The default mode validates inputs only.  The execution path requires an idle
allowlisted synthetic queue, creates two items, and leaves the second queued.
It never changes queue policy or sends notifications.
"""
import argparse
import concurrent.futures
import json
import subprocess
import uuid
from pathlib import Path

from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding

FLOW_IDS = (
    "a9c6e175-d6f6-50a7-860c-8fdb91da396e", "5391db37-d88c-57c5-839a-d66c26ffd46a",
    "d6228ad8-9758-567d-a1a3-2d5c97ab4c73", "6a491be2-4f32-549d-8afb-92d556e5c89b",
    "014c3583-22a5-5146-bf25-94768d689092", "656a2463-6fd0-5892-b382-3fc8babdc8ed",
    "a0fed279-6860-5897-912d-ccfabee2de0d",
)
EXPECTED_FAULTS = {"ACQUIRE_BUSY", "REQUEST_CONFLICT"}


def validate(binding, ledger):
    origin, organization = _validate_binding(binding)
    queue = ledger.get("queueKey")
    if not isinstance(queue, str) or not queue.startswith("qmcp-proof-") or queue not in binding.get("queueKeys", []):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    try:
        uuid.UUID(ledger["queue"])
        uuid.UUID(ledger["team"])
        uuid.UUID(ledger["user"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("NATIVE_QUEUE_ID_REQUIRED")
    return origin, organization, queue, ledger["queue"]


def fault_from_stdout(stdout):
    """Extract only an exact known framework fault from CLI JSON."""
    try:
        outer = json.loads(stdout or "")
        error = outer.get("error", {}) if isinstance(outer, dict) else {}
        message = error.get("message")
        if message in EXPECTED_FAULTS:
            return message
        nested = json.loads(message) if isinstance(message, str) else {}
        nested_error = nested.get("error", nested) if isinstance(nested, dict) else {}
        value = nested_error.get("message") if isinstance(nested_error, dict) else None
        return value if value in EXPECTED_FAULTS else None
    except (TypeError, ValueError, AttributeError):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--fixture-ledger", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    ledger = json.loads(Path(args.fixture_ledger).read_text(encoding="utf-8-sig"))
    origin, organization, queue, native_queue = validate(binding, ledger)
    if not args.run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in args.run_id):
        raise ValueError("RUN_ID_INVALID")
    output = Path(args.output_dir)
    if not args.execute:
        print(json.dumps({"ready": True, "writes": False, "tenantCalls": False, "queueKey": queue, "runId": args.run_id}, indent=2))
        return
    if output.exists():
        raise ValueError("EVIDENCE_RUN_EXISTS")
    output.mkdir(parents=True, exist_ok=False)
    evidence = {"classification": "synthetic-acquisition-identity", "organizationId": organization, "queueKey": queue, "runId": args.run_id, "completed": False, "tenantCalls": True}
    evidence_file = output / "evidence.json"

    def save(**values):
        evidence.update(values)
        evidence_file.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")

    save()
    command = _cli_command()

    def call(method, relative, body=None, state=None):
        def runner(*run_args, **run_kwargs):
            result = subprocess.run(*run_args, **run_kwargs)
            if state is not None and result.returncode:
                state["fault"] = fault_from_stdout(result.stdout)
            return result
        return _cli_request(command, origin, method, relative, body, runner=runner)

    def rid(label):
        return str(uuid.uuid5(uuid.UUID(ledger["queue"]), args.run_id + "|" + label))

    def api(name, request_id, data=None, owned=None, label=None, state=None, persist=True):
        body = {"QueueKey": queue, "RequestId": request_id, "DataJson": json.dumps(data or {}, separators=(",", ":"))}
        if owned:
            body.update({key: owned[key] for key in ("ItemId", "AttemptId", "Generation")})
        if persist:
            save(requests={**evidence.get("requests", {}), label or name: request_id})
        return json.loads(call("POST", "qmcp_WQ_" + name, body, state=state)["ResultJson"])

    def native_rows():
        path = "workqueueitems?$select=workqueueitemid,uniqueidbyqueue,statecode,statuscode&$filter=_workqueueid_value eq " + native_queue + " and (statecode eq 0 or statecode eq 1)&$top=10"
        response = call("GET", path)
        rows = response.get("value")
        if not isinstance(rows, list) or response.get("@odata.nextLink"): raise ValueError("NATIVE_PAGE_INVALID")
        return rows

    try:
        who = call("GET", "WhoAmI")
        if str(who.get("OrganizationId", "")).lower() != organization.lower() or str(who.get("UserId", "")).lower() != ledger["user"].lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        for flow in FLOW_IDS:
            if call("GET", "workflows(" + flow + ")?$select=statecode").get("statecode") != 0:
                raise ValueError("FLOWS_MUST_BE_DRAFT")
        policy_rows = call("GET", "qmcp_wqdefinitions?$select=qmcp_document&$filter=qmcp_key eq '" + queue + "'&$top=2").get("value")
        if not isinstance(policy_rows, list) or len(policy_rows) != 1: raise ValueError("POLICY_NOT_UNIQUE")
        policy = json.loads(policy_rows[0]["qmcp_document"])
        if not policy.get("Enabled") or policy.get("NativeQueueId", "").lower() != native_queue.lower(): raise ValueError("POLICY_BINDING_INVALID")
        if native_rows():
            raise ValueError("QUEUE_NOT_IDLE")
        enqueue_ids = [rid("enqueue-a"), rid("enqueue-b")]
        save(requests={"EnqueueA": enqueue_ids[0], "EnqueueB": enqueue_ids[1]})
        items = []
        for index, request_id in enumerate(enqueue_ids):
            payload = {"envelopeVersion": "1.0", "contract": "mail.v1", "correlationId": args.run_id + "-" + str(index), "deduplicationKey": args.run_id + "-identity-" + str(index), "source": {"kind": "synthetic"}, "payload": {"subject": "Synthetic acquisition identity proof", "senderAddress": "synthetic@example.invalid", "bodyText": "Please process this synthetic identity proof."}}
            result = api("Enqueue", request_id, payload, label="Enqueue" + ("A" if index == 0 else "B"))
            items.append(result["ItemId"])
        save(itemIds=items)

        before_prepare = native_rows()
        if {r["workqueueitemid"] for r in before_prepare} != set(items) or any(r["statecode"] != 0 for r in before_prepare): raise ValueError("SEED_STATE_INVALID")
        save(nativeBeforePrepare=before_prepare)
        prepare_ids = [rid("prepare-a"), rid("prepare-b")]
        save(requests={**evidence["requests"], "PrepareA": prepare_ids[0], "PrepareB": prepare_ids[1]})
        def prepare(request_id, label):
            state = {}
            try:
                result = api("PrepareAcquire", request_id, {"flowId": "identity-proof", "runId": args.run_id}, label=label, state=state, persist=False)
                return {"outcome": result, "fault": None, "initial": True}
            except ValueError:
                return {"outcome": None, "fault": state.get("fault") or "DATAVERSE_CLI_FAILED", "initial": True}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(lambda pair: prepare(*pair), ((prepare_ids[0], "PrepareA"), (prepare_ids[1], "PrepareB"))))
        save(initialPrepareResponses=json.loads(json.dumps([first, second])))
        # A transport failure is recorded as inconclusive, then the same ID may
        # be retried once; only the exact eventual ACQUIRE_BUSY is accepted.
        if first["fault"] == "DATAVERSE_CLI_FAILED" and not second["fault"]:
            first_retry = prepare(prepare_ids[0], "PrepareARetry"); first["retry"] = first_retry
        if second["fault"] == "DATAVERSE_CLI_FAILED" and not first["fault"]:
            second_retry = prepare(prepare_ids[1], "PrepareBRetry"); second["retry"] = second_retry
        responses = [first, second]
        save(prepareResponses=responses)
        def effective_outcome(response):
            return response.get("outcome") or (response.get("retry") or {}).get("outcome") or {}
        prepared = [r for r in responses if effective_outcome(r).get("Outcome") == "Prepared"]
        busy = [r for r in responses if r.get("fault") == "ACQUIRE_BUSY" or (r.get("retry") or {}).get("fault") == "ACQUIRE_BUSY"]
        if len(prepared) != 1 or len(busy) != 1:
            raise ValueError("DISTINCT_PREPARE_ASSERTION_FAILED")
        winner_index = 0 if responses[0] in prepared else 1
        winner = prepare_ids[winner_index]
        loser = prepare_ids[1 - winner_index]
        if effective_outcome(prepared[0]).get("NativeQueueId", "").lower() != native_queue.lower(): raise ValueError("PREPARE_QUEUE_MISMATCH")
        save(prepareResponses=responses, winnerRequestId=winner, loserRequestId=loser)

        def replay():
            return api("PrepareAcquire", winner, {"flowId": "identity-proof", "runId": args.run_id}, label="PrepareReplay", persist=False)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            replayed = list(pool.map(lambda _: replay(), range(2)))
        save(prepareReplay=replayed)
        winner_result = effective_outcome(prepared[0])
        if any(json.dumps(result, sort_keys=True, separators=(",", ":")) != json.dumps(winner_result, sort_keys=True, separators=(",", ":")) for result in replayed):
            raise ValueError("PREPARE_REPLAY_MISMATCH")
        changed_state = {}
        try:
            api("PrepareAcquire", winner, {"flowId": "changed-identity", "runId": args.run_id}, label="PrepareChanged", state=changed_state)
        except ValueError:
            # `_cli_request` sanitizes the response; retrying is forbidden for
            # this assertion because a changed fingerprint must be rejected.
            changed_fault = changed_state.get("fault") or "DATAVERSE_CLI_FAILED"
        else:
            changed_fault = "UNEXPECTED_SUCCESS"
        if changed_fault != "REQUEST_CONFLICT":
            raise ValueError("PREPARE_CHANGED_ARGUMENT_NOT_REJECTED")
        after_prepare = native_rows()
        if sorted(after_prepare, key=lambda r:r["workqueueitemid"]) != sorted(before_prepare, key=lambda r:r["workqueueitemid"]): raise ValueError("PREPARE_CHANGED_NATIVE_ITEMS")
        save(changedArguments=changed_fault, nativeAfterPrepare=after_prepare)

        # The native response is deliberately ignored. State is established by
        # independent reads of both known synthetic items.
        call("POST", "workqueues(" + native_queue + ")/Microsoft.Dynamics.CRM.Dequeue", {})
        after_dequeue = native_rows()
        by_id = {row.get("workqueueitemid", "").lower(): row for row in (after_dequeue or [])}
        expected_ids = {value.lower() for value in items}
        if set(by_id) != expected_ids or sorted((row.get("statecode"), row.get("statuscode")) for row in by_id.values()) != [(0, 0), (1, 1)]:
            raise ValueError("NATIVE_CLAIM_ASSERTION_FAILED")
        processing_id = next(key for key, row in by_id.items() if row.get("statecode") == 1)
        queued_id = next(key for key, row in by_id.items() if row.get("statecode") == 0)
        resolved = api("ResolveAcquire", winner, label="ResolveAcquire")
        resolved_again = api("ResolveAcquire", winner, label="ResolveAcquireReplay")
        if resolved != resolved_again or resolved.get("Outcome") != "Acquired" or resolved.get("ItemId", "").lower() != processing_id:
            raise ValueError("RESOLVE_REPLAY_ASSERTION_FAILED")
        save(acquisition=resolved, nativeAfterDequeue=after_dequeue, processingItemId=processing_id, queuedItemId=queued_id)
        attempts = {}
        for item_id in items:
            values = call("GET", "qmcp_wqattempts?$select=qmcp_wqattemptid&$filter=qmcp_itemid eq '" + item_id + "'").get("value")
            if not isinstance(values, list):
                raise ValueError("ATTEMPT_QUERY_INVALID")
            attempts[item_id.lower()] = values
        if len(attempts.get(processing_id, [])) != 1 or attempts.get(queued_id):
            raise ValueError("ATTEMPT_COUNT_ASSERTION_FAILED")
        record_id = str(uuid.uuid5(uuid.UUID(ledger["queue"]), args.run_id + "|identity-output"))
        save(recordId=record_id)
        call("POST", "qmcp_emailrequests", {"qmcp_emailrequestid": record_id, "qmcp_name": "Synthetic acquisition identity proof", "qmcp_key": resolved["BusinessKey"], "qmcp_queuekey": queue, "qmcp_document": json.dumps({"sourceKey": resolved["SourceKey"]}), "ownerid@odata.bind": "/teams(" + ledger["team"] + ")"})
        business = call("GET", "qmcp_emailrequests(" + record_id + ")?$select=qmcp_emailrequestid,qmcp_key,qmcp_queuekey,qmcp_document")
        if str(business.get("qmcp_emailrequestid", "")).lower() != record_id.lower() or business.get("qmcp_key") != resolved.get("BusinessKey") or business.get("qmcp_queuekey") != queue:
            raise ValueError("BUSINESS_OUTPUT_NOT_VERIFIED")
        completed = api("Complete", rid("complete"), {"table": "qmcp_emailrequest", "recordId": record_id}, resolved, label="Complete")
        if completed.get("Outcome") != "Processed":
            raise ValueError("COMPLETION_NOT_PROCESSED")
        final = {item_id.lower(): call("GET", "workqueueitems(" + item_id + ")?$select=workqueueitemid,uniqueidbyqueue,statecode,statuscode") for item_id in items}
        if final.get(processing_id, {}).get("statecode") != 2 or final.get(queued_id, {}).get("statecode") != 0:
            raise ValueError("FINAL_NATIVE_STATE_ASSERTION_FAILED")
        save(nativeAfterDequeue=after_dequeue, processingItemId=processing_id, queuedItemId=queued_id, attempts={key: len(value) for key, value in attempts.items()}, completedResult=completed, nativeFinal=final, queuedItemLeft=True, completed=True)
    except Exception as error:
        save(error=str(error) if isinstance(error, ValueError) and str(error).isupper() else "PROOF_INCONCLUSIVE")
        raise
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(str(error))
