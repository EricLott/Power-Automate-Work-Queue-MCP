# Autonomous runtime proof

This procedure records the synthetic installed-runtime proof completed on 2026-09-12. It demonstrates that scheduled Dataverse flows continue work after the initiating agent stops participating. It does not close an acceptance gate.

## Scope and safety

Use only the authorized development environment, a synthetic queue, synthetic test input, and the existing Dataverse connection. Do not substitute a customer mailbox, customer content, production environment, or unrelated production identifiers. Verify the organization with `WhoAmI` before each write. The recorded run used an authenticated Dataverse CLI to start work and observe it. No MCP session was connected. A separate MCP-host acceptance run remains required.

Before changing either flow, save the complete current workflow records, including `clientdata`, `statecode`, `statuscode`, and workflow IDs. The temporary configuration binds the synthetic queue key and native queue ID. Normalize every OpenAPI host in the saved clientdata to `connectionName`; the legacy `connectionReferenceName` form saves as a null host in this tenant. `OnQueueChanged` is unrelated to this proof; its webhook trigger must use `OpenApiConnectionWebhook` when it is tested separately.

## Procedure

1. Through the authenticated Dataverse Web API transport, POST `qmcp_WQ_StartTestRun` with the registered synthetic `QueueKey`, a fresh UUID `RequestId`, and `DataJson` containing the case below. Start one expected-`Exception` test run with synthetic input, call `PrepareAcquire`, perform the native Dataverse `Dequeue`, and call `ResolveAcquire`. Record only the returned run and item references in the local ignored fixture file. The acquired attempt must be left idle so its lease expires. Do not call `RecoverExpiredAttempt`, `AdvanceTestRun`, or any other recovery/coordinator operation after this point.

2. PATCH the installed Watchdog workflow record with the saved `clientdata`, changing only the synthetic queue parameters and connector host serialization; then PATCH `{ "statecode": 1 }` to activate it. Read back the workflow state and status to confirm activation. Apply the same process to TestCoordinator. Add the synthetic queue restriction to its `ListRuns` filter so it cannot advance unrelated tests. Read back both workflow records.

3. Wait past the acquired lease expiry and allow the one-minute recurrences to run. Read the synthetic test-run document from `qmcp_wqtestruns` by its `qmcp_key`, the acquired row from `workqueueitems`, and recent `qmcp_wqcommands` filtered by the synthetic queue key. The observer performs GETs only; it does not advance the test or recover the attempt. Preserve the resulting redacted observation and receipt files as evidence.

4. PATCH both workflows to `{ "statecode": 0 }`, then restore the saved parameters and clientdata, retain the corrected `connectionName` serialization, and verify the restored parameters and Draft state by readback. Record the final flow state and whether the temporary binding was removed.

## Request details

`DataJson` is the serialized JSON representation of this case container; substitute a valid envelope matching the fixture's registered contract:

```json
{
  "cases": [{
    "Id": "lease-expiry",
    "Input": "<replace with the registered synthetic envelope object>",
    "Expected": {},
    "ExpectedOutcome": "Exception",
    "ExpectedAttemptCount": 1
  }]
}
```

For acquisition, POST `qmcp_WQ_PrepareAcquire` with the same queue, a new request UUID and `DataJson: "{}"`; POST `workqueues(<NativeQueueId>)/Microsoft.Dynamics.CRM.Dequeue` with `{}`; then POST `qmcp_WQ_ResolveAcquire` with the exact Prepare request UUID. Require `Outcome: Acquired` before considering the fixture ready. These calls do not invoke business logic.

Workflow writes use `workflows(<installed-workflow-id>)`, and `clientdata` is a JSON-encoded string. Resolve each workflow from the installed solution and verify its identity before editing. Keep original records and actual run/request/item IDs in an ignored local evidence directory; publish only redacted observations. The original run's scratch scripts are not part of the distributable repository.

## Expected evidence and interpretation

The conservative expected result is native `Exception`, one attempt, `reviewRequired: true`, and test `Passed` because the test expected the lease-expiry exception with the observed attempt count. Durable Dataverse command receipts should show Watchdog `RunMaintenance` changing one item, `ApplyRetention` executing, and TestCoordinator eventually returning `Passed`. These receipts and the resulting native/test documents are the execution evidence.

The flow-run metadata query may return no rows. Treat that as missing diagnostic metadata, not as proof that the flows did not run. Do not claim a stronger outcome than the durable receipts and final state support. In particular, this procedure proves one synthetic idle-lease recovery path only; it does not prove mailbox intake, AI extraction, positive business output, load, separate-user authorization, clean installation, managed upgrade, or customer isolation.

The redacted record in `docs/evidence/autonomous-runtime-2026-09-12.json` reports the completed case: autonomous execution did not require an MCP session, the temporary flow configuration was restored, all seven flows ended Draft, and zero of the 22 acceptance gates were closed. A separate [positive-output proof](evidence/positive-coordinator-2026-09-12.json) subsequently verified real record field assertions and test-owned cleanup. It used CLI-supplied synthetic output; it does not establish prompt quality.

## Fresh scheduled backlog checkpoint — 2026-09-20

The reusable [scheduled backlog proof](../scripts/prove_scheduled_backlog.py) created three synthetic items, acquired them without business processing, restored the original queue policy, and temporarily activated only Watchdog. A durable scheduled `RunMaintenance` receipt reported `Swept` with `changed: 3`; independent reads found all three items in `Exception`/`ReviewRequired` with no active attempt. Watchdog was restored to Draft and the queue policy was restored. Redacted evidence is in [scheduled-backlog-2026-09-20.json](evidence/scheduled-backlog-2026-09-20.json).

This strengthens the scheduled backlog path but does not prove event-parent activation, real intake, separate-identity authorization, capacity, or managed release.
