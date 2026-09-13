# Effective identity and direct-update guard proof

Work item [#16](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/16) remains open. This checkpoint establishes a second effective identity for subsequent authorization experiments and one installed direct-update rejection. It does not establish least privilege or the full create/update/delete matrix.

## Identity check

Initial `WhoAmI` requests with `CallerObjectId` and legacy `MSCRMCallerID` returned the operator identity in this environment. Those results were correctly retained as inconclusive in the [initial preflight](evidence/security-identity-preflight-2026-09-13.json). They do not show that the CLI drops headers or that platform impersonation is unsupported.

A FetchXML query selecting `systemuserid` with the `eq-userid` condition returned exactly the operator without the header and exactly the expected second user with `CallerObjectId`. Microsoft documents [eq-userid as evaluating the calling user's ID](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/fetchxml/filter-rows) and [CallerObjectId impersonation](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/webapi/impersonate-another-user-web-api). The probe checks the expected user's Entra object mapping before accepting this result. A query for a literal expected user ID alone would not establish the request's effective identity.

Run `python scripts/probe_effective_identity.py --binding artifacts/live/mcp-binding.json --caller-object-id <Entra-object-id> --expected-user-id <Dataverse-user-id> --output <new-evidence-path> --execute`. Omit `--execute` for a no-call plan. The script uses existing CLI authentication, performs only reads, and must reject an absent, ambiguous or incorrect effective identity. Raw identity mappings remain in ignored local evidence; publish only the necessary redacted findings.

The [successful effective-identity evidence](evidence/security-effective-identity-2026-09-13.json) records the completed four-read probe using Dataverse CLI 1.0.77.

## Installed guard result

The [direct-update evidence](evidence/security-second-identity-update-2026-09-13.json) records a PATCH of the existing name back to the retained synthetic Queued item `e9c029c3-95e9-4e93-a07d-5d7688b31922` in the registered proof queue. Immediately before the PATCH, an impersonated `eq-userid` query established the second identity. The server returned exactly `LIFECYCLE_BYPASS`. An independent operator read found the selected row and ETag unchanged.

The second identity already has System Administrator and Approvals User roles; no roles were modified. This is evidence that the guard rejects an unauthorized direct update even for that administrator. It is not evidence of restricted table privileges, a separate interactive login, or all security boundaries. Further proof must cover Create/Delete, unrelated synthetic queues, queue reassignment, companion writes and legitimate native dequeue, together with restricted-role identities. Preserve the existing accounts and their role assignments when preparing that work.
