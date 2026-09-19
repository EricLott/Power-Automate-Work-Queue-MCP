# Local upgrade procedure proof

The MCP `plan_upgrade` tool now exposes the repository candidate's upgrade policy as a read-only, versioned result. It verifies the local package plan, API prefix/count, registration metadata version, and the explicit recovery policy. The policy requires pausing and draining active attempts before import, retaining incoming source events for reconciliation, keeping one compatible worker version per queue during cutover, and stopping at a failed package while preserving its journal.

The release-review comparison helper also exercises additive transitions: retained package names and dependencies, publisher/prefix identity, and existing API operations must remain stable. New packages and APIs are allowed only when their dependencies and identity rules are valid. Removing a package, dependency, API, publisher, or prefix—or using a non-increasing version—fails closed.

Local verification is intentionally bounded. The result is classified `candidate-only`, carries `tenantImport: not-run` and `tenantValidated: false`, and never presents uninstall/reinstall as rollback. A real development-tenant run must still inspect active attempts and native queue state, perform the managed import and any controlled queue migration, preserve customer flows/evidence, and exercise forward-fix or approved environment recovery. Those acceptance criteria remain open in [P7-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/65) and [G21](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/90).

Evidence source: `src/mcp/test/upgrade.test.js`, the MCP integration test, `config/upgrade-policy.json`, and `config/release.json`. No tenant data, credentials, mailbox content, or deployment result is included.

## Live upgrade-readiness checkpoint

The [2026-09-19 read-only preflight](evidence/upgrade-readiness-2026-09-19.json) matched the authorized development organization and found all four packages at `0.1.0.0` as unmanaged solutions. All seven framework flows were present and Draft, and the observable installation checks completed without unknown reads. Because no managed baseline exists in this environment, no managed upgrade, queue migration, or recovery mutation was attempted. The prerequisite for G21 is an approved environment with a supported managed baseline; this checkpoint does not close G21.
