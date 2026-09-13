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

Tenant execution of the expanded matrix is in progress. Do not treat this document or its local tests as issue closure.
