# Development import ledger

The user authorized full writes in a supplied development environment on 2026-09-12 and requested autonomous troubleshooting. PAC authentication and the supplied organization/environment IDs were verified before writes. This environment already contains other solutions; the run is not evidence of a pristine-tenant install. Work is tracked in [P0-06 / issue 17](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/17).

## Core result

The unmanaged **WQCore 0.1.0.0 import succeeded**. Follow-up PAC FetchXML reads found the solution, both `QueueFramework.Plugins` types, and 16 Core Custom APIs. The Watchdog flow remains **Draft**. The API definitions still require implementation binding and guards still require registration before runtime validation.

The successful candidate is retained locally as `artifacts/live/WQCore-07.zip`, with the PAC result in `artifacts/live/core-import-07.log`. Target identifiers, connection settings and full import reports remain in ignored local artifacts. No customer business data was processed.

## Additional package results

The unmanaged **WQTesting 0.1.0.0**, **WQNotificationsEmail 0.1.0.0** and **WQReferenceSharedMailbox 0.1.0.0** imports also succeeded. Follow-up reads verified all four solution versions and all seven flows in Draft state. Twenty Custom API definitions are present across Core and Testing. Their existing Dataverse/Outlook connection references were supplied through ignored deployment settings. No sender was activated and no email was sent.

## Regression verification

After the import corrections, the full local suite passed: **94 tests** (58 runtime, 8 plug-in adapter, 18 Python, 10 MCP/operator). All eight managed/unmanaged archives were rebuilt and passed PAC pack/unpack/repack and source/archive validation. These local checks do not replace tenant runtime proof.

## Import-driven corrections

| Reported failure | Correction and observed result |
|---|---|
| SourceControlHandler could not append a node from a sharded component | Omitted XML declarations in generated XML; subsequent import progressed to views. |
| Saved-query import raised a null reference | Added exported view managed-property, quick-find, privacy and version metadata; subsequent import passed views. |
| Plug-in package binary not found | Placed the NuGet file under `pluginpackages/<name>/package/<file>`; subsequent import registered the plug-in package. |
| ModernFlow Watchdog raised a null reference | Added exported workflow metadata, corrected `AsyncAutodelete` casing, used an empty template name and supplied an existing connected Dataverse connection reference. Subsequent import passed this stage. |
| Operations sitemap name was empty | Added `SiteMapName`; the complete Core import succeeded. |

Source checks now cover these required fields and the corrected binary path. `inspect_import_report.py` summarizes failed component results from PAC importjob output. Queries passed to `pac env fetch` use XML files and omit `top`, because PAC adds paging.

## Remaining evidence

Successful component import is partial evidence only. API invocation, key activation, transaction rollback/concurrency, lifecycle guards, separate-identity authorization, real connector execution, managed upgrades and all other acceptance criteria remain pending. No live acceptance gate is closed by this result.

Dataverse CLI device authentication subsequently succeeded, and its `WhoAmI` result matched the authorized organization. The direct transport requires `/api/data/v9.2/` in its request path. API binding uses the case-sensitive `PluginTypeId` navigation property; message filters use the table logical name in `primaryobjecttypecode`. The bootstrap now follows those observed contracts. No token is stored in source or logged.

## Runtime checkpoint

All 20 Custom APIs were bound to the installed lifecycle plug-in. A live call without a registered principal correctly returned `PRINCIPAL_NOT_REGISTERED`. [Table metadata evidence](evidence/tenant-metadata-2026-09-12.json) confirms all 14 alternate keys Active, optimistic concurrency enabled, and the intended ownership types.

A synthetic owner team and native queue were provisioned. Dataverse rejected queue ownership while the team had no read privilege; assigning the framework's scoped Reader roles resolved that prerequisite. No members were added to the team. A non-production framework principal profile was created for the authenticated development operator.

The initial `RegisterQueue` call was rejected as `LIFECYCLE_BYPASS`: a SharedVariables marker was not visible in the parent context. Admission now verifies the registered lifecycle handler, exact operation, synchronous transaction context and initiating identity instead of relying on that marker. Subsequent live `RegisterQueue`, `RegisterContract` and `Enqueue` calls succeeded. Repeating the same enqueue command returned the same item result.

Native dequeue exposed a separate boundary. An unregistered synthetic queue successfully returned a Processing item, but acquisition on a registered queue was denied by the guard. Its item Update arrived in a separate context without the calling lifecycle API ancestor. The proposed outer API transaction therefore has not demonstrated atomic dequeue, attempt creation and receipt persistence.

The next candidate uses a committed acquisition intent, standard native dequeue, a synchronous item Update post-operation handler that accepts the acquisition, and receipt resolution before business processing. This candidate is under implementation and security review; it has not yet passed tenant validation. Rollback, concurrent calls and lost-response recovery remain open gates. All seven flows remain Draft. Exception-only plug-in tracing was temporarily enabled for the investigation; its prior setting is retained locally for restoration.

The handoff candidate passed **121 local tests** (67 runtime, 21 plug-in adapter, 23 Python and 10 MCP/operator), and all eight archives passed the packaging round trip. Coverage includes acquisition intent expiry/identity checks, direct and forged-handler admission rejection, receipt queue isolation and rejecting a changed intent version. These are local checks; they do not establish the proposed native transaction boundary.


## Guarded handoff and recovery proof

The next bounded development run succeeded. All 23 Custom APIs are bound; 39 pre-operation guards and one acquisition post-operation step with its pre-image were registered. Native core adds `processinguser` and `processingstarttime` after pre-operation admission, so the two guards intentionally validate different observed field sets. Nested companion writes retain the registered post-handler ancestor but omit the nested API ancestor; authorization is restricted to the four acquisition persistence writes.

[Redacted proof evidence](evidence/acquisition-handoff-2026-09-12.json) records:

- A forced failure before receipt persistence rolled back the native claim and attempt. Both candidate items remained Queued with zero attempts and acceptance receipts.
- Two concurrent native dequeue calls against one prepared intent committed exactly one Processing item, attempt and acceptance receipt. The other item remained Queued. Repeated resolution returned the identical result.
- A business record written before a completion failure was reconciled and reused during recovery. The item finished Processed without a duplicate record.
- Safe automatic retry transitioned directly from Processing to Queued with a future delay while closing the failed attempt as Exception. An early dequeue left it unclaimed; a later claim used a higher ownership generation and completed.
- Final reads found three Processed synthetic items, five attempts and three distinct business records. The injected principal fault was removed and the original organization tracing setting restored.

Native transition troubleshooting established that resending historical `delayuntil` during completion invokes requeue validation. Delayed requeue also requires an initial Processing state. The adapter now omits delay for terminal transitions and immediate operator resets; automatic retry performs the delayed Processing-to-Queued transition directly.

The final local suite passed **140 tests** (72 runtime, 35 plug-in adapter, 23 Python, 10 MCP/operator). All eight archives passed the build and PAC round trip. The corrected plug-in package was pushed successfully. The reference solution reimport and publishing also succeeded; a subsequent read verified that ProcessOne remains Draft and uses PrepareAcquire, native Dequeue and ResolveAcquire. The post-operation step and pre-image were verified again. See the [reproduction procedure](acquisition-proof.md) for the parameterized CLI proof utility.

These results are selected synthetic single-operator experiments. They do not close the full rollback/failure matrix, separate-identity authorization, real flow/mailbox/prompt execution, clean installation or managed upgrade gates. All 22 acceptance gates remain open. Earlier sections retain their historical checkpoint results.

The committed parameterized proof was subsequently executed against the freshly deployed package and passed the full focused sequence again. Its redacted repeat observations are included in the same evidence file. This adds two Processed synthetic items and three attempts; it does not broaden the acceptance scope.


## Harness malformed-input checkpoint

Luna review found null test cases and fields could trigger an unhandled exception. The corrected API returns `INPUT_INVALID` for null case arrays, case entries, input, expected values and IDs. All five cases were tested through the public Dataverse API after the fresh package push; test runs remained zero and the five synthetic queue items were unchanged. [Redacted evidence](evidence/harness-input-2026-09-12.json) records the API outcomes and the **141-test** local regression result. All eight archives passed the final build round trip. This validates malformed-input rejection, not production isolation or autonomous coordinator execution.
