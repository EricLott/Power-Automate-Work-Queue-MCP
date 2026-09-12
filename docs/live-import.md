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

PAC authentication supports imports and FetchXML reads. The separate Microsoft Dataverse CLI authentication is needed for its direct API request transport; existing browser SSO did not complete that auxiliary sign-in. The prepared bootstrap can use that authenticated CLI or a caller-supplied Dataverse-scoped token. No token is stored in source or logged.
