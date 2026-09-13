# Local development

Use Windows with .NET SDK 8.0.400, Node.js 20+, npm, Python 3.12+, and Microsoft Power Platform CLI 2.12.2. The runtime also builds for .NET Framework 4.6.2 for the Dataverse sandbox. The SDK adapter tests run under the installed .NET Framework runtime.

The local tool installer downloads Microsoft's pinned CLI and .NET 10.0.12 runtime into `%LOCALAPPDATA%/qmcp-build-tools`; it does not modify Power Platform authentication profiles. Public dependency downloads require internet access on the first restore. Development and tests need no tenant, mailbox, AI service, or Power Platform credential.

```powershell
./scripts/install-local-tools.ps1  # only when PAC is unavailable
./scripts/build.ps1
./scripts/test.ps1
```

`build.ps1` is the supported full build. It generates deterministic solution sources, builds the C# dependency package and simulator, restores the locked MCP dependencies, and packs four solutions in both formats. It unpacks and repacks each archive, compares contents, verifies published assembly bytes through the embedded package, and checks framework invariants. `test.ps1` runs runtime, SDK adapter, Python structural, and real stdio MCP integration tests. Build outputs and local state are excluded from Git. The GitHub workflow is manual only; it has not been used for this local development run.

## Demonstration

```powershell
python scripts/local_demo.py
```

The demo provisions a synthetic local queue, submits a persistent test run, runs the reference worker in a separate process, reads output evidence, and leaves the local state under `artifacts/demo/`. It uses fixed fixture extraction, not AI Builder. Restarting a client or worker reads the same durable state. Use a new demo state path for a fresh installation.

To start an MCP server:

```powershell
node src/mcp/server.js
```

Configure a stdio MCP host to launch that command from this repository. No installation into a particular agent is required to test the server. Set `QMCP_SIM_STATE` to an absolute file path to isolate local scenarios. Start an independent worker with:

```powershell
dotnet src/simulator/bin/Release/net8.0/QueueFramework.Simulator.dll --worker mail
```

Available tools inspect the installation, plan/provision a local queue, scaffold customer flows, inspect template drift, query queue/item status, start tests, read evidence, and perform scoped cleanup. `plan_installation` is read-only: it checks the pinned local package manifest, artifact hashes, and development binding shape, then reports prerequisites; it never installs packages or performs live tenant verification. `start_test_run` requires a caller-generated UUID request ID; reuse it after an uncertain response. A test returns a run ID immediately; execution belongs to the separate runtime. Scaffolds have their own stable flow IDs and are never overwritten by scaffolding.

For live development, set `QMCP_ENVIRONMENT_BINDING` to a JSON file containing `environmentUrl`, `organizationId`, `environmentClass: "development"`, and a nonempty `queueKeys` allowlist. The default live transport uses the authenticated Microsoft Dataverse CLI profile through a bounded stdin bridge. It does not export access tokens. `WhoAmI` verifies the organization before each operation, and local queue provisioning is disabled in this mode. Existing authenticated CLI access was verified through a real MCP stdio session in the authorized development organization; this identity probe performs no mutations.

```powershell
$env:QMCP_ENVIRONMENT_BINDING = (Resolve-Path artifacts/live/mcp-binding.json).Path
node scripts/probe_mcp_session.mjs
```

The optional HTTP transport requires `QMCP_DATAVERSE_TRANSPORT=token` and an execution-time `QMCP_DATAVERSE_TOKEN`. Both transports enforce the same operation and queue allowlists. Never commit binding files or credentials. Unset the binding variable to return to local simulation.

## Offline validator boundaries

| Check | What it establishes | What it cannot establish |
|---|---|---|
| C# build and locked dependencies | Target compatibility and compile-time correctness | Sandbox loading or Dataverse behavior |
| Runtime tests | State-machine behavior under the explicit local store model | Real transaction isolation or dequeue semantics |
| SDK mocks | Correct request shape, identity, concurrency flags, guard logic | Platform response contracts or permission enforcement |
| PAC pack/unpack/repack | Solution structure accepted by the packager and content preservation | Successful import or dependency activation |
| Source validator | API parameter consistency, ownership fields, bounded loops, child references, no raw native state writes | Power Automate designer/connector compatibility |
| MCP stdio test | Actual protocol connection, persistent test lifecycle, disconnect independence | Real connectors or AI extraction quality |

Microsoft also publishes [XML schemas](https://learn.microsoft.com/en-us/power-apps/developer/model-driven-apps/edit-customizations-xml-file-schema-validation). Its linked archive contains the older **9.0.0.2090** schema set. `check_legacy_xsd.ps1` provides an advisory check after downloading that archive into `artifacts/schemas/`. It catches useful entity/view mistakes, but cannot validate modern cloud-flow JSON, connection references, Custom APIs, or plug-in packages. Its findings must be separated from genuine source errors; it is not a current import validator.

[`pac solution check`](https://learn.microsoft.com/en-us/power-platform/developer/cli/reference/solution#pac-solution-check) uses the remote Checker service. It is deliberately not part of this credential-free offline test run. There is no local Dataverse import engine in this repository.


Read-only live preflight is available separately from the local installation plan:

```powershell
python scripts/preflight_installation.py --binding artifacts/live/mcp-binding.json
```

It checks the pinned local artifacts and reads installed versions, API plug-in bindings, synchronous guard/image configuration, table keys/concurrency, connection mappings, and flow states. `observableComplete` describes those observed components; `ready` remains false while licensing, target privileges, and connection ownership need verification. It neither imports nor activates anything, and it excludes flow clientdata. The local `plan_installation` MCP tool does not yet incorporate this live preflight or apply a deployment.

Use `cancel_test_run` with a stable request ID to cancel pending test results. See [cancellation behavior and tenant proof](test-cancellation.md).


The MCP also exposes `plan_deployment`, `apply_deployment`, and `deployment_status` for the explicit unmanaged development candidate. Planning reads the configured target; apply requires the exact plan hash in host configuration and starts an independent journaled worker. See the [deployment workflow](deployment-workflow.md) for settings, authorization, recovery, and remaining managed-release requirements.
