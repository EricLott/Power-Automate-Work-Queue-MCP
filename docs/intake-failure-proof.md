# Pre-enqueue intake-failure proof

The public `qmcp_WQ_ReportIntakeFailure` path accepts a source reference and correlation ID without a native queue item. The framework stores only a stable source hash, correlation ID, bounded failure code and configured notification destinations. Repeating the same logical report with a different command request returns the same `FailureId` and leaves one durable failure row.

The reusable [probe](../scripts/prove_intake_failure.py) verifies the authorized organization, synthetic queue and Draft flow state, then performs two reports with no mailbox, queue worker, sender or business target. It independently checks that the native queue is unchanged, the failure row is singular, the source reference is absent from stored diagnostics, and the notification lookup is policy-consistent.

The authorized synthetic queue currently has zero notification destinations, so the proof observed zero event rows by design. That is not a delivery claim. A native flow alert remains the fallback when Dataverse itself is unavailable, because the framework report cannot be written during a complete Dataverse outage. The redacted result is [intake-failure-2026-09-20.json](evidence/intake-failure-2026-09-20.json).

This evidence does not prove native flow-trigger failure handling, an unavailable Dataverse environment, sender acceptance, recipient delivery, or separate-identity authorization.
