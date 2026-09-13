# Acquisition transaction boundaries

Issue #13 tracks the remaining transaction experiment for the installed acquisition handoff. The proof must establish the native Update transaction boundary with actual traces and independent persisted-state reads. A locally passing injected exception does not establish Dataverse rollback.

The test hooks cover these ordered boundaries inside the trusted synchronous acquisition path:

| Hook | Work already executed when the exception is raised |
|---|---|
| `after-native-claim` | Native Processing update and trusted post-operation entry; before the acquisition engine runs. |
| `after-attempt` | Attempt Create returned from the organization service. |
| `after-context` | Item context Update returned, including attempt ownership and generation. |
| `after-intent` | Acquisition cursor Update returned with its consumed result. |
| `before-receipt` | Engine completed its acquisition writes; receipt Create has not started. |
| `after-receipt` | Command receipt Create returned. |

New post-write hooks are restricted to `AcceptAcquire`. The existing profile authorization requires a nonproduction actor with the deployment role before any proof hook is enabled. With no proof fault configured, ordinary runtime behavior is unchanged. The post-operation trace contains correlation, transaction state, depth and a GUID-valid request ID; it does not contain queue input or business output.

For every injected failure, the tenant experiment must recognize the exact injected fault, restore the original principal profile, and independently verify a Queued native item, unchanged item context, no persisted attempt, no acceptance receipt and an unresolved prepared intent. Trace evidence must show the actual transaction state and depth. Missing data or unrelated transport errors are inconclusive. Temporary organization tracing must be restored even when the experiment fails.

This matrix tests the selected stage-40 handoff, not the rejected assumption that an outer Custom API automatically owns the native dequeue transaction. Prior concurrency and lost-result checks are recorded in [acquisition identity evidence](acquisition-identity-proof.md). Exhaustive crash recovery, separate-user authorization, connector behavior and clean managed installation require their own evidence.

The fresh package passed eight managed/unmanaged round trips and was pushed to the authorized development environment. The current regression checkpoint is 282 passing tests: 93 runtime, 47 plug-in, 111 Python and 31 MCP. The new tests include proof-hook authorization and scope, the six-case mocked experiment, rejection of missing collections and false transaction traces, and restoration after a failed experiment.

The [installed six-case matrix](evidence/transaction-boundaries-2026-09-13.json) passed on 2026-09-13 UTC. Every case independently retained native Queued state, the original item context and zero attempts/acceptance receipts; resolution remained Pending. Correlated traces show the native post-operation handler at depth 1 and AcceptAcquire at depth 2, both with transaction True. Each case also includes the actual internal INJECTED_PROOF_FAILURE trace, independently fetched again during evidence publication. Principal profile and organization tracing were restored and read back successfully. The synthetic item remains Queued for future controlled tests.

Native Dequeue wraps the exception twice, ultimately reporting an item-update failure containing ACQUISITION_HANDOFF_FAILED. That wrapper alone is insufficient. The script requires the exact known wrapper for this synthetic item, the correlated internal injected-fault trace, and the independent rollback reads. Trace records can appear asynchronously; retrieval retries are bounded. A prepared intent is reused while live, or allowed to expire before a new request identity is created for a later case. No live intent is overwritten to accelerate a test.

The selected native Update plus synchronous AcceptAcquire path therefore has observed atomic rollback at every durable acquisition write boundary. It does not depend on an outer Custom API owning the native dequeue transaction. No partially registered claim survived these failures, so a non-atomic orphan-quarantine substitute is not needed for this selected path. The earlier [identity experiment](acquisition-identity-proof.md) covers deliberately discarded native responses and repeated resolution without a second claim. These observations satisfy the bounded transaction spike in #13; they do not close the remaining separate-user, flow, deployment or release gates.

```powershell
python scripts/prove_transaction_boundaries.py --binding artifacts/live/mcp-binding.json --fixture-ledger artifacts/live/transaction-fixture.json --output-dir artifacts/live/transaction-new --run-id transaction-new
# Add --execute for an authorized synthetic tenant run.
```

The fixture ledger must name the exact retained queued item as queuedItemId, along with the native queue, owner team, principal and actor IDs. Use a new output directory and run ID. The evidence includes the three earlier script-level inconclusive attempts; none is counted as a platform pass. The final matrix run ID is transaction-v4-20260913.
