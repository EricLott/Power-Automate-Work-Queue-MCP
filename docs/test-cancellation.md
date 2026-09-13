# Test cancellation

`qmcp_WQ_CancelTestRun` requires the tester role and queue access. The MCP tool `cancel_test_run` accepts `queueKey`, `runId`, and a caller-generated `requestId`. Reuse that request ID after an uncertain response. Cancellation and its command receipt commit in the same runtime transaction.

Pending results become `Cancelled`. Unstarted native items move from Queued to OnHold; their companion context records a durable cancellation flag. Acquisition and retry reject cancelled work. An active attempt remains active because an external action already in progress cannot be revoked. A later completion can record the actual outcome, while the test remains cancelled; a failure cannot schedule a new retry.

Cancellation, acquisition, completion, failure, recovery, retry, and coordinator advancement compare the context or run row version observed during validation. A conflicting write fails the command and rolls back its native state changes. Injected local tests exercise these conflicts; they do not establish Dataverse's concurrency guarantees by themselves.

The first tenant experiment rejected Queued-to-Exception inside cancellation. A separate synthetic native probe verified Queued-to-OnHold and restoration. The implementation therefore uses the documented [OnHold state and Paused reason](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/reference/entities/workqueueitem#statecode) for unstarted cancelled items.

## Reproduce the bounded MCP proof

Use an authorized development binding, an isolated registered `mail.v1` synthetic queue, and inactive fixture worker flows. The proof creates one test item and retains its diagnostic history; it does not send email or execute an extraction prompt.

```powershell
$env:QMCP_ENVIRONMENT_BINDING = (Resolve-Path artifacts/live/mcp-binding.json).Path
node scripts/prove_test_cancellation.mjs --execute qmcp-proof-20260912 artifacts/live/new-cancellation-proof.json
```

The evidence file records the run and command IDs before cancellation. After fixing a failure, resume the saved run and request rather than creating another item:

```powershell
node scripts/prove_test_cancellation.mjs --resume qmcp-proof-20260912 artifacts/live/new-cancellation-proof.json
```

The proof requires a persisted Cancelled run, identical command replay, a native OnHold item, and zero processing attempts. Active-worker cancellation and tenant concurrency remain separate validation cases.

Reimporting WQTesting was observed to clear existing testing API plug-in bindings. Verify and repair all testing bindings after import, including existing APIs, before invoking any tool or activating TestCoordinator. `scripts/bootstrap_tenant.py` includes CancelTestRun in its testing package registration plan.
