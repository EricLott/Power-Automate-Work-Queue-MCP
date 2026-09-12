# Validation ledger

Local implementation is tracked in [LOCAL-01 / issue 106](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/106). The local suites test the implemented model, adapters, protocol, and package structure. They do not close tenant gates. Reproduction commands are in [local development](local-development.md); raw results are generated under `artifacts/test-results/` and `artifacts/validation/`.

The [2026-09-12 local evidence record](local-evidence.md) includes historical test counts; the latest checkpoint has 152 passing tests and eight successful package round trips, with versions, hashes, and explicit limitations.

## Gate mapping

Every gate below remains **open**. Selected synthetic tenant evidence is recorded in the [import ledger](live-import.md), including native handoff/recovery and installed autonomous Watchdog/coordinator execution; it does not satisfy every gate criterion. “Local coverage” describes an executable check or an artifact, not a gate pass.

| Gate | Local coverage | Remaining live evidence |
|---|---|---|
| [G01 Clean install](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/70) | PAC pack/unpack, metadata/catalog checks, bootstrap plan | Import, key activation, API binding, app and connection checks |
| [G02 Intake duplicate](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/71) | Stable deduplication and long mailbox identity tests | Native unique-key behavior with real intake |
| [G03 Intake conflict](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/72) | Content mismatch rejected without another item | Actual native/companion conflict and diagnostics |
| [G04 Acquisition concurrency](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/73) | Concurrent local acquisition and SDK dequeue request tests | Real isolation and transaction composition |
| [G05 Acquisition replay](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/74) | One persisted result for repeated request | Lost Dataverse response, rollback, retry |
| [G06 Completion replay](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/75) | One completion/outbox intent | Connector timeout after server commit |
| [G07 Delayed work](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/76) | Clock-controlled delay/retry test | Native delay eligibility plus scheduled discovery |
| [G08 Missed wake-up](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/77) | Detached worker and sweep structure | Disable event parent and observe scheduled backlog recovery |
| [G09 Paused queue](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/78) | Policy pause prevents acquisition | Native pause behavior and policy interaction |
| [G10 Unsupported payload](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/79) | Schema, size, duplicate JSON, poison-item tests | Native draft-3 envelope and real connector mapping |
| [G11 Post-write failure](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/80) | Existing output reused after a forced crash | Real Dataverse write followed by lost completion |
| [G12 Stale worker](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/81) | Complete/fail/checkpoint generation and expiry tests | Parallel flow executions and connector side-effect boundary |
| [G13 Unknown outcome](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/82) | Review hold and guarded operator retry | Recovery with real external uncertainty |
| [G14 Notification failure](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/83) | Business state independence, delivery fencing, scan progress | Outlook failure/timeout/acceptance evidence |
| [G15 Test isolation](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/84) | Production denial, scoped cleanup, rollback/hold tests | Separate identities, production destinations denied |
| [G16 Test evidence](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/85) | Output read, expected fields, errors, attempts, notifications | Authorized reads through the installed coordinator |
| [G17 AI extraction](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/86) | Output schema, versioned prompt, repeated fixture runs | Approved live AI Builder prompt and quality evaluation |
| [G18 Authorization](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/87) | Role/queue denial, caller identity, environment binding tests | Native/table/team privileges under separate real identities |
| [G19 Lifecycle bypass](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/88) | SDK guard tests and flow bypass lint | Direct writes and all registered pipeline paths |
| [G20 Agent disconnect](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/89) | Actual stdio host shutdown and detached runtime completion | Installed flows/coordinator continue without MCP |
| [G21 Upgrade](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/90) | Stable generated component IDs, customer isolation, state reload | Managed upgrade preserving data, registration and customer flows |
| [G22 Capacity](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/91) | Bounded loops/pages, concurrent model regression | Measured tenant throughput, throttling, request budget and retention |

## Evidence requirements

For a live run record the commit/package hash, environment and platform version, identity/role, case ID, request/run/item/attempt IDs, expected outcome, actual outcome, and an authorized evidence reference. Redact mailbox content and credentials. A failure, permission denial, missing output, or timeout cannot be turned into a pass. Preserve the original expected results when repeating AI evaluations.

The first build intentionally retains tenant uncertainty: dequeue transaction boundaries and response shape; queue state transitions; role and team ownership behavior; first import metadata; prompt/connector binding; child flow deployment; and managed upgrade behavior. The [first import runbook](first-import.md) orders those experiments before production activation.
