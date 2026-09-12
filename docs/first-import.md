# First development import

This runbook describes the development import and validation sequence. The [live import ledger](live-import.md) records which steps have actually been executed. Successful import alone does not establish platform transaction behavior or a production-ready release.

## Preparation and import order

1. Choose a disposable development Dataverse environment with native work queues and the required Power Automate licensing. Record its organization ID, platform version, locale, solution versions, and operator identity. Use synthetic messages and a test mailbox.
2. Review `artifacts/packages/manifest.json` and verify all file hashes. Use the **unmanaged** development candidates for the first bootstrap. Import `WQCore.zip`, then `WQTesting.zip`; optionally import `WQNotificationsEmail.zip` and `WQReferenceSharedMailbox.zip`. All generated flows are draft. Do not activate them yet.
3. Retain import logs. Check all companion tables, alternate keys, optimistic concurrency, action parameters, views, roles, app, and the `qmcp_QueueFramework` dependent assembly package. Confirm the package registered `QueueFramework.Plugins.LifecyclePlugin` and `QueueFramework.Plugins.LifecycleGuard`. Resolve metadata/import errors in source, regenerate, and repeat in a clean environment.
4. Create an explicit development binding file outside source control:

```json
{
  "environmentUrl": "https://YOUR-DEV-ORG.crm.dynamics.com",
  "organizationId": "ORGANIZATION-GUID",
  "environmentClass": "development",
  "queueKeys": ["mail"]
}
```

5. Generate a bootstrap plan with `python scripts/bootstrap_tenant.py`. Review its package hashes, API bindings, and guard registrations. When approved during the online phase, supply a short-lived token through `QMCP_DATAVERSE_TOKEN` and run `bootstrap_tenant.py --execute --binding <file> --approved-plan-hash <hash>`. The executor verifies `WhoAmI`, binds actual plug-in type IDs, and registers synchronous PreOperation guards. It does **not** enable flows, grant roles, or create principal profiles. API/step metadata might require adjustment based on the first import; retain those changes in the exported source.
6. Export the resulting unmanaged registration metadata back into source control. Validate a managed export from that development environment separately. The offline managed ZIPs cannot substitute for this bootstrap/upgrade verification.

The bootstrap also supports `--dataverse-cli` with a separately authenticated Microsoft Dataverse CLI profile (`@microsoft/dataverse` 1.0.77). This route uses the CLI's authenticated request command and temporary JSON body files; it does not export access tokens. PAC's `auth token` targets the Power Platform API and is not a Dataverse Web API token. Both bootstrap routes verify the organization ID before writes.

### Read-only metadata preflight

Before bootstrap, an authenticated Dataverse CLI profile can produce a
structural inventory without changing the environment:

```powershell
python scripts/probe_tenant_metadata.py --dataverse-cli `
  --binding C:\path\to\development-binding.json `
  --output artifacts\validation\tenant-metadata.json
```

The utility verifies the development binding with `WhoAmI`, then reads
filtered solution-version, Custom API binding, draft-flow, and guard-step
metadata. It performs no writes and does not establish import, permission,
transaction, connector, or activation success.

## Configure identities and the queue

Create a native queue using the stable envelope in `templates/native-envelope.schema.json`. Do not mutate an existing native schema to introduce a breaking envelope. Create an owner team and record the native queue ID and team ID.

Use separate test identities for producer, worker, reader, retry operator, sender, watchdog, coordinator, and installer. The supplied table roles are initial privilege sets, not a least-privilege certification. Add required base app/native privileges only after an explicit privilege-denial test explains them. Verify team ownership limits direct table access to authorized queues. The test coordinator needs narrowly controlled delete access for the reference test destination; ordinary workers do not.

An administrator creates `qmcp_wqprincipal` rows with `qmcp_key` equal to the Dataverse user/application-user GUID, `qmcp_name`, and a trusted `qmcp_document`, for example:

```json
{"roles":["worker"],"production":false}
```

Only a deployment administrator may change these rows. Missing profiles fail closed; omitted `production` defaults to true. No payload flag grants test authority. A deployment principal then calls `qmcp_WQ_RegisterQueue` with the policy from `config/reference.json`, replacing synthetic IDs and grants, and adding the real `OwnerTeamId`. Register `mail.v1` through `qmcp_WQ_RegisterContract`. Confirm key indexes are active before proceeding.

Every API request uses `QueueKey`, `RequestId` (UUID), and `DataJson` (JSON encoded as a string). Owned mutations also require `ItemId`, `AttemptId`, and integer `Generation`. Operator retries require the current `ExpectedVersion` as a string plus a reason and verified-safe reconciliation. Read operations use the same connector action surface. `ResultJson` must be present and parseable; an empty unbound action response is a failed bootstrap, not success.

## Prove the platform foundation first

Start with native acquisition plus attempt/receipt composition. Capture plug-in traces showing transaction membership. A deployment-only test principal in a non-production profile can temporarily set `proofFault` to `after-dequeue` or `before-receipt` to force rollback. Repeat the exact request ID, verify native/context/attempt/receipt state, and remove the fault setting before normal tests. Production profiles and unsupported fault names are rejected.

Test concurrent requests, the actual empty/dequeue output shape, rollback, lost responses, direct lifecycle writes, delayed eligibility, expiry, queue pause, and stale ownership. The adapter deliberately fails on unsupported response shapes or a missing transaction. Do not weaken those checks to make an import look successful; record and implement a validated alternative if the composition is unsupported.

## Bind and activate the reference

Bind Dataverse, Outlook, and content-conversion connection references to approved development connections. Set queue, native queue ID, test mailbox, and notification destination parameters. Keep the four customer flows in the same solution and verify the child-flow embedded connection requirements.

Replace the explicit `PROMPT_BINDING_REQUIRED` action with the exported action for an approved AI Builder prompt based on `templates/prompt.md`. It must produce the object described by `templates/extraction-output.schema.json`. Store the actual prompt/model metadata available from the provider. Validate the connector schema and run-after references before activation. The local fixture provider is not a live prompt implementation.

Activate a single reference worker after API and guard checks pass, then test event wake-up and scheduled recovery separately. Deliberately fail after the business record is committed but before completion; reconcile the existing source identity and verify that replay creates no second record. Test sender failures independently. Disable the MCP process during an initiated test and verify the installed coordinator still collects evidence.

## Release and rollback

Keep all 22 gates open until their real evidence is linked. Run remote Solution Checker, live security tests, mailbox integration, AI quality repetitions, load/retention tests, clean managed import, and an upgrade preserving customer flows and evidence. Record actual request usage and throughput without extrapolating the local simulator's timing.

For a failed installation, leave flows disabled, preserve import/trace evidence, and repair the development source. For an operating environment, pause new acquisition first, reconcile in-flight attempts, export/back up configuration, and follow a tested solution upgrade/rollback procedure. Uninstalling a solution containing data is not a general rollback strategy.
