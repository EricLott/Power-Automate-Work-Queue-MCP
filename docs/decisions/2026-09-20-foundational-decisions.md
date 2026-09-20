# Foundational Work Queue decisions

Status: implementation baseline recorded; Phase 0 exit is not approved.

This record consolidates the decisions that govern the `qmcp` runtime and its
reference flows. It distinguishes repository behavior and bounded synthetic
tenant evidence from platform guarantees that still require a clean or
managed environment. The architecture remains the proposed scope; this file
records the current implementation boundary and the evidence behind it.

## Decisions

| Area | Decision | Evidence and boundary |
|---|---|---|
| Native claim strategy | Use the documented native `Dequeue` action behind `PrepareAcquire` / `ResolveAcquire`; never claim work with list-then-update writes. | [Acquisition handoff decision](2026-09-12-acquisition-handoff.md), [acquisition identity proof](../acquisition-identity-proof.md), and [transaction-boundary proof](../transaction-boundary-proof.md). The full identity and deployment matrix remains open. |
| Schema dialect and identity | Register JSON Schema draft-07 contracts, hash the schema, protect the source identity with a bounded digest, and reject changed content for an existing identity. | [Schema boundary proof](../schema-boundary-proof.md), [intake proof](../intake-proof.md), and [validation ledger](../validation.md). Native draft-3/connector mapping remains a tenant validation item. |
| Lifecycle guards | Framework APIs and the synchronous lifecycle plug-in own queue-item and companion-table transitions. Direct writes to registered lifecycle data must fail closed; native state remains authoritative. | [Security identity proof](../security-identity-proof.md) and [registered-delete/companion evidence](../evidence/registered-delete-companion-2026-09-20.json). Restricted-role least privilege and the complete table/message matrix remain open in #16 and G18. |
| State authority | Native work-queue state controls availability and completion; `qmcp_wqitemcontext` controls framework ownership and generation; attempts, command receipts, and outbox rows are durable append/replay records. | [Architecture state model](../architecture.md), [acquisition proof](../acquisition-proof.md), and [contract completion proof](../contract-completion-proof.md). External effects are not treated as transactionally exactly-once. |
| Request and work retries | A request ID is created once per logical command and replayed through its receipt. Unknown outcomes require review. A new work attempt requires an authorized expected-version retry after reconciliation; only policy-approved technical failures may be scheduled automatically. | [Contract completion proof](../contract-completion-proof.md), [delayed retry proof](../delayed-retry-proof.md), and the runtime replay regression in [LifecycleTests.cs](../../tests/runtime/LifecycleTests.cs). |
| Outbox and notification | Record notification intent with the lifecycle result where possible; a separate sender claims pending events with a lease and reports delivery independently. Sender acceptance is not recipient proof. | [Notification failure proof](../notification-failure-proof.md) and [architecture outbox model](../architecture.md). Real Outlook failure/timeout and mailbox evidence remain open. |
| Test isolation | Testing is denied in production, namespaces fixture identities by run/case/repetition, stores test ownership with the item, and cleans only successful test-owned business records after independent evidence. Failed, inconclusive, and cancelled evidence is retained. | [Coordinator evidence](../evidence/positive-coordinator-2026-09-12.json), [autonomous runtime proof](../autonomous-runtime-proof.md), [cancellation evidence](../evidence/test-cancellation-active-2026-09-19.json), and the current [validation ledger](../validation.md). Separate-identity production-destination denial remains open. |
| Child-flow boundary | `OnQueueChanged` is a wake-up parent that invokes `ProcessOne`; scheduled sweep is the bounded recovery path. The parent must not own business processing or raw native writes. | [Generated-flow validation](../../scripts/validate_sources.py), [event parent proof](../event-parent-proof.md), and #107. Event subscription materialization is currently blocked by the authorized environment's maker/service access boundary. |
| Identity and environment | Every live operation binds to the expected organization, environment class, queue allowlist, and effective caller. Framework principals and queue grants are additive controls; an agent-supplied identity is never trusted as authorization. | [Effective-identity evidence](../evidence/security-effective-identity-2026-09-19.json), [security identity proof](../security-identity-proof.md), and [project tracking agreement](../project-tracking.md). A separate non-administrator native role matrix is still required. |
| Installation and upgrade | Installation is explicit plan/apply with pinned package hashes and read-back checks. Upgrade is forward-compatible and managed-only; uninstall/reinstall is not a rollback. A managed baseline is required before claiming upgrade continuity. | [Deployment workflow](../deployment-workflow.md), [upgrade procedure proof](../upgrade-procedure-proof.md), and [upgrade readiness evidence](../evidence/upgrade-readiness-2026-09-19.json). G01 and G21 remain blocked until their required environments exist. |

## Phase 0 exit assessment

The decisions above make the canonical API and local implementation usable
without relying on untested platform guarantees. They do not approve the
Phase 0 exit. The following prerequisites still contain unresolved acceptance
work:

- #16 / G18: restricted-role authorization and the complete native lifecycle
  matrix.
- #17 / G01: a genuinely clean environment for Core-only installation.
- #18 / #107: supported same-solution/event-flow deployment and callback
  materialization.
- #19: remaining schema/key and native metadata tenant validation.
- #20 / G11: the broader post-write and connector failure matrix.
- #90 / G21: an approved managed baseline and additive upgrade proof.

Accordingly, #21 remains `In Progress` and the release review remains open.
No tenant installation, mailbox activation, managed upgrade, or Phase 0
approval is inferred from this record.
