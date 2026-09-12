# Power Automate Work Queue Framework

An independent, proposed framework for reliable queue-based automation and an MCP development interface. Publisher prefix: `qmcp`.

**Current state:** design and project planning only. No runtime implementation or tenant validation is complete.

The installed Dataverse runtime owns processing, attempts, retries, recovery, notifications and initiated tests. Customer solutions own their intake and business worker flows. The local MCP server helps developers build and inspect supported automation; it is outside the production execution path.

- [Build board](https://github.com/users/EricLott/projects/2)
- [Proposed architecture v0.1](docs/architecture.md)
- [Tracking agreement and Definition of Done](docs/project-tracking.md)
- [Backlog source](planning/backlog.json)
- [Issue register](planning/issue-map.json)

Start with Phase 0: prove native acquisition, transaction boundaries, concurrency, request replay and recovery after a successful business write. Platform-dependent behaviors remain validation gates until supported by tenant evidence.

MVP packages: WQ.Core, WQ.Testing, optional WQ.Notifications.Email, WQ.Reference.SharedMailbox, and local wq-mcp. Deferred capabilities are tracked separately.
