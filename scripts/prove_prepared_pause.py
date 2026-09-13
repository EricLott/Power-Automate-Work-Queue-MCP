"""Opt-in proof of the prepared-acquisition pause boundary.

The default invocation is validation only.  ``--execute`` uses the exact
synthetic item recorded by the earlier queue-pause proof; it does not enqueue
or delete an item.  Every request id is persisted before its request is sent
so an uncertain policy write is repaired conservatively.
"""
import argparse
import json
import re
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
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")


def _uuid(value, code):
    if not isinstance(value, str) or not UUID_RE.fullmatch(value):
        raise ValueError(code)
    return value


def validate(binding, ledger, seed):
    origin, organization = _validate_binding(binding)
    queue = ledger.get("queueKey")
    if not isinstance(queue, str) or not queue.startswith("qmcp-proof-") or queue not in binding.get("queueKeys", []):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    native_queue = _uuid(ledger.get("queue"), "NATIVE_QUEUE_ID_REQUIRED")
    item = seed.get("itemId") or ledger.get("itemId")
    _uuid(item, "SEEDED_ITEM_REQUIRED")
    if seed.get("queueKey") not in (None, queue) or seed.get("organizationId") not in (None, organization):
        raise ValueError("SEED_ARTIFACT_MISMATCH")
    if seed.get("completed") is not True or seed.get("seededItemLeftQueued") is not True:
        raise ValueError("SEED_ARTIFACT_NOT_QUEUED")
    return origin, organization, queue, native_queue, item


def policies_equal(left, right):
    return {k: v for k, v in left.items() if k != "Revision"} == {k: v for k, v in right.items() if k != "Revision"}


def scoped_dequeue_runner(state, *run_args, **run_kwargs):
    """Run only the native dequeue request and recognize its structured fault."""
    result = subprocess.run(*run_args, **run_kwargs)
    if result.returncode:
        try:
            payload = json.loads(result.stdout or "")
        except (TypeError, ValueError):
            payload = {}
        message = payload.get("error", {}).get("message") if isinstance(payload, dict) else None
        state["errorMessage"] = message[:2000] if isinstance(message, str) else None
        state["errorCode"] = payload.get("error", {}).get("code") if isinstance(payload, dict) else None
        if message == "QUEUE_PAUSED":
            state["value"] = True
            state["fault"] = "QUEUE_PAUSED"
        elif payload.get("error", {}).get("code") == "0x80048d0a" and state.get("itemId"):
            try: native = json.loads(message)
            except (ValueError, TypeError): native = {}
            expected = "Fail to update work queue item " + state["itemId"] + " to Processing because: LIFECYCLE_BYPASS. Fault ErrorCode: -2147220891"
            if native.get("errorCode") == "InternalServerError" and native.get("message") == expected:
                state["value"] = True
                state["fault"] = "LIFECYCLE_BYPASS"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--fixture-ledger", required=True)
    parser.add_argument("--seed-evidence", default="docs/evidence/queue-pause-2026-09-12.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    ledger = json.loads(Path(args.fixture_ledger).read_text(encoding="utf-8-sig"))
    seed = json.loads(Path(args.seed_evidence).read_text(encoding="utf-8-sig"))
    origin, organization, queue, native_queue, item = validate(binding, ledger, seed)
    output = Path(args.output)
    if not args.execute:
        print(json.dumps({"ready": True, "writes": False, "tenantCalls": False, "queueKey": queue, "itemId": item}, indent=2))
        return
    if output.exists():
        raise ValueError("EVIDENCE_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = {"classification": "synthetic-prepared-pause", "organizationId": organization, "queueKey": queue, "itemId": item, "completed": False, "tenantCalls": True}
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    command = _cli_command()

    def call(method, relative, body=None, runner=subprocess.run):
        def diagnostic_runner(*args, **kwargs):
            result = runner(*args, **kwargs)
            if result.returncode:
                try: error = json.loads(result.stdout or "{}").get("error", {})
                except (ValueError, AttributeError): error = {}
                save(lastFailedOperation=relative.split("?")[0], lastError={k: str(error[k])[:2000] for k in ("code", "message") if k in error})
            return result
        return _cli_request(command, origin, method, relative, body, runner=diagnostic_runner)

    def save(**values):
        evidence.update(values)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")

    def api(name, request_id, data=None, request_label=None, **extra):
        save(requests={**evidence.get("requests", {}), request_label or name: request_id})
        body = {"QueueKey": queue, "RequestId": request_id, "DataJson": json.dumps(data or {}, separators=(",", ":"))}
        body.update(extra)
        result = call("POST", "qmcp_WQ_" + name, body)
        return json.loads(result["ResultJson"])

    original = paused = None
    policy_changed = False
    try:
        who = call("GET", "WhoAmI")
        if str(who.get("OrganizationId", "")).lower() != organization.lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        for flow in FLOW_IDS:
            if call("GET", "workflows(" + flow + ")?$select=statecode").get("statecode") != 0:
                raise ValueError("FLOWS_MUST_BE_DRAFT")
        rows = call("GET", "qmcp_wqdefinitions?$select=qmcp_document,versionnumber&$filter=qmcp_key eq '" + queue + "'&$top=2").get("value")
        if not isinstance(rows, list) or len(rows) != 1:
            raise ValueError("POLICY_NOT_UNIQUE")
        original, version = json.loads(rows[0]["qmcp_document"]), rows[0]["versionnumber"]
        if original.get("NativeQueueId", "").lower() != native_queue.lower() or not original.get("Enabled"):
            raise ValueError("POLICY_NOT_ENABLED")
        save(originalPolicy=original, originalVersion=version)
        eligible = call("GET", "workqueueitems?$select=workqueueitemid,uniqueidbyqueue,statecode,statuscode&$filter=_workqueueid_value eq " + native_queue + " and statecode eq 0&$top=2").get("value")
        if not isinstance(eligible, list) or len(eligible) != 1 or str(eligible[0].get("workqueueitemid", "")).lower() != item.lower():
            raise ValueError("SOLE_ELIGIBLE_SEED_MISMATCH")
        native_before = call("GET", "workqueueitems(" + item + ")?$select=workqueueitemid,uniqueidbyqueue,statecode,statuscode")
        if native_before.get("statecode") != 0 or not native_before.get("@odata.etag"):
            raise ValueError("SEEDED_ITEM_NOT_QUEUED")
        prepare_id = str(uuid.uuid4())
        prepared = api("PrepareAcquire", prepare_id)
        if prepared.get("Outcome") != "Prepared":
            raise ValueError("ACQUIRE_NOT_PREPARED")
        if str(prepared.get("NativeQueueId", "")).lower() != native_queue.lower():
            raise ValueError("PREPARED_NATIVE_QUEUE_MISMATCH")
        paused = dict(original); paused["Enabled"] = False
        pause_id = str(uuid.uuid4()); save(pauseRequestId=pause_id)
        policy_changed = True
        registered = api("RegisterQueue", pause_id, paused, request_label="RegisterQueuePause", ExpectedVersion=str(version))
        save(pauseResult=registered)
        native_after_pause = call("GET", "workqueueitems(" + item + ")?$select=workqueueitemid,uniqueidbyqueue,statecode,statuscode")
        if native_after_pause != native_before:
            raise ValueError("NATIVE_ROW_CHANGED_ON_PAUSE")

        saw_pause = {"value": False, "itemId": item}
        try:
            call("POST", "workqueues(" + native_queue + ")/Microsoft.Dynamics.CRM.Dequeue", {}, runner=lambda *a, **k: scoped_dequeue_runner(saw_pause, *a, **k))
        except ValueError:
            if not saw_pause["value"]:
                save(dequeueDiagnostic=saw_pause)
                raise ValueError("NATIVE_DEQUEUE_NOT_QUEUE_PAUSED")
        else:
            raise ValueError("NATIVE_DEQUEUE_ACCEPTED_WHILE_PAUSED")
        native_after_dequeue = call("GET", "workqueueitems(" + item + ")?$select=workqueueitemid,uniqueidbyqueue,statecode,statuscode")
        attempts = call("GET", "qmcp_wqattempts?$select=qmcp_wqattemptid&$filter=qmcp_itemid eq '" + item + "'").get("value")
        if native_after_dequeue != native_before or not isinstance(attempts, list) or attempts:
            raise ValueError("NATIVE_PAUSE_MUTATED_ITEM")
        resolved = api("ResolveAcquire", prepare_id)
        if resolved.get("Outcome") != "Pending":
            raise ValueError("RESOLVE_NOT_PENDING")
        save(nativeBefore=native_before, nativeAfterPause=native_after_pause, nativeAfterDequeue=native_after_dequeue, attempts=0, dequeueOutcome=saw_pause["fault"], prepareOutcome=prepared, resolveOutcome=resolved)
    finally:
        if policy_changed and original is not None:
            rows = call("GET", "qmcp_wqdefinitions?$select=qmcp_document,versionnumber&$filter=qmcp_key eq '" + queue + "'&$top=2").get("value", [])
            if len(rows) != 1:
                save(restoreError="POLICY_NOT_UNIQUE")
            else:
                current = json.loads(rows[0]["qmcp_document"])
                if not policies_equal(current, paused) and not policies_equal(current, original):
                    save(restoreError="CONCURRENT_POLICY_CHANGE")
                    raise ValueError("CONCURRENT_POLICY_CHANGE")
                restore_id = str(uuid.uuid4()); save(restoreRequestId=restore_id)
                api("RegisterQueue", restore_id, original, request_label="RegisterQueueRestore", ExpectedVersion=str(rows[0]["versionnumber"]))
                check = call("GET", "qmcp_wqdefinitions?$select=qmcp_document,versionnumber&$filter=qmcp_key eq '" + queue + "'&$top=2").get("value", [])
                if len(check) != 1 or not policies_equal(json.loads(check[0]["qmcp_document"]), original):
                    raise ValueError("RESTORE_READBACK_FAILED")
                save(policyRestored=True, restoredPolicy=json.loads(check[0]["qmcp_document"]), restoredVersion=check[0]["versionnumber"])
        if evidence.get("policyRestored") and evidence.get("dequeueOutcome") in ("QUEUE_PAUSED", "LIFECYCLE_BYPASS") and evidence.get("resolveOutcome", {}).get("Outcome") == "Pending":
            save(completed=True)
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(str(error))
