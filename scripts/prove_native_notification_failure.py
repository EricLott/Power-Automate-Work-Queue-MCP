"""Prove installed EmailSender failure preserves the business outcome.

The runner temporarily binds the installed EmailSender flow to the bound
synthetic queue and an intentionally invalid recipient. It observes the
durable event after the native Outlook action fails, verifies the linked
business item is unchanged, and restores the original flow record to Draft.
"""
import argparse
import datetime
import json
import subprocess
import time
import uuid
from pathlib import Path

from bootstrap_tenant import _cli_command, _cli_request
from generate_sources import uid
from probe_tenant_metadata import _validate_binding


FLOW_NAMES = ("ProcessOne", "OnQueueChanged", "SweepQueue", "Intake", "Watchdog", "TestCoordinator", "EmailSender")
FLOW_NAME = "EmailSender"
DEFAULT_DESTINATION = "not-an-email-address"


def validate(binding, ledger):
    origin, organization = _validate_binding(binding)
    queue = ledger.get("queueKey")
    if not isinstance(queue, str) or not queue.startswith("qmcp-proof-"):
        raise ValueError("SYNTHETIC_QUEUE_REQUIRED")
    if queue not in binding.get("queueKeys", []):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    for key in ("queue", "user"):
        try:
            uuid.UUID(str(ledger[key]))
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


def decode_event(row):
    try:
        document = json.loads(row.get("qmcp_document", "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        document = {}
    return row, document if isinstance(document, dict) else {}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--fixture-ledger", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--notification-address", default=DEFAULT_DESTINATION)
    parser.add_argument("--wait-seconds", type=int, default=180)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    ledger = json.loads(Path(args.fixture_ledger).read_text(encoding="utf-8-sig"))
    origin, organization, queue = validate(binding, ledger)
    if not 90 <= args.wait_seconds <= 300:
        raise ValueError("WAIT_BOUND_INVALID")
    if not args.notification_address or "@" in args.notification_address:
        raise ValueError("INVALID_FAILURE_ADDRESS_REQUIRED")
    if not args.execute:
        print(json.dumps({
            "ready": True,
            "tenantCalls": False,
            "writes": False,
            "queueKey": queue,
            "flow": FLOW_NAME,
            "notificationAddress": args.notification_address,
        }, indent=2))
        return

    output = Path(args.output)
    if output.exists():
        raise ValueError("EVIDENCE_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "classification": "synthetic-native-email-sender-failure",
        "date": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
        "organizationId": organization,
        "queueKey": queue,
        "flow": FLOW_NAME,
        "notificationAddress": args.notification_address,
        "tenantCalls": True,
        "writesPerformed": False,
        "externalDestinationsUsed": False,
        "completed": False,
        "flowsRestored": False,
    }

    def save(**values):
        evidence.update(values)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    save()
    command = _cli_command()
    original = None
    flow_path = "workflows(" + uid("flow:" + FLOW_NAME) + ")"

    def call(method, path, body=None):
        return _cli_request(command, origin, method, path, body, runner=subprocess.run)

    def events():
        rows = call("GET", "qmcp_wqevents?$select=qmcp_key,qmcp_document,createdon&$filter=qmcp_queuekey eq '" + queue + "'&$top=500").get("value", [])
        return [decode_event(row) for row in rows]

    def cursor_value():
        import hashlib
        key = hashlib.sha256((queue + "|events").encode("utf-8")).hexdigest()
        rows = call("GET", "qmcp_wqcursors?$select=qmcp_key,qmcp_document&$filter=qmcp_key eq '" + key + "'&$top=2").get("value", [])
        if len(rows) > 1:
            raise ValueError("EVENT_CURSOR_NOT_UNIQUE")
        try:
            return json.loads(rows[0].get("qmcp_document", "{}")).get("value", "") if rows else ""
        except (TypeError, ValueError, json.JSONDecodeError):
            raise ValueError("EVENT_CURSOR_INVALID")

    def item_state(item_id):
        if not item_id:
            return None
        return call("GET", "workqueueitems(" + item_id + ")?$select=statecode,statuscode,versionnumber")

    def find_target(after):
        now = datetime.datetime.now(datetime.timezone.utc)
        candidates = []
        for row, document in events():
            if document.get("State") != "Pending" or document.get("Destination") != "qmcp-synthetic-outbox-proof":
                continue
            try:
                next_attempt = datetime.datetime.fromisoformat(str(document.get("NextAttempt", "")).replace("Z", "+00:00"))
            except ValueError:
                continue
            if next_attempt <= now:
                candidates.append((row, document))
        candidates.sort(key=lambda value: value[0].get("qmcp_key", ""))
        if not candidates:
            raise ValueError("NO_ELIGIBLE_SYNTHETIC_EVENT_AFTER_CURSOR")
        after_candidates = [value for value in candidates if value[0].get("qmcp_key", "") > after]
        return (after_candidates[0], False) if after_candidates else (candidates[0], True)

    try:
        who = call("GET", "WhoAmI")
        if (str(who.get("OrganizationId", "")).lower() != organization.lower()
                or str(who.get("UserId", "")).lower() != str(ledger["user"]).lower()):
            raise ValueError("ENVIRONMENT_MISMATCH")
        for name in FLOW_NAMES:
            if call("GET", "workflows(" + uid("flow:" + name) + ")?$select=statecode").get("statecode") != 0:
                raise ValueError("FLOWS_MUST_BE_DRAFT")

        cursor_before = cursor_value()
        (target_row, target_document), cursor_wrapped = find_target(cursor_before)
        target_id = target_document.get("Id")
        item_id = target_document.get("ItemId")
        if not target_id:
            raise ValueError("EVENT_ID_MISSING")
        native_before = item_state(item_id)
        original = call("GET", flow_path + "?$select=workflowid,name,statecode,statuscode,clientdata")
        if original.get("name") != FLOW_NAME or original.get("statecode") != 0:
            raise ValueError("EMAIL_SENDER_NOT_DRAFT")
        temporary = json.loads(original["clientdata"])
        normalize_hosts(temporary)
        parameters = temporary["properties"]["definition"]["parameters"]
        parameters["qmcp_QueueKey"]["defaultValue"] = queue
        parameters["qmcp_NativeQueueId"]["defaultValue"] = str(ledger["queue"])
        parameters["qmcp_NotificationAddress"]["defaultValue"] = args.notification_address
        save(
            writesPerformed=True,
            cursorBefore=cursor_before,
            cursorWrapped=cursor_wrapped,
            targetEventId=target_id,
            targetItemId=item_id,
            initialEventState=target_document.get("State"),
            initialTries=target_document.get("Tries"),
            nativeBefore=native_before,
        )
        call("PATCH", flow_path, {"clientdata": json.dumps(temporary, separators=(",", ":"))})
        configured = call("GET", flow_path + "?$select=statecode,clientdata")
        configured_parameters = json.loads(configured["clientdata"])["properties"]["definition"]["parameters"]
        if (configured_parameters["qmcp_QueueKey"]["defaultValue"] != queue
                or configured_parameters["qmcp_NativeQueueId"]["defaultValue"].lower() != str(ledger["queue"]).lower()
                or configured_parameters["qmcp_NotificationAddress"]["defaultValue"] != args.notification_address):
            raise ValueError("SENDER_BINDING_NOT_CONFIRMED")
        call("PATCH", flow_path, {"statecode": 1, "statuscode": 2})
        if call("GET", flow_path + "?$select=statecode").get("statecode") != 1:
            raise ValueError("EMAIL_SENDER_NOT_ACTIVE")
        save(flowActivated=True)

        deadline = time.monotonic() + args.wait_seconds
        final_row = None
        final_document = None
        while time.monotonic() < deadline:
            matches = [(row, document) for row, document in events() if document.get("Id") == target_id]
            if len(matches) != 1:
                raise ValueError("TARGET_EVENT_NOT_UNIQUE")
            row, document = matches[0]
            if int(document.get("Tries", 0)) > int(target_document.get("Tries", 0)):
                final_row, final_document = row, document
                break
            time.sleep(10)
        if final_document is None:
            raise ValueError("NATIVE_SENDER_FAILURE_NOT_OBSERVED")
        native_after = item_state(item_id)
        save(
            finalEventState=final_document.get("State"),
            finalTries=final_document.get("Tries"),
            finalErrorCode=final_document.get("ErrorCode"),
            nativeAfter=native_after,
            businessResultUnchanged=native_after == native_before,
        )
        if (final_document.get("State") != "Pending"
                or final_document.get("ErrorCode") != "SENDER_FAILED"
                or native_after != native_before):
            raise ValueError("NATIVE_NOTIFICATION_FAILURE_ASSERTION_FAILED")
        evidence["completed"] = True
    except Exception as error:
        evidence["error"] = str(error) if isinstance(error, ValueError) and str(error).isupper() else "NATIVE_NOTIFICATION_FAILURE_INCONCLUSIVE"
        raise
    finally:
        if original is not None:
            restoration_errors = []
            try:
                call("PATCH", flow_path, {"statecode": 0})
                call("PATCH", flow_path, {"clientdata": original["clientdata"]})
                restored = call("GET", flow_path + "?$select=statecode,clientdata")
                if restored.get("statecode") != 0 or restored.get("clientdata") != original.get("clientdata"):
                    raise ValueError("FLOW_RESTORE_MISMATCH")
            except Exception:
                restoration_errors.append(FLOW_NAME)
            save(flowsRestored=not restoration_errors, restorationErrors=restoration_errors)
            if restoration_errors:
                raise ValueError("FLOW_RESTORATION_FAILED")
    save(recordedAtUtc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not evidence.get("completed"):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise SystemExit(1)
