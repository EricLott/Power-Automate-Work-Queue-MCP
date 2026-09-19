# Delayed retry proof wrapper

`prove_delayed_retry.py` provides a resumable, synthetic-only check for the native delayed-retry path. It is deliberately split into two commands so the caller never sleeps inside the proof and can inspect the native queue between scheduling and reacquisition.

The wrapper requires an explicitly bound development binding and a seeded item ledger. It rejects unbound queues, non-UUID items, and mismatched stage evidence before making a tenant call.

## Reproduce

Use a fresh evidence path and an authorized synthetic development fixture:

```powershell
python scripts/prove_delayed_retry.py `
  --binding artifacts/live/mcp-binding.json `
  --fixture-ledger artifacts/live/native-pause-fixture.json `
  --output artifacts/live/delayed-retry-new.json

# Stage the technical retry and record the native delay.
python scripts/prove_delayed_retry.py `
  --binding artifacts/live/mcp-binding.json `
  --fixture-ledger artifacts/live/native-pause-fixture.json `
  --output artifacts/live/delayed-retry-new.json `
  --execute

# After the recorded delay has elapsed, finish in a separate invocation.
python scripts/prove_delayed_retry.py `
  --binding artifacts/live/mcp-binding.json `
  --fixture-ledger artifacts/live/native-pause-fixture.json `
  --output artifacts/live/delayed-retry-new.json `
  --finish
```

The stage asserts a queued synthetic item, a prepared acquisition, native dequeue ownership, `RetryScheduled`, and a non-empty native `delayuntil`. It records `earlyClaimNotProven` until the caller performs the later finish step. The finish re-prepares with the same queue and item, requires native dequeue to return the seeded item, resolves the new attempt, writes one synthetic business record, and completes using the same owned acquisition.

The default invocation makes no tenant calls and creates no evidence file. Existing evidence is never overwritten. A transport failure leaves the evidence incomplete for inspection instead of being reported as a pass.

The reusable wrapper has offline coverage for binding validation, dry-run isolation, stage assertions, and refusal to finish from mismatched evidence. The historical live acquisition proof records delayed retry/reacquisition in the authorized synthetic development tenant; this wrapper's offline tests do not replace that tenant evidence. All flows remain Draft and no mailbox or external destination is used.
