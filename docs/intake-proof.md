# Intake duplicate and content-conflict proof

The installed `qmcp_WQ_Enqueue` accepted a synthetic envelope, returned the same native item for a second request with identical source/key/content, and rejected changed content with exact `KEY_CONTENT_CONFLICT`. Native reads before and after confirmed one Queued row and identical stored input hashes. [Evidence](evidence/intake-duplicates-2026-09-12.json) includes request IDs and the installed runtime evidence reference.

Run with an existing authenticated Dataverse CLI profile and a development binding containing an explicitly allowlisted synthetic queue:

```powershell
python scripts/prove_intake_duplicates.py --binding artifacts/live/mcp-binding.json --queue-key qmcp-proof-20260912 --output artifacts/live/intake-new-proof.json --execute
```

Each run persists its request IDs before mutation and requires a new evidence path. It retains the synthetic queued item without executing business work. Only the exact framework conflict error is accepted; authentication, timeout, extra native items or changed stored input fail the proof. Offline fault-injection tests verify those evidence checks.

This proves sequential enqueue deduplication and conflict rejection at the public API boundary. Concurrent submissions, the real mailbox trigger, and extraction quality require their own evidence. Gate issues #71/#72 retain their prerequisite review.

## Concurrent submissions

A second tenant run used `--concurrent` to submit the same source and content with two distinct request IDs from parallel clients. Both returned normally: one `Enqueued`, one `Existing`, with the same native item. The changed-content request again returned `KEY_CONTENT_CONFLICT`; native reads confirmed one Queued item and unchanged stored input. [Concurrent evidence](evidence/intake-concurrent-2026-09-12.json) includes all request IDs.

The runner permits one exact-request retry after an ambiguous CLI failure, but this run needed no retry. It does not establish forced uniqueness-collision rollback: simultaneous client dispatch does not guarantee both server transactions read the absent key before either commits. Add `--concurrent` to the reproduction command with a new output path. Seven offline proof tests cover normal evidence, concurrent count checks, changed input, extra rows, accepted conflicts, and transport failures.
