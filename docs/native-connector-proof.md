# Native dequeue through the Dataverse connector

The [installed connector matrix](evidence/native-connector-2026-09-13.json) passed in the authorized development environment on 2026-09-13 UTC. A temporary recurrence flow called the standard Dataverse connector's PerformBoundAction with entityName `workqueues`, actionName `Microsoft.Dynamics.CRM.Dequeue` and the explicit synthetic queue ID. It did not list items and then patch one to claim it.

| Queue condition | Observed connector response |
|---|---|
| One available native item | Succeeded; body is a workqueueitem entity with the expected ID and Processing state/status 1. |
| No eligible item after that claim | Succeeded; body and error are null. This is a normal empty result, not a processing failure. |
| Native queue paused | Failed; body contains error code 0x80048d0b, with a JSON message containing RecordNotActive and the exact paused queue ID. |

All three observations came from the same real flow run, recorded in synthetic [Dataverse Notes](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/reference/entities/annotation) through the connector and independently read through the CLI. The runner verifies the note IDs, case/run identifiers, common flow-run identity, creator and exact response shapes. Notes are diagnostic evidence, not business output. The isolated native probe queue has no framework queue binding, so this experiment makes no attempt-ownership claim. The [reference quality proof](reference-quality-proof.md) separately records successful installed ProcessOne execution with the registered queue and real Predict action; current Draft state reflects restoration after those runs.

The generated flow restores the native queue to Active. The runner then disables the probe flow and restores the synthetic item to Queued. The first run revealed that immediate Processing -> Queued is rejected by native Dataverse. Cleanup now ends the isolated probe attempt as Exception and resets Exception -> Queued, both observed supported transitions. This is test-fixture cleanup, not a worker retry policy. The corrected full run passed, and fresh independent reads verified the flow Draft, queue Active, item Queued and original empty JSON input. Native processing history is retained. The earlier failed cleanup and its repair remain in the evidence.

## Calling-path decision for P0-01

Architecture v0.1 proposed native dequeue inside an outer Custom API through IOrganizationService. The original installed experiment reached native processing but its item Update did not retain the outer API ancestor, and the framework guard rejected it. The [import ledger](live-import.md#runtime-checkpoint) and [handoff decision](decisions/2026-09-12-acquisition-handoff.md) record that negative result. It is not a supported-but-passing acquisition path. Production deliberately rejects legacy AcquireNext.

The selected path is PrepareAcquire, native connector Dequeue, a synchronous native Update post-handler that invokes AcceptAcquire, and ResolveAcquire before business work. The [transaction matrix](transaction-boundary-proof.md) proves the selected post-handler/API transaction, and the [identity matrix](acquisition-identity-proof.md) proves concurrency and lost-result replay. P0-01's initial wording assumed both proposed calling paths would be supported; the completed spike evaluates both and selects the evidenced alternative. It does not promise support for the rejected outer-API composition.

## Reproduction

```powershell
python scripts/prove_native_connector.py --binding artifacts/live/mcp-binding.json --output-dir artifacts/live/native-connector-new --run-id connector-new
# Add --execute for the authorized isolated native probe.
```

The script requires the known isolated probe queue and its exact sole synthetic item, an active queue, null expiry, empty JSON input, no framework binding and all seven installed runtime/reference flows Draft. It creates a run-specific probe flow and three diagnostic Notes, retaining them for review. Output directories and identifiers must be fresh. The default performs no tenant calls. The flow uses only the existing Dataverse connection reference and invokes no business processor, mailbox, email or Teams connector.

The current regression checkpoint is 289 passing tests: 93 runtime, 47 plug-in, 118 Python and 31 MCP. Seven new offline tests cover generator inputs, failure recording, restoration, dry run and mocked runner success/failure. They validate the scripts; the linked real connector observations establish the tenant behavior. This proof does not close separate-user security, real mailbox integration, managed installation/upgrade or load gates.
