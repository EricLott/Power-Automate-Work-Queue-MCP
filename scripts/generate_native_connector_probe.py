"""Generate a bounded, synthetic native Dataverse connector proof flow.

The result is Power Automate ``clientData`` suitable for inspection or a later
tenant experiment.  This module deliberately performs no network or tenant
operations; all identifiers and the run id are supplied by the caller.
"""
import argparse
import json
import re
import uuid
from pathlib import Path


CONNECTION = "qmcp_reference_worker_dataverse"
DATAVERSE_API = "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps"
CASES = ("available", "empty", "paused")
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def _uuid(value, label):
    try:
        parsed = uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ValueError(label + "_INVALID_UUID") from None
    return str(parsed)


def _note_ids(noteids):
    if isinstance(noteids, dict):
        values = [noteids.get(case) for case in CASES]
    elif isinstance(noteids, (list, tuple)) and len(noteids) == len(CASES):
        values = list(noteids)
    else:
        raise ValueError("NOTE_IDS_REQUIRED")
    if any(value is None for value in values):
        raise ValueError("NOTE_IDS_REQUIRED")
    normalized = [_uuid(value, "NOTE") for value in values]
    if len(set(normalized)) != len(CASES): raise ValueError("NOTE_IDS_MUST_BE_DISTINCT")
    return dict(zip(CASES, normalized))


def _native_dequeue(queueid, after=None):
    return {
        "type": "OpenApiConnection",
        "inputs": {
            "host": {"apiId": DATAVERSE_API, "connectionName": CONNECTION,
                     "operationId": "PerformBoundAction"},
            "parameters": {"entityName": "workqueues",
                           "actionName": "Microsoft.Dynamics.CRM.Dequeue",
                           "recordId": queueid},
            "retryPolicy": {"type": "none"},
        },
        "runAfter": {} if after is None else {after: ["Succeeded"]},
    }


def _record(noteid, case, dequeue, runid, after):
    # Keep the evidence expression limited to the synthetic probe's own run
    # and the native action's status/body/error fields.
    action = "setProperty(json('{}'),'status',actions('" + dequeue + "')?['status'])"
    action = "setProperty(" + action + ", 'body', body('" + dequeue + "'))"
    action = "setProperty(" + action + ", 'error', actions('" + dequeue + "')?['error'])"
    evidence = "json('{}')"
    for key, value in (("runId", runid), ("case", case),
                       ("flowRunId", "workflow()?['run']?['name']"),
                       ("actionStatus", "actions('" + dequeue + "')?['status']")):
        expression = (value if value.startswith(("workflow(", "actions("))
                      else "'" + value + "'")
        evidence = "setProperty(" + evidence + ", '" + key + "', " + expression + ")"
    evidence = "setProperty(" + evidence + ", 'body', body('" + dequeue + "'))"
    evidence = "setProperty(" + evidence + ", 'error', actions('" + dequeue + "')?['error'])"
    evidence = "setProperty(" + evidence + ", 'actions', setProperty(json('{}'), '" + dequeue + "', " + action + "))"
    return {
        "type": "OpenApiConnection",
        "inputs": {
            "host": {"apiId": DATAVERSE_API, "connectionName": CONNECTION,
                     "operationId": "CreateRecord"},
            "parameters": {"entityName": "annotations", "item/annotationid": noteid,
                           "item/subject": "qmcp native connector proof " + runid + " " + case,
                           "item/notetext": "@string(" + evidence + ")"},
            "retryPolicy": {"type": "none"},
        },
        "runAfter": {after: ["Succeeded", "Failed", "TimedOut"]},
    }


def _update(queueid, statecode, statuscode, after, all_states=False):
    return {
        "type": "OpenApiConnection",
        "inputs": {
            "host": {"apiId": DATAVERSE_API, "connectionName": CONNECTION,
                     "operationId": "UpdateRecord"},
            "parameters": {"entityName": "workqueues", "recordId": queueid,
                           "item/statecode": statecode, "item/statuscode": statuscode},
            "retryPolicy": {"type": "none"},
        },
        "runAfter": {after: (["Succeeded", "Failed", "TimedOut", "Skipped"]
                              if all_states else ["Succeeded"])},
    }


def generate(queueid, runid, noteids):
    """Return deterministic synthetic probe ``clientData`` for three cases."""
    queueid = _uuid(queueid, "QUEUE")
    if not isinstance(runid, str) or not _RUN_ID.fullmatch(runid):
        raise ValueError("RUN_ID_INVALID")
    notes = _note_ids(noteids)
    actions = {
        "DequeueAvailable": _native_dequeue(queueid),
        "RecordAvailable": _record(notes["available"], "available", "DequeueAvailable", runid, "DequeueAvailable"),
        "DequeueEmpty": _native_dequeue(queueid, "RecordAvailable"),
        "RecordEmpty": _record(notes["empty"], "empty", "DequeueEmpty", runid, "DequeueEmpty"),
        "PauseQueue": _update(queueid, 1, 3, "RecordEmpty"),
        "DequeuePaused": _native_dequeue(queueid, "PauseQueue"),
        "RecordPaused": _record(notes["paused"], "paused", "DequeuePaused", runid, "DequeuePaused"),
        "RestoreQueue": _update(queueid, 0, 1, "RecordPaused", all_states=True),
    }
    definition = {
        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
        "contentVersion": "0.1.0.0",
        "parameters": {"$connections": {"defaultValue": {}, "type": "Object"},
                       "$authentication": {"defaultValue": {}, "type": "SecureObject"}},
        "triggers": {"manual": {"type": "Recurrence", "recurrence": {"frequency": "Minute", "interval": 1},
                                  "runtimeConfiguration": {"concurrency": {"runs": 1}}}},
        "actions": actions,
        "outputs": {},
    }
    return {"properties": {"connectionReferences": {
        CONNECTION: {"runtimeSource": "embedded", "connection": {"connectionReferenceLogicalName": CONNECTION},
                     "api": {"name": "shared_commondataserviceforapps"}},
    }, "definition": definition, "templateName": ""}, "schemaVersion": "1.0.0.0"}


generate_native_connector_probe = generate


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--note-ids", required=True, help="JSON object with available, empty and paused UUIDs")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = generate(args.queue_id, args.run_id, json.loads(args.note_ids))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
