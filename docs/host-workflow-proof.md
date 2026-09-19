# Supported host and workflow proof

## First release compatibility decision

The first local release supports an agent host that can launch Node.js 20+ and speak MCP over stdio, including `tools/list`, `tools/call`, `resources/list`, and `resources/read`. The repository's `StdioClientTransport` integration harness is the compatibility reference. Resource injection is not assumed; the host must explicitly discover or read `qmcp://wq/` resources.

The first release does not claim support for a remote hosted MCP service, an HTTP transport, automatic prompt/resource injection, or a host-specific UI integration. Those are separate compatibility work and are not inferred from the local protocol test.

## Clean local workflow

The public MCP integration covers the credential-free path:

1. Inspect the local installation and selected environment.
2. Produce the pinned installation plan.
3. Scaffold a synthetic customer target.
4. Validate its JSON, drift, and static safety result.
5. Plan and provision a synthetic queue.
6. Start a durable test run, close the MCP client, run the independent worker, read evidence from a new session, and clean up test-owned records.
7. Read versioned architecture and flow resources through MCP.

The promotion step is intentionally `not-run`: local evidence cannot establish a tenant import, connection binding, permissions, or activation gate. The development-bound deployment tools require an explicit binding and approved plan hash.

## Verification

`./scripts/build.ps1 -SkipRestore` passed solution generation, plug-in and simulator builds, four unmanaged/managed package round trips, and offline structural checks. `./scripts/test.ps1` then passed:

- 101 runtime tests
- 47 plug-in tests
- 129 offline Python tests
- 38 MCP tests, including the public scaffold/validate workflow and client-disconnect continuation

This is local workflow evidence, not a tenant acceptance claim.

## Current live host checkpoint

On 2026-09-19, `scripts/probe_mcp_session.mjs` connected through the actual MCP stdio transport with the explicit development binding and CLI bridge. It exposed 17 tools, listed 13 resources, read `qmcp://wq/architecture/v0.1` and `qmcp://wq/flow/ProcessOne/v1`, and verified the Dataverse organization through `inspect_installation`; no mutation was performed. The redacted record is [mcp-stdio-2026-09-19.json](evidence/mcp-stdio-2026-09-19.json). This proves the bound host/protocol boundary, not clean installation, flow activation, independent-identity authorization, or full disconnected tenant workflow.

A second live run started a synthetic durable test through MCP, closed the client, reconnected with a fresh MCP session, replayed cancellation, and read the persisted `Cancelled`/`OnHold` result with zero attempts. The redacted record is [mcp-disconnect-2026-09-19.json](evidence/mcp-disconnect-2026-09-19.json). This proves durable MCP-session recovery across disconnect; installed autonomous worker/coordinator continuation remains a separate G20 criterion.
