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
