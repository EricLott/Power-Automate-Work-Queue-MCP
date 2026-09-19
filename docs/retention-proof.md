# Bounded retention and maintenance proof

Queue policy contains independently validated windows for payloads, receipts/replay, attempts, errors and test evidence. The current safe implementation acts on the first two: an old terminal payload is replaced with `{}`, while an old command receipt becomes a `ReplayExpired` tombstone that retains request identity and prevents replay execution. The remaining attempt/error/evidence classes are explicitly protected until a separate cascade policy is validated.

Retention runs inside the runtime command boundary, uses bounded native and command pages, and preserves active attempts, review-held items, ordinary `OnHold` work, test evidence and attempt history. A concurrent or stale policy update is rejected by the existing queue-policy version check. Invalid or out-of-range retention windows fail closed as `POLICY_INVALID`.

Local regression coverage is in `tests/runtime/RetentionPolicyTests.cs`, `tests/runtime/CancellationTests.cs`, and the existing cleanup/CAS tests. It verifies independent payload/receipt windows, replay tombstones, deduplication identity, review holds, active work and cancellation preservation. A real tenant run is still required for native aged-row behavior, scheduler execution, storage cost, and managed-release compatibility; P7-04 remains open until those acceptance criteria are observed.
