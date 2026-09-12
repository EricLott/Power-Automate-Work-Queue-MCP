# Acquisition handoff decision

**Status:** proposed candidate; tenant validation pending

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
