# Schema and metadata boundary proof

This checkpoint records the local framework limits used by `qmcp` before a command or native queue payload is accepted. It is an implementation regression record, not a Dataverse platform-limit claim.

## Reproduction

```powershell
dotnet test tests/runtime/QueueFramework.Tests.csproj --no-restore --filter FullyQualifiedName~QueueFramework.Tests.BoundaryTests
```

The boundary tests verify:

- JSON input is measured as UTF-8 bytes and accepts exactly 131,072 bytes but rejects the next multi-byte character.
- JSON reader depth beyond 32 is rejected as `INPUT_INVALID`.
- More than 8,192 JSON descendants is rejected as `INPUT_TOO_COMPLEX`.
- Stable reference fingerprints are canonical, lowercase SHA-256 digests with 64 hexadecimal characters.

The existing runtime limit is intentionally separate from Dataverse metadata behavior. Alternate-key activation timing, native schema dialect support, actual tenant payload ceilings, and any production capacity limit still require an authorized tenant experiment and remain open under [P0-08](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/19).

## Authorized contract and storage metadata checkpoint — 2026-09-20

The read-only [schema metadata evidence](evidence/schema-metadata-2026-09-20.json), produced by `scripts/probe_schema_metadata.py`, observed two installed `mail.v1` contract rows using the draft-07 dialect, the fixed object envelope with three required fields and `additionalProperties: false`, and six relevant Memo attributes with a native `MaxLength` of 1,048,576 bytes. The public API catalog's `DataJson` parameter is exposed as `Edm.String`. The fresh [key evidence](evidence/schema-key-2026-09-20.json) observed all 13 configured keys as Active.

These observations establish the installed development-tenant metadata and storage boundary, not a service request-size or throughput guarantee. Clean-import activation timing and native payload-ceiling testing remain open, so P0-08 is not closed.

## Authorized tenant key checkpoint — 2026-09-19

The read-only [schema/key probe](evidence/schema-key-2026-09-19.json) used the explicit development binding and queried the 13 configured guarded tables plus `workqueueitem`. All 13 tables were present and each exposed exactly one alternate key with `EntityKeyIndexStatus: Active`; no write, key creation, or metadata mutation was performed. The reproducible command is:

```powershell
python scripts/probe_schema_keys.py --binding artifacts/live/mcp-binding.json --output artifacts/live/schema-key-2026-09-19.json --dataverse-cli
```

This proves current key activation for the installed development tenant. It does not prove a clean-import activation wait, native payload ceilings, or managed-production compatibility, so P0-08 remains In Review.
