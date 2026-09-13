# Development deployment workflow

`scripts/deploy_release.py` plans and applies the pinned unmanaged development candidate. It covers all four explicitly mapped framework packages. Managed upgrades, customer flow deployment, queue provisioning, licensing verification, and activation remain separate release requirements.

The planner verifies package checksums, dependency order, exact connection-reference mappings, the development organization, installed versions, and Draft framework flow states. It binds these observations, settings-file hashes, and registration metadata to `planHash`. It rejects a managed target or a different installed version pending compatibility review.

Create a JSON map with one settings file per package:

```json
{
  "WQCore": "C:/deployment/core-settings.json",
  "WQTesting": "C:/deployment/testing-settings.json",
  "WQNotificationsEmail": "C:/deployment/email-settings.json",
  "WQReferenceSharedMailbox": "C:/deployment/reference-settings.json"
}
```

Use the authenticated CLI profile and an explicit development binding:

```powershell
python scripts/deploy_release.py --binding artifacts/live/mcp-binding.json --settings artifacts/live/deployment-settings.json
```

An authorized operator supplies the reviewed hash and a new UUID. No `approved: true` tool argument is accepted:

```powershell
python scripts/deploy_release.py --binding artifacts/live/mcp-binding.json --settings artifacts/live/deployment-settings.json --execute --approved-plan-hash <reviewed-hash> --request-id <uuid>
```

The executor checks the plan again under a target lock, stages verified package and settings bytes, imports in dependency order, repairs every API and guard registration, and checks installed components. It checks the source inputs between imports and stops if they change. Flows remain Draft. Successful component verification produces `ImportedAwaitingAcceptance`, not a claim that tenant acceptance gates passed.

## Execution records and recovery

`artifacts/deployments/<request-id>.json` is the durable execution record. It includes the organization, plan hash, per-package outcomes and diagnostic log paths, registration results, component observations, and affected solution IDs. These local records and settings stay outside Git.

Reusing the same request ID and inputs returns its existing record without repeating imports. A different plan or changed inputs with that ID is a conflict. Failed imports retain evidence and stop subsequent imports; prior successful imports are not undone. There is no automatic uninstall or activation.

A process interruption can leave a Running record and target lock. Neither file proves that a worker is still alive. Inspect the actual process and tenant import state before recovering; do not restart based only on an observation timeout. After confirming termination, reconcile the partial deployment, remove only that deployment's target lock, and create a fresh reviewed plan with a new request ID. A failed or interrupted request is never silently resumed.

The local CLI uses the operator's authorization boundary. It is not a security boundary against another process with unrestricted access to the same account and filesystem. Production deployment needs the separate approved deployment identity and trusted approval control required by the architecture.

## MCP launch and status

The MCP host configures `QMCP_ENVIRONMENT_BINDING`, `QMCP_DEPLOYMENT_SETTINGS`, and `QMCP_APPROVED_DEPLOYMENT_PLAN`. The last value must equal the reviewed plan hash. `apply_deployment` takes only that hash and a request UUID; tool arguments cannot supply an approval flag or substitute settings paths. The independent Python worker continues after the MCP session closes.

`deployment_status` requires the binding and request UUID. It checks the record's organization and reads either a CLI-started or MCP-started execution. Its `liveState: unknown` is deliberate: a persisted Running record does not prove process liveness. Use actual process/import observations when recovering an interruption. A worker rejected before importing writes a Rejected record; launch failures are recorded separately.

```powershell
$env:QMCP_ENVIRONMENT_BINDING = (Resolve-Path artifacts/live/mcp-binding.json).Path
node scripts/probe_deployment_status.mjs <request-id>
```

The MCP `plan_installation` tool remains a local artifact plan. Use `plan_deployment` for the environment-bound hash; it uses the configured binding and settings and needs no approval to read. Allow up to three minutes for the live CLI metadata queries in the MCP client timeout.
