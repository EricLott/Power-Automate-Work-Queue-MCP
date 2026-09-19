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

## Service-protection boundary

The profile intentionally does not probe until throttling. Current [Microsoft Dataverse service-protection guidance](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/api-limits) says to start at a low, consistent rate, increase gradually, and honor the server-provided `Retry-After` interval after a limit error. The documented default values (including 6,000 requests and 1,200 seconds of combined execution time in a five-minute window, with a concurrency limit of 52 or higher per web server) can vary by environment and are not tenant measurements. Any future burst run must have an explicit item/concurrency ceiling, capture `Retry-After` and response headers, stop on the first service-protection signal, and leave the queue drained before it is considered evidence.
