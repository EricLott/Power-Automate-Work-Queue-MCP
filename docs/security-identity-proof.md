# Effective identity and direct-update guard proof

Work item [#16](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/16) remains open. This checkpoint establishes a second effective identity for subsequent authorization experiments and one installed direct-update rejection. It does not establish least privilege or the full create/update/delete matrix.

## Identity check

Initial `WhoAmI` requests with `CallerObjectId` and legacy `MSCRMCallerID` returned the operator identity in this environment. Those results were correctly retained as inconclusive in the [initial preflight](evidence/security-identity-preflight-2026-09-13.json). They do not show that the CLI drops headers or that platform impersonation is unsupported.

A FetchXML query selecting `systemuserid` with the `eq-userid` condition returned exactly the operator without the header and exactly the expected second user with `CallerObjectId`. Microsoft documents [eq-userid as evaluating the calling user's ID](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/fetchxml/filter-rows) and [CallerObjectId impersonation](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/webapi/impersonate-another-user-web-api). The probe checks the expected user's Entra object mapping before accepting this result. A query for a literal expected user ID alone would not establish the request's effective identity.

Run `python scripts/probe_effective_identity.py --binding artifacts/live/mcp-binding.json --caller-object-id <Entra-object-id> --expected-user-id <Dataverse-user-id> --output <new-evidence-path> --execute`. Omit `--execute` for a no-call plan. The script uses existing CLI authentication, performs only reads, and must reject an absent, ambiguous or incorrect effective identity. Raw identity mappings remain in ignored local evidence; publish only the necessary redacted findings.

The [successful effective-identity evidence](evidence/security-effective-identity-2026-09-13.json) records the completed four-read probe using Dataverse CLI 1.0.77.

The [2026-09-19 refresh](evidence/security-effective-identity-2026-09-19.json) repeated the four-read probe in the authorized development environment and again verified organization, operator control, and the distinct effective identity without writes. The user-supplied environment object ID correctly resolved to the operator and was rejected by the probe's `CALLER_DID_NOT_DIFFER` guard. This confirms the probe is fail-closed for a non-distinct identity; it does not establish least privilege or an independent login.

## Installed guard result

The [direct-update evidence](evidence/security-second-identity-update-2026-09-13.json) records a PATCH of the existing name back to the retained synthetic Queued item `e9c029c3-95e9-4e93-a07d-5d7688b31922` in the registered proof queue. Immediately before the PATCH, an impersonated `eq-userid` query established the second identity. The server returned exactly `LIFECYCLE_BYPASS`. An independent operator read found the selected row and ETag unchanged.

The second identity already has System Administrator and Approvals User roles; no roles were modified. This is evidence that the guard rejects an unauthorized direct update even for that administrator. It is not evidence of restricted table privileges, a separate interactive login, or all security boundaries. Further proof must cover Create/Delete, unrelated synthetic queues, queue reassignment, companion writes and legitimate native dequeue, together with restricted-role identities. Preserve the existing accounts and their role assignments when preparing that work.

## Disposable native-table comparison

The subsequent [five-case tenant run](evidence/queue-write-guards-2026-09-13.json) passed with the same verified second effective identity:

| Direct operation | Observed result |
|---|---|
| Create in the registered queue | Exact `LIFECYCLE_BYPASS`; generated item ID absent. |
| Create in the unregistered synthetic probe queue | Item present in the expected queue. |
| Update its name | Updated value independently read back. |
| Move it into the registered queue | Exact `LIFECYCLE_BYPASS`; selected row and ETag unchanged. |
| Delete the unregistered disposable item | Generated item ID independently confirmed absent. |

Run `python scripts/prove_queue_write_guards.py --binding artifacts/live/mcp-binding.json --caller-object-id <Entra-object-id> --expected-user-id <Dataverse-user-id> --queue-key <bound-synthetic-key> --registered-queue-id <native-queue-id> --output <new-evidence-path> --execute`. The queue arguments select the current synthetic registration; the defaults preserve the original 2026-09-12 fixture. The no-execute form performs no tenant calls. The script first verifies effective identity, Draft flow states, exact queue allowlist, native queue names/status and registry membership. It persists new IDs before creating anything. It does not delete historical proof items. Both generated IDs were absent at final cleanup.

The first attempt used `{}` input and was rejected by native envelope validation before guard execution; that did not pass a guard case. The successful run supplied the complete synthetic `mail.v1` envelope. The offline orchestration test checks this prerequisite and exercises the five-case sequence through the CLI response parser; separate tests reject generic failures and false successful denials.

This comparison completes the registered-Create and unrelated-queue CRUD/move portion of the matrix. At that checkpoint, registered Delete, companion writes, restricted-role identities and broader legitimate acquisition authorization remained outstanding in #16. The next section records the subsequent results. No runtime code or user role assignment changed for these experiments.


## Registered deletion and companion writes

The [registered-delete/companion proof](evidence/registered-delete-companion-2026-09-13.json) uses a fresh framework-enqueued synthetic item, never an earlier business or proof item. The Enqueue request ID, native item ID and companion ID are retained. The second identity was verified again with the effective-identity probe before mutations.

Reproduction uses `qmcp_WQ_Enqueue` with QueueKey `qmcp-proof-20260912`, a new RequestId and a complete synthetic `mail.v1` envelope in DataJson. Record the returned ItemId and read its single `qmcp_wqitemcontext` by `qmcp_itemid`. Under the verified second identity, attempt native item DELETE, companion PATCH with the existing `qmcp_document`, companion DELETE, and companion POST with a fresh UUID/key, a synthetic name and `{}` document. Require exactly `LIFECYCLE_BYPASS` for each; generic transport errors cannot pass. Independently reread both retained rows after every rejection and verify native state, companion document hash and both ETags match their before snapshots. Finally query the attempted new companion UUID and require its absence.

The report retains the explicit before and per-case after snapshots, hashing the companion document instead of publishing its contents. The fresh Queued item and companion remain intentionally retained; the denied Create must leave no row. This establishes the tested companion table's direct Create/Update/Delete boundary and registered native Delete under a second administrator identity. Restricted-role behavior, other companion table registrations and the complete legitimate acquisition comparison remain outstanding; #16 stays open.

## Framework role and queue-grant boundaries

The [unregistered-principal check](evidence/unregistered-principal-api-2026-09-13.json) verified that the second effective identity had no framework principal row, then called `GetQueueHealth`. It returned exactly `PRINCIPAL_NOT_REGISTERED`, with no result payload.

The subsequent [temporary-reader experiment](evidence/framework-reader-boundaries-2026-09-13.json) created a new, recorded framework principal for that identity with only the `reader` role. This changed no Dataverse user security roles. With no queue grant, Enqueue returned `FORBIDDEN`, and GetQueueHealth also returned `FORBIDDEN`. The operator then used `RegisterQueue` with the current expected version to add only a reader grant for the synthetic queue. GetQueueHealth returned `Outcome: Health` and 41 items; Enqueue still returned `FORBIDDEN`. Independent command-receipt queries for all three denied requests returned no rows.

The `finally` restoration used `RegisterQueue` to restore the saved policy and then removed the specifically recorded temporary principal. Readbacks verified policy equality apart from its incremented Revision, absence of the temporary profile, and no restoration errors. The result preserves request IDs, the bounded health summary and restoration flags. The profile and queue grant are not left enabled.

To reproduce, first verify a distinct effective identity and absence of its principal and queue grant; require the seven framework/reference flows to be Draft. Save the original policy document and version before creating a test-owned principal. Execute the role-only denial, queue-grant denial, authorized read, and write-denial sequence above. Always restore the saved policy using the current expected version and delete only the newly created principal, verifying both operations independently. Query denied command receipts by SHA-256 of `actorId|operation|requestId`. Retain an inconclusive result if any identity, fault, readback or restoration check fails.

These results establish framework profile and queue-grant enforcement. Native Dataverse least privilege remains unproved because the tested account retains System Administrator privileges. A separate non-administrator Worker/Reader direct-table permission matrix remains required before #16 or G18 can close.

The [2026-09-19 direct-write refresh](evidence/queue-write-guards-2026-09-19.json) repeated the five-case native comparison with the verified distinct identity. Registered-queue Create and move were denied with `LIFECYCLE_BYPASS`; unregistered synthetic Create/Update/Delete were independently verified and cleaned up. No business data, roles, or queue policy changed. This strengthens the cross-queue/direct-write boundary but does not close G18 because the identity retains administrator privileges and the complete role matrix remains open.

The [2026-09-20 direct-write refresh](evidence/queue-write-guards-2026-09-20.json) repeated the same five cases against the current authorized synthetic queue `qmcp-proof-f8283972` after the runner was generalized to accept the bound queue key and native queue ID. The verified distinct identity again received exact `LIFECYCLE_BYPASS` for registered Create and move, while the unregistered synthetic row was created, updated, and deleted with independent readback and cleanup. No business data, roles, or queue policy changed. This is fresh evidence for the guard boundary, not least-privilege proof; #16 and G18 remain open for the restricted-role matrix and remaining Update/Delete coverage.

The [2026-09-20 registered-delete/companion refresh](evidence/registered-delete-companion-2026-09-20.json) reused the processed synthetic item from the post-write recovery proof, so no new retained fixture was created. Under the verified distinct identity, registered native Delete, companion Update, companion Delete, and fresh companion Create each returned exact `LIFECYCLE_BYPASS`; native and companion ETags/document hash stayed unchanged and the generated Create ID was absent. No business data, roles, or queue policy changed. This closes the observed registered-delete and one-companion-table behavior for the tested administrator identity, but does not close #16 or G18 because restricted-role least privilege and the complete role/table matrix remain open.

The [2026-09-19 companion-Create refresh](evidence/all-companion-create-guards-2026-09-19.json) then exercised all 12 configured companion tables. Every direct Create returned exact `LIFECYCLE_BYPASS`, and every generated primary key was independently absent afterward. No cleanup was needed because no row was created. Update/Delete coverage and restricted native privileges remain separate acceptance work.

The [2026-09-20 companion Update/Delete matrix](evidence/companion-update-delete-matrix-2026-09-20.json) completed the corresponding behavioral checks for all 12 configured companion tables using one retained synthetic row per table. Under the verified distinct identity, all 12 Update and all 12 Delete attempts returned exact `LIFECYCLE_BYPASS`; independent reads confirmed every ETag and document hash remained unchanged. Registered native Delete was also denied with the same exact fault. No business data, roles, or queue policy changed. The tested identity remains an administrator, so this advances the observed guard matrix but does not close #16 or G18.

## Every companion Create registration

The [all-companion Create run](evidence/all-companion-create-guards-2026-09-13.json) tested every one of the 12 guarded companion tables listed in `config/registration.json`: definition, queue binding, contract, item context, attempt, command, event, cursor, intake failure, test case, test run and test result. Each direct POST under the freshly verified second effective identity returned exactly `LIFECYCLE_BYPASS`. Independent queries found each generated primary key absent both before and after its attempt. All 12 cases completed; no test row required deletion.

For reproduction, verify the effective identity first. For each configured companion table, generate and record a fresh UUID, require its absence, then POST to its entity set with `<logical-table-name>id` set to that UUID, `qmcp_name` set to a synthetic proof label, `qmcp_key` set to the UUID and `qmcp_document` set to `{}`. Require the exact guard error and independently query the primary key again. Stop on any other fault or successful creation; do not count an input-validation failure as a guard pass. The report records all generated IDs, table names, exact outcomes, configuration hash, tool version and deployed package hash.

This closes the untested-table gap for synchronous companion Create registration. It does not establish all tables' Update/Delete behavior or restricted Dataverse privileges. A targeted read-only search for existing active identities with test/framework-related names returned no candidates; that limited search is not a tenant-wide identity certification. Existing people's administrator roles were not changed to manufacture a least-privilege result.

## Installed registration matrix

The [read-only registration audit](evidence/guard-registration-matrix-2026-09-13.json) verified all 39 expected table/message pairs: Create, Update and Delete for the 12 companion tables and native work queue item. Every step is enabled, synchronous, stage 20, rank 1, with no filtering attributes. Each step's message ID agrees with its message filter, and its filter identifies the expected table. All handlers resolve to the installed `QueueFramework.Plugins.LifecycleGuard` type.

Reproduce by reading the named `Queue framework guard:` processing steps, retrieving their referenced message and message-filter rows by ID, and comparing the resulting pairs with `config/registration.json`. Also retrieve the handler plug-in type by ID and verify its type name. Require exactly the expected set and count, rather than accepting only a total of 39. A filtered step or a mismatched message/filter/handler must fail this check.

This evidence rules out missing, disabled or misbound registrations within the audited set. It proves configuration, not successful execution of every Update/Delete case. The behavioral results above remain scoped to the operations actually invoked; native non-administrator permission testing remains separate.

## Role-assignment inventory — 2026-09-20

The read-only [authorization role inventory](evidence/authorization-role-inventory-2026-09-20.json)
queried the authorized development tenant's installed WQ role definitions and
assignments. All eight unique WQCore/WQTesting Worker/Reader role names had zero
assignments. The two explicitly verified identities were read back only as
administrator-role summaries; neither is suitable restricted-role evidence.
No user roles, queue grants, principals, or business data were changed.

This is a reproducible prerequisite finding, not a least-privilege pass. Follow-up
[#112](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/112)
tracks provisioning or nomination of a dedicated non-administrator development
identity before the remaining native role matrix can run.
