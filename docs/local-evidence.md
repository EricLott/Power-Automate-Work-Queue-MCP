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

All [22 acceptance gates](validation.md) remain open. The next stage is the [first development import](first-import.md): actual API/guard registration, native dequeue transaction experiments, privileges/team ownership, connection references, child-flow bindings, and an approved AI Builder prompt. The [acquisition handoff decision](decisions/2026-09-12-acquisition-handoff.md) records the proposed post-operation composition and its unproven atomicity gates. Generated flows are draft, and the prompt action deliberately fails until its provider binding is supplied. The local extractor is a synthetic fixture.

The older Microsoft XSD advisory reports unsupported `JsonFileName` and `connectionreferences` elements in each package. This is recorded as a legacy-schema limitation, not a passed current import validation. Managed import/upgrade, live AI quality, real mailbox behavior, and capacity measurements have not been demonstrated.


## Subsequent handoff regression checkpoint

After native transition corrections, **140 local tests** passed: 72 runtime, 35 plug-in adapter, 23 Python and 10 MCP/operator. The fresh build passed all eight archive round trips. [Live synthetic evidence](evidence/acquisition-handoff-2026-09-12.json) supplements these checks; all acceptance gates remain open. Earlier counts above describe historical runs.

The subsequent test-harness null-input correction passed **141 tests** (73 runtime, 35 plug-in adapter, 23 Python and 10 MCP/operator) and all eight package round trips. Explicit null cases, inputs, expected objects and IDs return `INPUT_INVALID` before any test-run or queue writes.

The connector-host serialization correction and read-only MCP installation planner passed **147 local tests** (73 runtime, 35 plug-in, 25 Python, 14 MCP) and eight archive round trips. The [installed autonomous runtime proof](evidence/autonomous-runtime-2026-09-12.json) separately demonstrates one synthetic scheduled recovery and assertion sequence.

The final output-evidence adapter and webhook correction passed **152 local tests** (73 runtime, 39 plug-in adapter, 26 Python, 14 MCP) and eight archive round trips. The new installation tool is also called through the actual stdio MCP integration test. Live positive field assertions and scoped cleanup are [recorded separately](evidence/positive-coordinator-2026-09-12.json).


## Cancellation and authenticated CLI transport

The latest suites pass 175 tests: 84 runtime, 40 SDK adapter, 34 Python, and 17 MCP tests. Coverage includes cancellation receipt replay, active-attempt preservation, denied retry, injected version conflicts, authenticated CLI identity/queue boundaries, and conservative preflight reporting. See [the cancellation evidence](evidence/test-cancellation-2026-09-12.json) for the separate live result. Local conflict injection is not a native concurrency proof.

## Development deployment and cancellation retention checkpoint

The hash-bound deployment worker imported all four unmanaged development packages, repaired registrations, and passed all observable post-import component checks. The journal returned `ImportedAwaitingAcceptance`, with affected solution IDs and all seven flows still Draft. [Evidence](evidence/deployment-2026-09-12.json) records the pinned hashes and remaining manual prerequisites. This is not a clean managed installation or managed upgrade proof.

A subsequent retention fix permits expired cancelled OnHold inputs to be redacted while preserving identity and cancellation results. Recent inputs, review holds, active work, and ordinary OnHold items remain protected. All 198 local tests passed (88 runtime, 40 SDK adapter, 42 Python, 28 MCP), as did eight archive round trips. The updated plug-in package was pushed successfully; repeating the existing MCP cancellation request preserved Cancelled/OnHold, zero attempts, and identical replay. Aging was simulated locally; native aged-retention behavior remains to be tested.

## Installed AI reference checkpoint

The generated reference worker now uses an explicitly bound Dataverse Predict model, validates extracted JSON and sender identity, reconciles output, and retries uncertain completion with identical command parameters. The fresh build and eight package round trips passed; 223 local tests passed (91 runtime, 40 SDK adapter, 61 Python, 31 MCP). These counts precede the separately developed repeated-quality proof script.

[The installed reference test](reference-prompt-proof.md) passed one synthetic scheduled run with independent native/business evidence. The original failed run is preserved. Repeated AI-quality cases, actual mailbox intake, and flow-specific lost-response injection remain unproven.

## Grounded intent and repeated quality checkpoint

Prompt v1.2 adds source-bound intent evidence before business writes. All 235 local tests passed (91 runtime, 40 SDK adapter, 73 Python, 31 MCP), alongside the fresh package build and round trips. [Three installed quality runs](evidence/reference-quality-repeat-2026-09-12.json) separately passed 18 assertions with nine independently verified outputs and nine verified output absences. The earlier failed run remains recorded; this does not close mailbox, failure-window or release gates.
