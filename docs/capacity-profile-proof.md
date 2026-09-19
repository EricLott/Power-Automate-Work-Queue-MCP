# Local capacity profile proof

The repository now includes `scripts/profile_local_capacity.py`, a bounded synthetic profile for the local simulator. It creates a fresh synthetic queue, enqueues at most 100 fixture items, drains them with the fixture worker, and records enqueue/drain latency, local items per second, native status counts, harness requests, durable command receipts, retry requests, prompt calls, pending sender events, and state-file growth.

Run it only after the normal build:

```powershell
python scripts/profile_local_capacity.py --items 25 --output artifacts/validation/local-capacity-profile.json
```

The output is classified `local-synthetic-capacity-profile`, sets `tenantImport: not-run`, and explicitly sets tenant throughput and cost claims to false. The profile uses no credentials, Dataverse, mailbox, AI, connector, or service-throttling calls. Its polling interval is bounded and applies only to the local harness; it is not a service retry strategy.

The profile is useful for detecting local regressions in bounded work and storage growth. It is not a platform limit, API-request budget, cost estimate, throttling result, or production sizing recommendation. P7-05 still requires an authorized tenant baseline/burst run with service guidance, request usage, retries, prompt usage, storage, sender backlog, and redacted cost assumptions before completion.
