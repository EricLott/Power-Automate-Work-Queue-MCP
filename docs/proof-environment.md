# Synthetic proof environment

This inventory completes the setup deliverable in [#11](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/11). Isolation means explicitly allowlisted synthetic queues, recorded resource ownership, and controlled flow activation in the user-supplied development environment. It does not mean a dedicated empty tenant. Clean managed installation remains [#17](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/17) and G01.

## Verified inventory, 2026-09-13 UTC

The [read-only inventory](evidence/proof-environment-2026-09-13.json) records matching organization identity, four installed solutions at 0.1.0.0, 24 API definitions linked to plug-in types, 39 guard steps, and seven expected flows in Draft. API plug-in linkage is distinct from action entity binding. PAC 2.12.2 and Dataverse CLI 1.0.77 authenticate the approved operator. The user-supplied platform build is recorded as reported, not independently detected.

| Resource | Approved use and final state |
|---|---|
| `qmcp-proof-20260912`, native queue `33fd4458-5922-5be7-85d1-07a9176c9957` | Registered synthetic framework queue. Forty retained inputs were read within this queue only; each has synthetic source metadata or an empty redacted object. Input hashes are retained instead of content. |
| Team `3220a0c3-e520-5927-a39f-aa7bd8dfcdd1` | Ownership scope for framework fixtures. Separate-user least privilege is still unproved. |
| Native probe queue `d14ec06b-3109-57e6-b18e-43763044a876` | Unregistered synthetic queue for native connector behavior; Active after the [connector proof](native-connector-proof.md). Its synthetic item is Queued. |
| Seven framework/reference flows | Draft at inventory time. Selected flows were temporarily activated for recorded prior proofs. Intake and EmailSender have not been activated for mailbox ingestion or delivery. |
| Diagnostic flows and Notes | Synthetic connector evidence retained with exact resource IDs in the connector proof; diagnostic flows restored to Draft. |

Fixture builders in `scripts/prove_acquisition_identity.py` and `scripts/generate_native_connector_probe.py` use generated synthetic content and recorded IDs. Reference evaluations and their versioned expectations are documented in [reference quality proof](reference-quality-proof.md). No real mailbox input is needed for these experiments.

## Access and evidence boundaries

The [import ledger](live-import.md) records identity verification before writes and the initial missing API bindings/guard registration. Those setup gaps were resolved in subsequent proofs. Current metadata confirms linkage; it does not prove privileges. Separate identities and direct-write authorization remain #16, G18 and G19. Real mailbox integration, clean managed install, upgrades and capacity remain open in the [gate ledger](validation.md). Existing authorization is for this supplied environment; no unrelated production resources are proof fixtures.

Bindings and full operator details stay in ignored `artifacts/live/` files. The binding restricts framework calls to the registered queue key. Never copy credentials into an evidence record. A source tag alone is not provenance proof: use the controlled fixture builder and recorded run/resource identities together. The exact-queue inventory avoids reading unrelated tenant content.

## Reproduce and record

Run `./scripts/pac.ps1 env who`, then `python scripts/probe_tenant_metadata.py --binding artifacts/live/mcp-binding.json --output artifacts/live/proof-environment-metadata.json --dataverse-cli`. Verify the organization before any mutation. The published inventory also records a bounded exact-queue input query, with no continuation page, selecting item ID and input and retaining only hashes/source tags. Gate states were read using GitHub CLI REST for repository issues 70–91.

Copy the [evidence template](templates/proof-evidence.json) for each new experiment. Fill environment, tool/package versions, identity roles, fixture ownership, commands, expected results and request/run IDs before execution. Keep `inconclusive` until actual evidence establishes the outcome; a missing result or access denial cannot pass. Record unknown versions as unknown. Record cleanup expectations before mutations and verify final states independently afterward.

Retained synthetic data is intentional evidence, not a claim of an empty environment. Cleanup must target recorded test-owned resources only. Registered queue lifecycle changes use public framework APIs. The unregistered native probe requires its documented native transition sequence; never generalize its cleanup into a tenant-wide reset. Record restoration failures even when the main experiment passed.
