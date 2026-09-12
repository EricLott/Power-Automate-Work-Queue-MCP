# Local candidate verification — 2026-09-12

The credential-free candidate passed **91 tests**: 58 runtime, 8 Dataverse SDK adapter, 15 Python offline, and 10 MCP/operator tests. The three-repetition synthetic demonstration also passed. No Power Platform credentials, live import, connector execution, or remote Solution Checker were used.

The [machine-readable record](evidence/local-2026-09-12.json) contains test names, tool versions, package hashes, structural results, and log hashes. Raw logs and test evidence remain in the local `artifacts/` directory. ZIP timestamps can change between builds; use each build's generated manifest for deployment review.

## Reproduce

```powershell
./scripts/build.ps1
./scripts/test.ps1
python scripts/local_demo.py
```

The recorded final build used `-SkipRestore` after pinned dependencies had already been restored. See [local development](local-development.md) for prerequisites and the optional legacy XSD advisory.

## Verified locally

- Four packages, each in managed and unmanaged form, passed PAC pack/unpack/repack and content comparison: eight archives total.
- Published plug-in/dependency assembly bytes match the package embedded in the Core solution. Fresh packaging prevents stale incremental NuGet artifacts from being reused.
- Regeneration preserved all 271 inspected source/configuration files byte-for-byte.
- Runtime tests cover command replay, source conflict, ownership fencing, retries, recovery after a business write, bounded scans, notification isolation, evidence requirements, and scoped cleanup.
- The actual stdio MCP integration starts a persistent test run, closes its client/server, runs a separate worker, and reconnects to inspect completed evidence.
- Bootstrap and Dataverse transport tests reject wrong environments before mutations. They use fake transports, not tenant calls.

GPT-5.6 Luna agents reviewed packaging, runtime/SDK handling, and MCP/operator boundaries. Integration fixed malformed command error handling, request validation, set-order normalization during PAC round trips, and stale plug-in packaging.

## Scope still requiring the online phase

All [22 acceptance gates](validation.md) remain open. The next stage is the [first development import](first-import.md): actual API/guard registration, native dequeue transaction experiments, privileges/team ownership, connection references, child-flow bindings, and an approved AI Builder prompt. Generated flows are draft, and the prompt action deliberately fails until its provider binding is supplied. The local extractor is a synthetic fixture.

The older Microsoft XSD advisory reports unsupported `JsonFileName` and `connectionreferences` elements in each package. This is recorded as a legacy-schema limitation, not a passed current import validation. Managed import/upgrade, live AI quality, real mailbox behavior, and capacity measurements have not been demonstrated.
