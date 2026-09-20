# Outbox coordination proof

The sender path claims a durable event with a lease, records a controlled non-acceptance, and leaves the event `Pending` for a later retry. The business/native item remains unchanged. The proof uses the retained synthetic event from the completion-response evidence and the destination `qmcp-synthetic-outbox-proof`; it does not contact a connector or recipient.

The reusable [probe](../scripts/prove_outbox_coordination.py) verifies the authorized organization, synthetic queue and Draft flow state, requires exactly one pending synthetic event, calls `qmcp_WQ_ClaimEvent`, calls `qmcp_WQ_FinishEvent` with a synthetic offline code, and independently reads the final event and native item. The redacted result is [outbox-coordination-2026-09-20.json](evidence/outbox-coordination-2026-09-20.json).

The live result was `Claimed` followed by `Pending`; the event attempt count advanced to one and the controlled error was retained. This demonstrates durable retry-state preservation, not connector acceptance, recipient delivery, concurrent sender contention, or behavior during a complete Dataverse outage.
