# Acquisition handoff decision

**Status:** selected handoff; bounded tenant transaction/concurrency/replay validation passed; broader release validation remains open

**Date:** 2026-09-12

## Decision

Workers use `PrepareAcquire`, native Dataverse `Dequeue` bound to `workqueue`,
and `ResolveAcquire`. `PrepareAcquire` commits a stable request intent before
the native action. The queue ID comes from its result. A synchronous stage-40
`workqueueitem` Update handler with a `Before` pre-image (`statecode,workqueueid`)
calls `AcceptAcquire` inside the native update transaction. `ResolveAcquire`
uses the same request ID as `PrepareAcquire` and runs after native Dequeue
success, failure, or timeout. Business processing starts only for
`Outcome == Acquired`; pending, expired, empty, or unresolved outcomes exit
without a business write.

`AcquireNext` remains in the API catalog for compatibility, but the production
plug-in rejects it with `ACQUISITION_HANDOFF_REQUIRED`. `AcceptAcquire` is
restricted to the trusted acquisition post-plugin ancestor; it is not a direct
worker escape hatch. All generated flows remain Draft until tenant binding and
validation are complete.

## Evidence and boundary

The [development import ledger](../live-import.md#runtime-checkpoint) records
that native Dequeue returned a Processing item, while the item Update arrived
in a separate context without the calling lifecycle API ancestor. That is an
observed platform boundary, not evidence that an outer Custom API transaction
includes the native update. The stage-40 post-operation composition above is
the proposed recovery path; atomicity of native claim, `AcceptAcquire`,
attempt/context persistence, and receipt resolution remains unproven until
real tenant traces and rollback evidence are captured.

## Required validation gates

- Capture stage, transaction, depth, initiating identity, parent context, and
  pre-image/target fields for a successful handoff.
- Force failures before and after `AcceptAcquire`, after attempt/receipt writes,
  and after native Dequeue; verify rollback and no orphaned intent or attempt.
- Run concurrent workers against one queue and verify one owner, one attempt,
  and one receipt.
- Lose the flow response at each boundary, repeat the same request ID, and
  verify deterministic `Pending`, `Expired`, `NoAcquisition`, or acquired
  replay behavior without a second claim.
- Verify direct `AcceptAcquire`, malformed Update targets, wrong queues, and
  non-Update contexts fail closed.
- Confirm pre-image registration and connection/action metadata in a clean
  development import, then repeat with the managed upgrade candidate.

These checks are the remaining evidence for G04/G05 and do not follow from
local runtime tests or PAC pack/unpack success.

### Review update — 2026-09-13

The checklist above is the original validation plan, not the current gate status. The [acquisition identity experiment](../acquisition-identity-proof.md) completed G04/G05. The [six-boundary transaction experiment](../transaction-boundary-proof.md) observed transaction True in the native post-operation handler and nested AcceptAcquire, with independent rollback after native claim, attempt, context, consumed intent and receipt persistence. The original outer-Custom-API composition remains rejected; the selected stage-40 handoff now has tenant evidence for its own atomic boundary. Separate-identity, clean-install, managed-upgrade and flow-specific failure checks remain tracked independently.


## Bounded live evidence added on 2026-09-12

The [redacted tenant checkpoint](../evidence/acquisition-handoff-2026-09-12.json) now demonstrates rollback before receipt persistence, one committed claim under two concurrent native calls, repeated receipt resolution, completion replay and delayed retry in the authorized synthetic development fixture. Full fault, identity and deployment matrices above remain release gates.

Request ownership comes from the durable acceptance receipt. An old native call arriving after intent replacement can consume the new intent, but the old request cannot resolve the new receipt. Only the new request can enter business processing. Local tests cover expired unconsumed intent replacement and receipt isolation. An abandoned accepted attempt requires conservative watchdog recovery; raw native output never authorizes business processing. No arbitrary expiry quarantine is assumed to prove a platform duration bound.
