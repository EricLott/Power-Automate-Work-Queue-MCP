# Tenant capacity profile

`scripts/profile_tenant_capacity.py` runs a bounded, synthetic development-tenant profile. It refuses non-development bindings, non-synthetic queues, more than 25 items, and a queue with existing queued or Processing work. Each item is enqueued, acquired through the PrepareAcquire/native Dequeue/ResolveAcquire handoff, written to the synthetic target table, completed, and read back in native `Processed` state.

The harness counts every Dataverse CLI request by method and route, records wall-clock rate, retries, errors, and throttling observations, and explicitly labels the result as an observation rather than a service or production capacity guarantee.

## Current checkpoint

On 2026-09-19, five synthetic items completed in the authorized development queue. The run observed 37 Dataverse requests (7 GET, 30 POST; 7.4 requests per item), 120.653157 seconds elapsed, 0.041 sequential items/second, zero retries, zero errors, no observed throttling, and five final native `Processed` states. The redacted result is [tenant-capacity-2026-09-19.json](evidence/tenant-capacity-2026-09-19.json).

Reproduce with the authorized binding and ignored fixture ledger:

```powershell
python scripts/profile_tenant_capacity.py `
  --binding artifacts/live/mcp-binding.json `
  --fixture-ledger artifacts/live/native-pause-fixture.json `
  --items 5 `
  --output artifacts/live/tenant-capacity-new.json `
  --execute
```

The run does not measure burst capacity, platform throttling thresholds, retention/storage cost, prompt execution, mailbox intake, or sender delivery. G22 remains open for those broader limits.

## Bounded burst experiment

A separate authorized development-tenant experiment on 2026-09-19 requested five synthetic items at concurrency two. Three items completed before two concurrent `qmcp_WQ_PrepareAcquire` calls returned the redacted `DATAVERSE_CLI_FAILED` harness error. The two remaining synthetic items were reconciled serially through the normal lifecycle path; the final readback showed zero queued and zero Processing items. The result is recorded in [tenant-capacity-burst-2026-09-19.json](evidence/tenant-capacity-burst-2026-09-19.json).

This is a client-bridge/lifecycle-concurrency failure observation, not a Dataverse throttling or platform-capacity result. A follow-up read-only probe showed two concurrent `WhoAmI` calls and two concurrent queue reads succeeding, so the failure is scoped to the concurrent lifecycle burst rather than all CLI concurrency. The experimental concurrent harness was not retained. Capacity evidence therefore remains sequential-only until [follow-up #108](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/108) establishes a supported concurrency-safe transport or documents the boundary.

## Service-protection boundary

The profile intentionally does not probe until throttling. Current [Microsoft Dataverse service-protection guidance](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/api-limits) says to start at a low, consistent rate, increase gradually, and honor the server-provided `Retry-After` interval after a limit error. The documented default values (including 6,000 requests and 1,200 seconds of combined execution time in a five-minute window, with a concurrency limit of 52 or higher per web server) can vary by environment and are not tenant measurements. Any future burst run must have an explicit item/concurrency ceiling, capture `Retry-After` and response headers, stop on the first service-protection signal, and leave the queue drained before it is considered evidence.
