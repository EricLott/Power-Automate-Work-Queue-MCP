# Authorized retry request proof

The local runtime and MCP adapter require an inspected item version, a bounded reason, and the literal `VerifiedSafe` reconciliation before an operator retry can be sent. The runtime then rechecks queue authorization, current item version, expiry, state, active ownership, safe-effects policy, and attempt limit inside its transaction.

## Reproduction

```powershell
dotnet test tests/runtime/QueueFramework.Tests.csproj --no-restore --filter FullyQualifiedName~QueueFramework.Tests.LifecycleTests
npm test --prefix src/mcp
```

The regression matrix covers missing queue grants (`FORBIDDEN`), active processing (`RETRY_UNSAFE`), unsafe policy (`RETRY_UNSAFE`), stale versions (`VERSION_CONFLICT`), and replaying one request ID without scheduling a second retry. The MCP adapter preserves the expected version and does not accept an agent-supplied role or arbitrary operation.

This proof is local and adapter-level. Native Dataverse authorization under separate identities and the full installed retry transition remain tenant evidence requirements for [P3-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/42).
