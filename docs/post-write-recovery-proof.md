# Post-write recovery proof

`scripts/prove_post_write_recovery.py` runs a bounded authorized synthetic tenant experiment. It enqueues one synthetic item, temporarily shortens only the synthetic queue lease, acquires the item, writes one `qmcp_emailrequest` target row, and intentionally does not call `Complete`. After the lease expires, `RecoverExpiredAttempt` moves the item to `ReviewRequired`; a guarded `RequestRetry` then reacquires it. The runner looks up the target by the persisted business/source key, requires exactly one row, completes using that existing record, and independently verifies native `Processed` state and one target row. The original queue policy is restored with optimistic concurrency in `finally`.

```powershell
python scripts/prove_post_write_recovery.py --binding artifacts/live/mcp-binding.json --fixture-ledger artifacts/live/fixture-ids.json --output artifacts/live/post-write-recovery-new.json --execute
```

The fresh 2026-09-20 result is recorded in [redacted tenant evidence](evidence/post-write-recovery-2026-09-20.json). The first valid target was preserved without duplication, and the review boundary was explicit before retry. The proof uses no sender, mailbox, customer content, or external destination. It demonstrates an abandoned worker/lease boundary, not every connector transport failure or ambiguous multi-row reconciliation case.
