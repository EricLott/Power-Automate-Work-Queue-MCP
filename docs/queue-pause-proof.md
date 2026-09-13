# Framework queue pause proof

On 2026-09-12, the installed public PrepareAcquire API returned QueuePaused for a synthetic queued item after QueuePolicy.Enabled was set to false. Independent native reads before and after returned identical state, status and ETag W/"19077864". No acquisition or business write was performed. The original policy was restored and read back equal except for the expected revision increment from 4 to 6.

[Evidence](evidence/queue-pause-2026-09-12.json) records the organization, native item, command IDs, policy versions and synthetic envelope. Runtime baseline: commit 272a911, installed unmanaged solution version 0.1.0.0, PAC 2.12.2 and Dataverse CLI 1.0.77. All seven flows were checked Draft before execution. The seeded item remains queued intentionally.

Reproduce with a fresh evidence path and an explicitly bound synthetic queue:

```powershell
python scripts/prove_queue_pause.py --binding artifacts/live/mcp-binding.json --fixture-ledger artifacts/live/fixture-ids.json --output artifacts/live/pause-new.json
# Add --execute for the authorized tenant experiment.
```

Default mode makes no tenant calls. Five offline tests cover binding checks, dry run, revision comparison, restoration after a lost pause response, and refusal to overwrite a concurrently changed policy. Those restoration faults are simulated, not live transport-fault evidence.

This proves refusal at PrepareAcquire under the framework policy. It does not establish native queue UI pause behavior or the race where a prepared acquisition is paused before native dequeue. Those remaining boundaries stay tracked in #78 and #15; this evidence alone does not close the pause gate.
