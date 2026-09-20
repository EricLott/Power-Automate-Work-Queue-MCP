# Orphan reconciliation proof

The runtime watchdog quarantines a native `Processing` item that has no framework item context. The bounded maintenance scan changes the native item to `Exception`, creates a minimal framework context marked `ReviewRequired`, and does not create an attempt or business output. The behavior is covered by `BoundaryTests.WatchdogQuarantinesNativeProcessingItemWithoutFrameworkContext`.

The opt-in tenant utility is [prove_orphan_reconciliation.py](../scripts/prove_orphan_reconciliation.py). It verifies the authorized development organization and synthetic queue, requires all installed flows to be Draft, requires no queued or Processing synthetic work, claims one synthetic item only through native Dataverse `Dequeue`, and invokes `qmcp_WQ_RunMaintenance`. It records redacted native state and framework-row counts; it never calls business processing or an external connector.

The 2026-09-20 live attempt stopped at the idle-queue precondition. The authorized queue still contains the queued synthetic item retained by the queue-pause proof, so no orphan was created and no existing evidence was changed. A tenant acceptance run remains open until that retained fixture is explicitly reconciled or an isolated synthetic queue is authorized.

This proves the local quarantine behavior and defines a safe tenant procedure; it does not prove review metadata for a context-free orphan, bounded multi-page production scanning, separate-identity authorization, or managed-release behavior.
