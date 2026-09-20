# Concurrent sender proof

The sender claim is protected by the persisted event row's optimistic version. Two simultaneous public `ClaimEvent` calls against one eligible synthetic event produced exactly one `Claimed` result and one public `VERSION_CONFLICT` result. The losing request did not receive a delivery lease, so concurrent senders cannot hold the same active lease.

The winning lease was finished with the controlled code `SYNTHETIC_CONCURRENT_MAIL_OFFLINE`. The response was `Pending`, the retry count advanced from one to two, and the event remained durable for later retry. The event had no native item reference because it was an intake-failure notification; no business/native mutation was expected. No connector, mailbox, recipient, or external destination was contacted.

The reusable [probe](../scripts/prove_concurrent_sender.py) verifies the authorized organization, synthetic queue, Draft flow state, persisted sender cursor, one eligible synthetic event, the two concurrent claims, the safe loser outcome (`NoWork` or `VERSION_CONFLICT`), controlled finish, and final event state. The redacted result is [concurrent-sender-2026-09-20.json](evidence/concurrent-sender-2026-09-20.json).

This closes the concurrent active-lease criterion for the synthetic development path only. Connector acceptance, recipient delivery, complete Dataverse outage behavior, external identity separation, and production-scale contention remain separate evidence.
