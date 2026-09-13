# Native transition matrix

This is the current evidence map for the native Work Queue lifecycle required
by P0-04 (#15). It separates native item state from framework dispositions.
`DataverseStore.NativeSet` maps `Queued`, `Processing`, `Processed`, `OnHold`
and `Exception` to native state/status values; the mapping is not itself proof
that Dataverse permits every source/destination transition.

| Native transition or boundary | Intended path | Evidence | Status |
|---|---|---|---|
| Queued -> Processing | Native `Dequeue` on an active queue, followed by the acquisition handoff | [acquisition handoff evidence](evidence/acquisition-handoff-2026-09-12.json) records concurrent native claims, one Processing item, an attempt and an acceptance receipt; [direct acquisition evidence](evidence/direct-acquisition-2026-09-13.json) records the no-claim negative | **Observed** |
| Processing -> Processed | `Complete` after a resolved durable acquisition | [contract/completion evidence](evidence/contract-completion-2026-09-12.json) and [acquisition evidence](evidence/acquisition-handoff-2026-09-12.json) record Processed native state and one output per synthetic source | **Observed** |
| Processing -> Exception | Framework `Fail` with an unsafe/terminal disposition, or watchdog recovery after an expired lease | [autonomous runtime evidence](evidence/autonomous-runtime-2026-09-12.json) records lease expiry, one attempt, ReviewRequired and native Exception; delayed retry evidence records the failed attempt as Exception | **Observed for tested paths** |
| Processing -> Queued with future availability | Safe technical retry schedules a delayed retry | [acquisition evidence](evidence/acquisition-handoff-2026-09-12.json) records a RetryScheduled item, an early Dequeue that did not claim it, and later reacquisition after the delay | **Observed for one synthetic delay** |
| Exception -> Queued | Operator `RequestRetry` after reconciliation and an active safe-effects policy | [Stale-worker proof](stale-worker-proof.md) records review, explicit reconciliation, a new generation and successful completion; the delayed retry sequence in [acquisition evidence](evidence/acquisition-handoff-2026-09-12.json) also completed a later generation. The exact native reset is implemented by `NativeSet` without resending a historical delay | **Observed in focused sequences** |
| Queued -> OnHold | Test cancellation of an unstarted item | [cancellation-retention evidence](evidence/cancellation-retention-2026-09-12.json) records the live replay/state checkpoint; the more detailed [cancellation proof](evidence/test-cancellation-2026-09-12.json) records `Outcome: OnHold`, zero attempts, and a cancelled test run | **Observed** |
| Prepared intent + subsequently paused framework policy | Native transition is rejected by the pre-operation guard with wrapped `LIFECYCLE_BYPASS` | [prepared-pause evidence](evidence/prepared-pause-2026-09-13.json) records the prepared request, paused policy boundary, unchanged item state/status/ETag and Pending resolution | **Observed** |
| Prepared intent + native queue Paused | Native queue statecode 1/statuscode 3 rejects Dequeue before item mutation | [native queue pause evidence](evidence/native-queue-pause-2026-09-13.json) records RecordNotActive/Paused, unchanged queued item and zero attempts, then Active restoration | **Observed** |
| Queued item past native expiry | Dequeue must not return an expired item | [Native expiry evidence](evidence/native-expiry-2026-09-13.json) records a past expiry, successful empty dequeue response, unchanged row/ETag and restored original expiry | **Observed on isolated native probe** |
| Processing item past lease/deadline | Watchdog recovery must move the item to a safe exception/review disposition | [autonomous runtime evidence](evidence/autonomous-runtime-2026-09-12.json) proves one installed idle-lease recovery case; deadline-specific behavior and repeated recovery remain untested | **Native transition observed; broader watchdog scenarios remain separate** |
| Native exception-reason variants | Generic, IT, business and processing-timeout reasons | The adapter intentionally maps framework failure/recovery outcomes to native `Exception` (state/status 4). It does not claim or implement a separate native reason-code matrix; those variants are outside the supported transition scope | **Out of supported scope** |

The implementation deliberately keeps framework controls such as
`ReviewRequired`, `RetryScheduled`, `TestFixture` and `OutcomeUnknown` in
framework records. They are not asserted as additional native statuses. The
current adapter also avoids sending a historical `delayuntil` when resetting
an Exception item, because the observed native requeue path validates that
field and requires a future value.

The supported native transition matrix is now evidenced for P0-04. This is not
all possible Dataverse transitions or every failure combination. Deadline-specific
watchdog logic, separate identities, real connectors, load and release upgrades
retain their own issue/gate requirements. Production rejects legacy AcquireNext;
its local-only compatibility paths are not part of this native transition contract.

The [native connector proof](native-connector-proof.md) adds an observed negative: an immediate Processing -> Queued update without future delayuntil is rejected as InvalidArgument. Its isolated probe cleanup used Processing -> Exception -> Queued, with final state read back. The framework's delayed technical-retry path and explicit operator reset from Exception remain distinct supported paths; do not treat every status pair as freely interchangeable.

## Reproducing the expiry boundary

The expiry proof requires an isolated unregistered queue named `qmcp empty native
dequeue probe` with exactly one queued item named `qmcp synthetic native probe`
and empty JSON input. Its explicit fixture contains `queueId` and `itemId`.
It verifies organization and absence of a framework binding, persists the original
row, sets only expirydate to one day before the test, and calls native Dequeue.
An empty successful response and identical expired row/ETag are required.
Restoration uses If-Match and verifies all selected original fields apart from
the expected ETag change. A transport failure cannot pass.

```powershell
python scripts/prove_native_expiry.py --binding artifacts/live/dev-binding.json --fixture artifacts/live/expiry-fixture.json --output artifacts/live/expiry-new.json
# Add --execute only for the authorized synthetic tenant experiment.
```

Default mode makes no tenant calls. The recorded run used runtime baseline
7c2bb88, solution 0.1.0.0, and verified restoration to null expiry. It did not
activate or modify flows, use custom dequeue filters, or create a framework
attempt. Three offline tests cover dry run, successful skip/restoration, and
restoration after a generic dequeue failure. Broader framework expiry recovery
is not inferred from this native eligibility check.
