# Power Automate Work Queue Framework

An independent framework for reliable queue-based automation and an MCP development interface. Publisher prefix: `qmcp`.

**Current state:** a credential-free local development candidate. Runtime, simulator, Dataverse adapter, MCP server, solution sources, flow scaffolds, and local tests are implemented. All four unmanaged solutions have imported successfully into the authorized development environment. All 22 live acceptance gates remain pending. This is not a production release.

The installed Dataverse runtime owns processing, attempts, retries, recovery, notifications and initiated tests. Customer solutions own their intake and business worker flows. The local MCP server helps developers build and inspect supported automation; it is outside the production execution path.

- [Build board](https://github.com/users/EricLott/projects/2)
- [Local build and demonstration](docs/local-development.md)
- [Verified local candidate: 91 tests and eight archives](docs/local-evidence.md)
- [Development import results](docs/live-import.md)
- [First import runbook](docs/first-import.md)
- [Implementation decisions and limits](docs/implementation-decisions.md)
- [Local evidence and live gates](docs/validation.md)
- [Proposed architecture v0.1](docs/architecture.md)
- [Tracking agreement and Definition of Done](docs/project-tracking.md)
- [Backlog source](planning/backlog.json)
- [Issue register](planning/issue-map.json)
- [Readable build plan index](docs/backlog-index.md)
- [Planning verification](planning/verification.json)

The user authorized local implementation before tenant access. The local simulator exercises the intended behavior; it cannot prove native dequeue transactions, security, connector metadata, import, or platform throughput. Those remain Phase 0/live gates. The first import uses disabled flows and an explicit bootstrap step to bind actual registered plug-in types.

MVP packages: WQ.Core, WQ.Testing, optional WQ.Notifications.Email, WQ.Reference.SharedMailbox, and local wq-mcp. Deferred capabilities are tracked separately.

```powershell
./scripts/build.ps1
./scripts/test.ps1
```

The build restores pinned public dependencies, compiles the plug-in dependency package, and uses Microsoft's PAC to pack, unpack, and repack managed and unmanaged candidates. It never authenticates to Power Platform. Package ZIPs and their SHA-256 manifest are generated under `artifacts/packages/`.
