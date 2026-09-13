# Bounded status reads and output redaction

GetItemStatus now returns only string table and recordId from the stored completion output. Previously it returned arbitrary additional worker fields, which could expose private result data to readers. The stored completion evidence is unchanged. LastAttempt is included alongside ActiveAttempt so completed work retains an attempt reference without a native cloud-flow run record.

The [installed proof](evidence/status-redaction-2026-09-13.json) completed a synthetic queued item with privateNote and nested sentinel fields. Public status returned exactly the output reference and correct LastAttempt, with no active attempt. Independent item-context reads retained the full completion document, and the business record's source key matched. No flow or notification sender was activated. The synthetic item is Processed and its business record is retained.

The updated plug-in package was pushed successfully after a fresh build and package round trips. All 266 tests passed: 93 runtime, 40 plug-in, 102 Python and 31 MCP. New runtime tests verify redaction, preserved internal evidence and refusal of a reader on an existing queue without a grant. The installed experiment uses one authorized actor; it does not replace separate-user security validation.

GetQueueHealth remains bounded to 100 native items per page, with NextCursor, per-page count/oldest time and enabled/revision configuration state. Neither read returns input payloads. API authorization remains queue-scoped; status also verifies the item belongs to the requested queue. Optional native cloud-run metadata is not required to read the framework's durable status and attempt references.

```powershell
python scripts/prove_status_redaction.py --binding artifacts/live/mcp-binding.json --fixture artifacts/live/native-pause-fixture.json --output artifacts/live/status-redaction-new.json
# Add --execute for the authorized synthetic run.
```

The fixture specifies the exact sole queued synthetic item, native queue and owner team. Use a new output path. Request and record IDs are persisted before calls; the same acquisition request is used for prepare and resolve. The script never automatically restarts uncertain processing. Inspect its saved ownership and current tenant state after a failure. The recorded item has completed and cannot be reused as a queued fixture.
