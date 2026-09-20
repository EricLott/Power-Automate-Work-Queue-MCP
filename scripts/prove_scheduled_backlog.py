"""Prove that the installed Watchdog sweep processes several expired items.

The proof is opt-in and synthetic-only.  It temporarily shortens the lease on
one allowlisted development queue, acquires three items without business work,
restores the queue policy, activates Watchdog, and verifies one durable
RunMaintenance receipt plus independent native/context reads for every item.
The workflow and queue policy are restored in ``finally``; no customer flow,
mailbox, notification, or TestCoordinator is activated.
"""
import argparse
import copy
import json
import subprocess
import time
import uuid
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


def decode_result(row):
    document = json.loads(row.get("qmcp_document", "{}"))
    result = document.get("Result", "{}")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (TypeError, ValueError):
            result = {}
    return document, result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--fixture-ledger", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--lease-seconds", type=int, default=10)
    parser.add_argument("--wait-seconds", type=int, default=150)
    args = parser.parse_args(argv)

    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    ledger = json.loads(Path(args.fixture_ledger).read_text(encoding="utf-8-sig"))
    origin, organization, queue = validate(binding, ledger)
    if not 1 <= args.lease_seconds <= 30:
        raise ValueError("LEASE_BOUND_INVALID")
    if not 60 <= args.wait_seconds <= 300:
        raise ValueError("WAIT_BOUND_INVALID")
    if not args.execute:
        print(json.dumps({"ready": True, "tenantCalls": False, "writes": False, "queueKey": queue}, indent=2))
        return

    output = Path(args.output)
    if output.exists():
        raise ValueError("EVIDENCE_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    proof_id = str(uuid.uuid4())
    workflow_id = uid("flow:Watchdog")
    workflow_path = "workflows(" + workflow_id + ")"
    evidence = {
        "classification": "synthetic-development-scheduled-backlog",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "organizationId": organization,
        "queueKey": queue,
        "proofId": proof_id,
        "workflow": "Watchdog",
        "itemsRequested": 3,
        "leaseSeconds": args.lease_seconds,
        "tenantCalls": True,
        "writesPerformed": True,
        "externalDestinationsUsed": False,
        "completed": False,
        "workflowRestored": False,
        "policyRestored": False,
    }
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    command = _cli_command()
    original_workflow = None
    original_policy = None
    policy_version = None
    policy_changed = False
    item_ids = []

    def save(**values):
        evidence.update(values)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def call(method, path, body=None):
        return _cli_request(command, origin, method, path, body, runner=subprocess.run)

    def api(operation, label, data=None, item=None, expected_version=None):
        body = {
            "QueueKey": queue,
            "RequestId": str(uuid.uuid5(uuid.UUID(proof_id), label)),
            "DataJson": json.dumps(data or {}, separators=(",", ":")),
        }
        if item:
            body["ItemId"] = item
        if expected_version is not None:
            body["ExpectedVersion"] = str(expected_version)
        response = call("POST", "qmcp_WQ_" + operation, body)
        return json.loads(response["ResultJson"])

    def query_definition():
        rows = call(
            "GET",
            "qmcp_wqdefinitions?$select=qmcp_document,versionnumber&$filter=qmcp_key eq '"
            + queue
            + "'&$top=2",
        ).get("value", [])
        if len(rows) != 1:
            raise ValueError("QUEUE_POLICY_NOT_UNIQUE")
        return json.loads(rows[0]["qmcp_document"]), rows[0]["versionnumber"]

    def query_items(states=None):
        path = "workqueueitems?$select=workqueueitemid,statecode,statuscode,input&$filter=_workqueueid_value eq " + ledger["queue"]
        if states:
            path += " and (" + " or ".join("statecode eq " + str(state) for state in states) + ")"
        path += "&$top=100"
        return call("GET", path).get("value", [])

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

    def workflow_parameters(clientdata):
        return json.loads(clientdata)["properties"]["definition"]["parameters"]

    def configure_workflow():
        nonlocal original_workflow
        original_workflow = call("GET", workflow_path + "?$select=workflowid,name,statecode,statuscode,clientdata")
        if original_workflow.get("workflowid", "").lower() != workflow_id.lower() or original_workflow.get("name") != "Watchdog":
            raise ValueError("WORKFLOW_ID_MISMATCH")
        temporary = json.loads(original_workflow["clientdata"])
        normalize_hosts(temporary)
        parameters = temporary["properties"]["definition"]["parameters"]
        parameters["qmcp_QueueKey"]["defaultValue"] = queue
        parameters["qmcp_NativeQueueId"]["defaultValue"] = ledger["queue"]
        call("PATCH", workflow_path, {"statecode": 0})
        call("PATCH", workflow_path, {"clientdata": json.dumps(temporary, separators=(",", ":"))})
        configured = call("GET", workflow_path + "?$select=statecode,clientdata")
        configured_parameters = workflow_parameters(configured["clientdata"])
        if configured_parameters["qmcp_QueueKey"]["defaultValue"] != queue or configured_parameters["qmcp_NativeQueueId"]["defaultValue"].lower() != ledger["queue"].lower():
            raise ValueError("WORKFLOW_BINDING_NOT_CONFIRMED")
        call("PATCH", workflow_path, {"statecode": 1})
        active = call("GET", workflow_path + "?$select=statecode,statuscode")
        if active.get("statecode") != 1:
            raise ValueError("WORKFLOW_NOT_ACTIVE")
        save(workflowActivated=True)

    def restore_workflow():
        if original_workflow is None:
            return
        restored_data = json.loads(original_workflow["clientdata"])
        normalize_hosts(restored_data)
        call("PATCH", workflow_path, {"statecode": 0})
        call("PATCH", workflow_path, {"clientdata": json.dumps(restored_data, separators=(",", ":"))})
        restored = call("GET", workflow_path + "?$select=statecode,clientdata")
        if restored.get("statecode") != 0:
            raise ValueError("WORKFLOW_RESTORE_FAILED")
        if workflow_parameters(restored["clientdata"]) != workflow_parameters(json.dumps(restored_data, separators=(",", ":"))):
            raise ValueError("WORKFLOW_PARAMETERS_NOT_RESTORED")
        save(workflowRestored=True, finalWorkflowState="Draft")

    def restore_policy():
        nonlocal policy_changed, policy_version
        if original_policy is None or not policy_changed:
            return
        current, current_version = query_definition()
        if current.get("NativeQueueId", "").lower() != original_policy.get("NativeQueueId", "").lower():
            raise ValueError("QUEUE_POLICY_ID_CHANGED")
        api("RegisterQueue", "restore-policy", original_policy, expected_version=current_version)
        restored, policy_version = query_definition()
        if any(restored.get(key) != original_policy.get(key) for key in ("NativeQueueId", "Enabled", "MaxAttempts", "LeaseSeconds", "DeadlineSeconds", "RetryBaseSeconds", "RetryMaxSeconds", "SafeEffects", "Contracts", "Grants", "Destinations", "Retention")):
            raise ValueError("QUEUE_POLICY_NOT_RESTORED")
        policy_changed = False
        save(policyRestored=True, restoredRevision=restored.get("Revision"))

    try:
        who = call("GET", "WhoAmI")
        if str(who.get("OrganizationId", "")).lower() != organization.lower() or str(who.get("UserId", "")).lower() != ledger["user"].lower():
            raise ValueError("ENVIRONMENT_MISMATCH")
        flow_state = call("GET", workflow_path + "?$select=statecode").get("statecode")
        if flow_state != 0:
            raise ValueError("WATCHDOG_MUST_BE_DRAFT")
        existing_active = query_items(states=(0, 1))
        if existing_active:
            raise ValueError("SYNTHETIC_QUEUE_NOT_IDLE")
        original_policy, policy_version = query_definition()
        temporary_policy = copy.deepcopy(original_policy)
        temporary_policy["LeaseSeconds"] = args.lease_seconds
        temporary_policy["DeadlineSeconds"] = max(args.lease_seconds, int(original_policy.get("DeadlineSeconds", 1800)))
        registered = api("RegisterQueue", "shorten-lease", temporary_policy, expected_version=policy_version)
        policy_changed = True
        save(policyRevision=registered.get("Revision"), policyVersion=registered.get("Version"))

        for index in range(3):
            label = "enqueue-" + str(index)
            envelope = {
                "envelopeVersion": "1.0",
                "contract": "mail.v1",
                "correlationId": proof_id + "-" + str(index),
                "deduplicationKey": proof_id + "-" + str(index),
                "source": {"kind": "synthetic"},
                "payload": {
                    "subject": "Synthetic scheduled backlog proof " + str(index),
                    "senderAddress": "synthetic@example.invalid",
                    "bodyText": "Synthetic scheduled recovery validation only.",
                },
            }
            enqueued = api("Enqueue", label, envelope)
            if enqueued.get("Outcome") != "Enqueued" or not enqueued.get("ItemId"):
                raise ValueError("ENQUEUE_NOT_CONFIRMED")
            item_ids.append(enqueued["ItemId"])

        acquired = []
        for index, item_id in enumerate(item_ids):
            label = "acquire-" + str(index)
            prepared = api("PrepareAcquire", label, {"flowId": "scheduled-backlog-proof", "runId": proof_id})
            if prepared.get("Outcome") != "Prepared":
                raise ValueError("ACQUIRE_NOT_PREPARED")
            dequeued = call("POST", "workqueues(" + ledger["queue"] + ")/Microsoft.Dynamics.CRM.Dequeue", {})
            if dequeued.get("workqueueitemid", "").lower() != item_id.lower():
                raise ValueError("UNEXPECTED_ITEM_DEQUEUED")
            resolved = api("ResolveAcquire", label)
            if resolved.get("Outcome") != "Acquired" or resolved.get("ItemId", "").lower() != item_id.lower():
                raise ValueError("ACQUIRE_NOT_RESOLVED")
            acquired.append({"itemId": item_id, "attemptId": resolved.get("AttemptId"), "generation": resolved.get("Generation")})
        save(acquired=acquired)
        restore_policy()
        configure_workflow()

        deadline = time.monotonic() + args.wait_seconds
        observed = None
        while time.monotonic() < deadline:
            command_rows = call("GET", "qmcp_wqcommands?$select=qmcp_queuekey,qmcp_document,createdon&$filter=qmcp_queuekey eq '" + queue + "'&$top=100").get("value", [])
            receipts = []
            for row in command_rows:
                document, result = decode_result(row)
                if document.get("Operation") != "RunMaintenance":
                    continue
                receipts.append({"operation": "RunMaintenance", "created": row.get("createdon"), "outcome": result.get("Outcome"), "changed": result.get("Changed")})
            states = []
            for item_id in item_ids:
                native = call("GET", "workqueueitems(" + item_id + ")?$select=statecode,statuscode")
                contexts = call("GET", "qmcp_wqitemcontexts?$select=qmcp_document&$filter=qmcp_itemid eq '" + item_id + "'&$top=2").get("value", [])
                attempts = call("GET", "qmcp_wqattempts?$select=qmcp_document&$filter=qmcp_itemid eq '" + item_id + "'&$top=10").get("value", [])
                context = json.loads(contexts[0]["qmcp_document"]) if len(contexts) == 1 else {}
                attempt_docs = [json.loads(row["qmcp_document"]) for row in attempts]
                states.append({"itemId": item_id, "statecode": native.get("statecode"), "statuscode": native.get("statuscode"), "reviewRequired": context.get("ReviewRequired"), "activeAttempt": context.get("ActiveAttempt"), "attemptOutcomes": [doc.get("Outcome") for doc in attempt_docs]})
            matched = next((receipt for receipt in receipts if receipt.get("outcome") == "Swept" and (receipt.get("changed") or 0) >= 3), None)
            if matched and all(state["statecode"] == 4 and state["statuscode"] == 4 and state["reviewRequired"] is True and not state["activeAttempt"] and "Exception" in state["attemptOutcomes"] for state in states):
                observed = {"receipt": matched, "items": states}
                break
            time.sleep(5)
        if observed is None:
            raise ValueError("SCHEDULED_BACKLOG_NOT_OBSERVED")
        save(observations=observed, completed=True, limitation="This proves a bounded three-item synthetic scheduled sweep; event-parent activation, separate identity, capacity and managed-release behavior remain separate gates.")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        save(error=str(error) if str(error).isupper() else "SCHEDULED_BACKLOG_PROOF_FAILED", completed=False)
        raise
    finally:
        try:
            restore_workflow()
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            save(restoreError=str(error) if str(error).isupper() else "WORKFLOW_RESTORE_FAILED", completed=False)
        try:
            restore_policy()
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            save(restoreError=str(error) if str(error).isupper() else "POLICY_RESTORE_FAILED", completed=False)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not evidence.get("completed") or not evidence.get("workflowRestored") or not evidence.get("policyRestored"):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise SystemExit(1)
