# Coordinator autonomy proof

`scripts/prove_coordinator_autonomy.py` is the bounded tenant probe for the
P5-02 autonomous coordinator path. In execute mode it validates the authorized
synthetic binding, refuses to touch a queue with active rows, temporarily binds
and activates only `ProcessOne`, `SweepQueue`, and `TestCoordinator`, starts one
synthetic service case, observes the coordinator result and receipts, and
restores every changed flow in a `finally` block. Intake, event wake-up,
Watchdog, EmailSender, mailbox access, and external destinations are out of
scope.

The 2026-09-20 attempt was intentionally read-only after preflight. The shared
synthetic queue contains the retained queued row from the queue-pause proof, so
the probe stopped with `SYNTHETIC_QUEUE_NOT_IDLE`; no flow or queue state was
written and all flow states were already restored. The redacted result is in
[`docs/evidence/coordinator-autonomy-2026-09-20.json`](evidence/coordinator-autonomy-2026-09-20.json).

The next tenant action is to provision or nominate a separate isolated
synthetic queue with no retained active rows. The retained queue-pause fixture
must not be processed or deleted merely to make this proof pass.
