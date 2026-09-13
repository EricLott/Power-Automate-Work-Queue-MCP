# Stale-worker ownership proof

The [installed tenant proof](evidence/stale-worker-2026-09-12.json) acquired a synthetic item, failed it to review, explicitly reconciled that no business side effect had occurred, and reacquired it with a new attempt and higher generation. Three concurrent calls with the old ownership and fresh request IDs attempted Complete, Fail and Checkpoint. Each returned exact `STALE_ATTEMPT`.

Independent reads confirmed that the current attempt and item-context rows, including their row versions, remained unchanged. The current worker then completed successfully, and native Processed state plus the actual synthetic business record were verified. No external connector action was executed or cancelled. The test uses one authenticated actor with two ownership generations; separate user/connection authorization remains a different proof.

```powershell
python scripts/prove_stale_worker.py --binding artifacts/live/mcp-binding.json --fixture-ledger artifacts/live/fixture-ids.json --output artifacts/live/stale-new.json --execute
```

The runner requires exactly one queued synthetic input and all seven flows Draft. It retains the synthetic business record and attempt evidence. The initial run incorrectly used a different request ID for ResolveAcquire; its active acquisition was recovered using the original PrepareAcquire request. A regression test now requires paired prepare/resolve IDs and distinct mutation IDs. The narrow `--resume` mode supports only that recorded early resolution failure, before an old attempt ID was persisted. Other failures require current-state inspection before resuming.
