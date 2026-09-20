"""Prove one winner for two concurrent claims of a synthetic event.

The proof reuses the first eligible pending synthetic event after the
persisted sender cursor on the authorized development queue. It races two
public ClaimEvent calls, finishes the winner with a controlled non-acceptance,
and verifies that the event remains Pending. No policy change or connector
call is made by this probe.
"""
import argparse
import hashlib
import json
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from bootstrap_tenant import _cli_command, _cli_request
from generate_sources import uid
from probe_tenant_metadata import _validate_binding


def validate(binding, ledger):
    origin, organization = _validate_binding(binding)
    queue = ledger.get("queueKey")
    if not isinstance(queue, str) or not queue.startswith("qmcp-proof-"):
        raise ValueError("SYNTHETIC_QUEUE_REQUIRED")
    if queue not in binding.get("queueKeys", []):
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
    if not args.execute:
        print(json.dumps({"ready": True, "tenantCalls": False, "writes": False, "queueKey": queue}, indent=2))
        return

    output = Path(args.output)
    if output.exists():
        raise ValueError("EVIDENCE_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    proof_id = str(uuid.uuid4())
    evidence = {
        "classification": "synthetic-development-concurrent-sender",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "organizationId": organization,
        "queueKey": queue,
        "proofId": proof_id,
        "tenantCalls": True,
        "writesPerformed": True,
        "externalDestinationsUsed": False,
        "policyChanged": False,
        "completed": False,
    }
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    command = _cli_command()

    def save(**values):
        evidence.update(values)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def call(method, path, body=None):
        return _cli_request(command, origin, method, path, body, runner=subprocess.run)

    def api(operation, label, data=None):
        body = {"QueueKey": queue, "RequestId": str(uuid.uuid5(uuid.UUID(proof_id), label)), "DataJson": json.dumps(data or {}, separators=(",", ":"))}
        return json.loads(call("POST", "qmcp_WQ_" + operation, body)["ResultJson"])

    def events():
        rows = call("GET", "qmcp_wqevents?$select=qmcp_key,qmcp_document,createdon&$filter=qmcp_queuekey eq '" + queue + "'&$top=100").get("value", [])
        return [{"key": row.get("qmcp_key"), "createdon": row.get("createdon"), "document": json.loads(row.get("qmcp_document", "{}"))} for row in rows]

    def cursor():
        key = hashlib.sha256((queue + "|events").encode()).hexdigest()
        rows = [row for row in call("GET", "qmcp_wqcursors?$select=qmcp_key,qmcp_document&$top=100").get("value", []) if row.get("qmcp_key") == key]
        if len(rows) > 1:
            raise ValueError("EVENT_CURSOR_NOT_UNIQUE")
        return json.loads(rows[0].get("qmcp_document", "{}")).get("value", "") if rows else ""

    def item_state(item_id):
        return call("GET", "workqueueitems(" + item_id + ")?$select=statecode,statuscode")

    try:
        who = call("GET", "WhoAmI")
        if str(who.get("OrganizationId", "")).lower() != organization.lower() or str(who.get("UserId", "")).lower() != ledger["user"].lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        for flow_name in ("ProcessOne", "OnQueueChanged", "SweepQueue", "Intake", "Watchdog", "TestCoordinator", "EmailSender"):
            if call("GET", "workflows(" + uid("flow:" + flow_name) + ")?$select=statecode").get("statecode") != 0:
                raise ValueError("FLOWS_MUST_BE_DRAFT")
        after = cursor()
        now = datetime.now(timezone.utc)
        eligible = []
        for event in events():
            document = event["document"]
            if event["key"] <= after or document.get("State") != "Pending" or document.get("Destination") != "qmcp-synthetic-outbox-proof":
                continue
            try:
                next_attempt = datetime.fromisoformat(str(document.get("NextAttempt", "")).replace("Z", "+00:00"))
            except ValueError:
                continue
            if next_attempt <= now:
                eligible.append(event)
        eligible.sort(key=lambda row: row["key"])
        if not eligible:
            raise ValueError("NO_ELIGIBLE_SYNTHETIC_EVENT_AFTER_CURSOR")
        target = eligible[0]["document"]
        target_id, item_id = target.get("Id"), target.get("ItemId")
        if not target_id:
            raise ValueError("EVENT_ID_MISSING")
        native_before = item_state(item_id) if item_id else None
        save(cursorAfter=after, targetEventId=target_id, destination=target.get("Destination"), initialTries=target.get("Tries"))

        def claim(label):
            state = {}

            def runner(args, **kwargs):
                result = subprocess.run(args, **kwargs)
                state["raw"] = (result.stdout or "") + " " + (result.stderr or "")
                return result

            try:
                body = {
                    "QueueKey": queue,
                    "RequestId": str(uuid.uuid5(uuid.UUID(proof_id), label)),
                    "DataJson": "{}",
                }
                raw = _cli_request(command, origin, "POST", "qmcp_WQ_ClaimEvent", body, runner=runner)
                result = json.loads(raw["ResultJson"])
                event = result.get("Event") or {}
                return {"outcome": result.get("Outcome"), "eventId": event.get("Id"), "event": event}
            except Exception as error:
                raw = state.get("raw", "")
                if "VERSION_CONFLICT" in raw:
                    return {"outcome": "VERSION_CONFLICT", "eventId": None, "error": "VERSION_CONFLICT"}
                return {"outcome": "ERROR", "error": str(error)}

        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(claim, ("claim-a", "claim-b")))
        save(claimAttempts=[{"outcome": row.get("outcome"), "eventId": row.get("eventId"), "error": row.get("error")} for row in claims])
        winners = [row for row in claims if row.get("outcome") == "Claimed" and row.get("eventId") == target_id]
        losers = [row for row in claims if row.get("outcome") in {"NoWork", "VERSION_CONFLICT"}]
        if len(winners) != 1 or len(losers) != 1:
            raise ValueError("CONCURRENT_CLAIM_RESULT_INVALID")
        winner = winners[0]["event"]
        finished = api("FinishEvent", "finish-winner", {"eventId": winner["Id"], "leaseToken": winner["LeaseToken"], "accepted": False, "code": "SYNTHETIC_CONCURRENT_MAIL_OFFLINE"})
        final = [row for row in events() if row["document"].get("Id") == target_id]
        native_after = item_state(item_id) if item_id else None
        if finished.get("Outcome") != "Pending" or len(final) != 1:
            raise ValueError("CONCURRENT_EVENT_NOT_RETAINED")
        final_event = final[0]["document"]
        if final_event.get("State") != "Pending" or final_event.get("Tries") != int(target.get("Tries", 0)) + 1 or final_event.get("ErrorCode") != "SYNTHETIC_CONCURRENT_MAIL_OFFLINE":
            raise ValueError("CONCURRENT_EVENT_STATE_INVALID")
        if native_after != native_before:
            raise ValueError("NATIVE_ITEM_CHANGED")
        save(winnerCount=len(winners), loserCount=len(losers), loserOutcome=losers[0].get("outcome"), finishOutcome=finished.get("Outcome"), finalState=final_event.get("State"), finalTries=final_event.get("Tries"), nativeItemPresent=bool(item_id), nativeItemUnchanged=True if item_id else None, completed=True, limitation="This proves one winner and one safe loser (NoWork or the public VERSION_CONFLICT optimistic-contention response) for two concurrent sender claims on one synthetic event; connector acceptance, recipient delivery, and complete-Dataverse-outage behavior remain separate.")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        save(error=str(error) if str(error).isupper() else "CONCURRENT_SENDER_PROOF_FAILED", completed=False)
        raise
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not evidence.get("completed"):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise SystemExit(1)
