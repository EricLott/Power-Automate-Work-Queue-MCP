# Coordinator autonomy proof

`scripts/prove_coordinator_autonomy.py` is the bounded tenant probe for the
P5-02 autonomous coordinator path. In execute mode it validates the authorized
synthetic binding, refuses to touch a queue with active rows, temporarily binds
and activates only `ProcessOne`, `SweepQueue`, and `TestCoordinator`, starts one
synthetic service case, observes the coordinator result and receipts, and
restores every changed flow in a `finally` block. It requires a Passed run
whose result has `Cleanup: Completed`. If the installed TestCoordinator is
missing the checked-in `CleanupIfPassed` branch, the probe temporarily repairs
that definition from the repository source and records the repair; the original
installed definition is restored afterward. Intake, event wake-up, Watchdog,
EmailSender, mailbox access, and external destinations are out of scope.

The 2026-09-20 attempt was intentionally read-only after preflight. The shared
synthetic queue contains the retained queued row from the queue-pause proof, so
the probe stopped with `SYNTHETIC_QUEUE_NOT_IDLE`; no flow or queue state was
written and all flow states were already restored. The redacted result is in
[`docs/evidence/coordinator-autonomy-2026-09-20.json`](evidence/coordinator-autonomy-2026-09-20.json).

The isolated 2026-09-20 run passed on a separate synthetic native queue. It
observed autonomous `ProcessOne` / `SweepQueue` processing, a Passed run, and a
coordinator `CleanupTestRun` receipt with `Cleanup: Completed`; postconditions
verified all temporary flows Draft, zero active queue items, and deletion of
the proof-owned business record. The installed Draft coordinator was then
aligned permanently with the checked-in cleanup branch, without activation;
the read-back is in [`coordinator-definition-alignment-2026-09-20.json`](evidence/coordinator-definition-alignment-2026-09-20.json).
The retained queue-pause fixture was not processed or deleted.

After the bounded count assertions were added, the rebuilt packages were
imported into the authorized development tenant and the isolated proof was
repeated. The result passed with `recordCount: 1`, `recordCountBounded: true`,
`unwantedEffectCount: 0`, and `Cleanup: Completed`; the two coordinator
receipts were `Passed`. The native flow path now projects `qmcp_sourcekey` and
`qmcp_testrun` on the business record so the fixed Dataverse evidence query
can observe the same test-owned record written by `ProcessOne`. Redacted
evidence is in
[`coordinator-autonomy-counts-2026-09-20.json`](evidence/coordinator-autonomy-counts-2026-09-20.json).
