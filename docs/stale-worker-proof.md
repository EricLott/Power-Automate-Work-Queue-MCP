# Stale-worker ownership proof

The [installed tenant proof](evidence/stale-worker-2026-09-12.json) acquired a synthetic item, failed it to review, explicitly reconciled that no business side effect had occurred, and reacquired it with a new attempt and higher generation. Three concurrent calls with the old ownership and fresh request IDs attempted Complete, Fail and Checkpoint. Each returned exact `STALE_ATTEMPT`.

Independent reads confirmed that the current attempt and item-context rows, including their row versions, remained unchanged. The current worker then completed successfully, and native Processed state plus the actual synthetic business record were verified. No external connector action was executed or cancelled. The test uses one authenticated actor with two ownership generations; separate user/connection authorization remains a different proof.

```powershell
python scripts/prove_stale_worker.py --binding artifacts/live/mcp-binding.json --fixture-ledger artifacts/live/fixture-ids.json --output artifacts/live/stale-new.json --execute
```

The runner requires exactly one queued synthetic input and all seven flows Draft. It retains the synthetic business record and attempt evidence. The initial run incorrectly used a different request ID for ResolveAcquire; its active acquisition was recovered using the original PrepareAcquire request. A regression test now requires paired prepare/resolve IDs and distinct mutation IDs. The narrow `--resume` mode supports only that recorded early resolution failure, before an old attempt ID was persisted. Other failures require current-state inspection before resuming.

## Fresh authorized checkpoint — 2026-09-20

The proof was rerun against the authorized synthetic development queue. Independent readback showed generation 1 replaced by generation 3; concurrent old-generation `Complete`, `Fail`, and `Checkpoint` calls each returned `STALE_ATTEMPT`, while the current attempt/context stayed unchanged. The current worker then completed the item to native `Processed` with one synthetic business record. Redacted evidence is in [stale-worker-2026-09-20.json](evidence/stale-worker-2026-09-20.json). All seven flows were Draft before and after the experiment, and no external destination was used.

This strengthens the stale-worker implementation and evidence path. Separate-identity authorization, disablement recovery, and the broader coordinator/recovery contract remain open.
