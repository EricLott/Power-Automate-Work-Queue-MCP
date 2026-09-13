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

## Prepared acquisition boundary

The follow-up tenant experiment passed on 2026-09-13: preparation while enabled succeeded, then disabling the policy prevented the subsequent native dequeue transition. The exact item-specific Dataverse error identified LIFECYCLE_BYPASS. Independent reads found an unchanged native row including ETag, zero attempts, and Pending resolution for the same acquisition request. Policy restoration was verified at revision 12.

The installed pre-operation guard checks Enabled before the post-operation AcceptAcquire handler. Consequently this boundary produces the wrapped LIFECYCLE_BYPASS rejection, rather than the later handler's QUEUE_PAUSED. No runtime behavior was relaxed to pass the test. The parser requires the observed outer code, nested error type, exact item ID and exact message; unrelated failures remain inconclusive.

[All attempt evidence](evidence/prepared-pause-2026-09-13.json) preserves the initial unexpected-fault result, two inconclusive preparation attempts (the diagnosed one returned ACQUIRE_BUSY), the diagnostic guard rejection, and the final pass. The live acquisition cursor was read to establish its expiration before the final attempt. Successful policy restorations advanced revisions; failed preparation made no policy write.

```powershell
python scripts/prove_prepared_pause.py --binding artifacts/live/mcp-binding.json --fixture-ledger artifacts/live/fixture-ids.json --output artifacts/live/prepared-pause-new.json
# Add --execute for an authorized tenant run. Allow any prior acquisition intent to expire.
```

The eight targeted prepared-pause tests passed. The combined pause tooling suite passed 17 tests, including restoration and exact-error parsing. Native queue status pause remains the next check under #78; this experiment uses the framework policy only. The synthetic item remains queued and all flows remain Draft.

## Native queue pause

The final native-status experiment passed on 2026-09-13. With the framework enabled and a fresh prepared acquisition, native Work Queue statecode 1/statuscode 3 rejected Dequeue with the queue-specific RecordNotActive / Paused error. Independent reads verified the item unchanged including its ETag, zero attempts, and Pending resolution. The queue was restored to statecode 0/statuscode 1 and read back. PATCH calls used the observed queue ETag through If-Match.

[Native pause evidence](evidence/native-queue-pause-2026-09-13.json) includes the initial error-discovery run and a subsequent incomplete run whose replayed preparation had expired. Neither counts as a passing run. The final experiment used a fresh preparation request and passed every assertion. Operation IDs on native PATCHes are local evidence labels, not command receipts or replay guarantees.

To reproduce, copy the fixture ledger and add itemId from the earlier queue-pause seed evidence. The script requires this to be the sole queued item in the bound synthetic queue, an enabled matching framework policy, an Active native queue and seven Draft flows.

```powershell
python scripts/prove_native_queue_pause.py --binding artifacts/live/mcp-binding.json --fixture-ledger artifacts/live/native-pause-fixture.json --output artifacts/live/native-pause-new.json
# Add --execute for an authorized tenant run; allow previous acquisition intents to expire.
```

Default mode makes no tenant calls. The exact queue-specific native rejection or a successful empty dequeue response is required; generic failures do not pass. Any incomplete proof exits unsuccessfully. The native pause tests include generic-error restoration, empty-response handling, and exact queue-specific error parsing. Combined with the two framework-policy experiments, the pause scenario is now evidenced. Broader native-transition and acquisition prerequisite reviews remain in #15 and #29.
