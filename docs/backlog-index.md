# Build plan issue index

Design v0.1 planning baseline. Live status, owners, evidence and dependencies are maintained in the linked GitHub issues and [project](https://github.com/users/EricLott/projects/2). No runtime gate passed during planning.

## Planning

| Work item | Type | Prerequisites |
|---|---|---|
| [H01 — Connect workspace to the GitHub repository](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/9) | task | None |
| [H02 — Establish the design baseline and linked project backlog](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/10) | task | [H01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/9) |

## P0

| Work item | Type | Prerequisites |
|---|---|---|
| [E0 — P0 — Prove acquisition and recovery](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/1) | epic | None |
| [P0-00 — Prepare the isolated proof environment and evidence ledger](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/11) | task | None |
| [P0-01 — Prove native dequeue through a flow and a Custom API](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/12) | spike | [P0-00](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/11) |
| [P0-02 — Prove dequeue, attempt and command receipt transactionality](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/13) | spike | [P0-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/12) |
| [P0-03 — Prove concurrent and repeated acquisition safety](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/14) | spike | [P0-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/13) |
| [P0-04 — Validate native transitions, delays, expiry and pause](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/15) | spike | [P0-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/12) |
| [P0-05 — Prove lifecycle guards and least-privilege boundaries](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/16) | spike | [P0-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/12) |
| [P0-06 — Prove minimal Core import into a clean environment](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/17) | spike | [P0-00](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/11) |
| [P0-07 — Prove same-solution parent and child flow deployment](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/18) | spike | [P0-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/12), [P0-06](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/17) |
| [P0-08 — Validate schema dialect, key activation and metadata limits](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/19) | spike | [P0-00](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/11) |
| [P0-09 — Prove recovery after the business write but before Complete](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/20) | spike | [P0-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/13), [P0-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/14), [P0-08](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/19) |
| [P0-10 — Record foundational decisions and approve Phase 0 exit](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/21) | task | [P0-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/14), [P0-04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/15), [P0-05](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/16), [P0-06](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/17), [P0-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/18), [P0-08](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/19), [P0-09](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/20) |

## P1

| Work item | Type | Prerequisites |
|---|---|---|
| [E1 — P1 — Build the runtime foundation](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/2) | epic | None |
| [P1-01 — Establish solution and source build structure](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/22) | task | [P0-10](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/21) |
| [P1-02 — Implement Core metadata, alternate keys and relationships](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/23) | task | [P1-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/22) |
| [P1-03 — Implement roles, queue authorization and lifecycle guards](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/24) | task | [P1-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/23) |
| [P1-04 — Publish canonical API and envelope contracts](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/25) | task | [P1-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/22) |
| [P1-05 — Register queues, immutable contracts and policy revisions](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/26) | story | [P1-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/23), [P1-04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/25) |
| [P1-06 — Implement shared command receipt and plug-in services](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/27) | task | [P1-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/24), [P1-04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/25) |
| [P1-07 — Implement qmcp_WQ_Enqueue with source deduplication](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/28) | story | [P1-05](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/26), [P1-06](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/27) |
| [P1-08 — Implement qmcp_WQ_AcquireNext with proven ownership strategy](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/29) | story | [P1-06](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/27), [P1-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/28) |
| [P1-09 — Implement qmcp_WQ_Complete and qmcp_WQ_Fail](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/30) | story | [P1-08](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/29) |
| [P1-10 — Implement bounded item-status and queue-health reads](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/31) | story | [P1-09](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/30) |
| [P1-11 — Verify the first runtime vertical slice](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/32) | task | [P1-09](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/30), [P1-10](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/31) |
| [G02 — Acceptance gate: Intake duplicate](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/71) | gate | [P1-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/28), [P1-11](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/32) |
| [G03 — Acceptance gate: Intake conflict](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/72) | gate | [P1-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/28), [P1-11](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/32) |
| [G04 — Acceptance gate: Acquisition concurrency](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/73) | gate | [P0-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/14), [P1-08](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/29) |
| [G05 — Acceptance gate: Acquisition replay](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/74) | gate | [P0-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/14), [P1-08](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/29) |
| [G06 — Acceptance gate: Completion replay](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/75) | gate | [P1-09](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/30), [P1-11](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/32) |
| [G09 — Acceptance gate: Paused queue](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/78) | gate | [P0-04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/15), [P1-08](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/29) |

## P2

| Work item | Type | Prerequisites |
|---|---|---|
| [E2 — P2 — Build the reference business process](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/3) | epic | None |
| [P2-01 — Build normalized shared-mailbox intake](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/33) | story | [P1-11](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/32) |
| [P2-02 — Build the reference target table and idempotent write](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/34) | story | [P1-11](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/32) |
| [P2-03 — Build versioned extraction and deterministic output validation](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/35) | story | [P2-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/34) |
| [P2-04 — Build the ProcessOne worker with explicit failure scopes](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/36) | story | [P2-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/34), [P2-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/35) |
| [P2-05 — Build event wake-up and bounded scheduled sweep](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/37) | story | [P2-04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/36) |
| [P2-06 — Package customer-owned templates and Dataverse intake adapter](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/38) | task | [P2-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/33), [P2-05](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/37) |
| [P2-07 — Verify real intake, queue injection and all write failure windows](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/39) | task | [P2-06](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/38) |
| [G08 — Acceptance gate: Missed wake-up](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/77) | gate | [P2-05](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/37), [P2-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/39) |
| [G10 — Acceptance gate: Unsupported payload](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/79) | gate | [P1-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/28), [P2-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/39) |
| [G11 — Acceptance gate: Post-write failure](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/80) | gate | [P0-09](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/20), [P2-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/39) |

## P3

| Work item | Type | Prerequisites |
|---|---|---|
| [E3 — P3 — Add recovery and operations](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/4) | epic | None |
| [P3-01 — Implement bounded checkpoints and stale-generation enforcement](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/40) | story | [P1-11](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/32) |
| [P3-02 — Implement bounded safe work retry policy](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/41) | story | [P3-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/40), [P2-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/39) |
| [P3-03 — Implement authorized retry requests with expected version](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/42) | story | [P3-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/41) |
| [P3-04 — Implement watchdog recovery and orphan reconciliation](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/43) | story | [P3-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/40), [P3-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/41) |
| [P3-05 — Implement pre-enqueue intake failure reporting](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/44) | story | [P1-10](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/31) |
| [P3-06 — Build the model-driven operations app and liveness views](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/45) | story | [P3-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/42), [P3-04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/43), [P3-05](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/44) |
| [P3-07 — Verify recovery under cancellation, disablement and policy changes](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/46) | task | [P3-06](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/45) |
| [G07 — Acceptance gate: Delayed work](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/76) | gate | [P0-04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/15), [P3-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/41), [P3-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/46) |
| [G12 — Acceptance gate: Stale worker](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/81) | gate | [P3-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/40), [P3-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/46) |
| [G13 — Acceptance gate: Unknown outcome](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/82) | gate | [P3-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/41), [P3-04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/43), [P3-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/46) |

## P4

| Work item | Type | Prerequisites |
|---|---|---|
| [E4 — P4 — Add durable notifications](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/5) | epic | None |
| [P4-01 — Implement outbox delivery coordination](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/47) | story | [P3-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/46) |
| [P4-02 — Implement queue notification rules and safe destinations](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/48) | story | [P4-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/47) |
| [P4-03 — Package optional email sender and delivery recovery](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/49) | story | [P4-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/48) |
| [P4-04 — Verify notification failure and optional-package independence](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/50) | task | [P4-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/49) |
| [G14 — Acceptance gate: Notification failure](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/83) | gate | [P4-04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/50) |

## P5

| Work item | Type | Prerequisites |
|---|---|---|
| [E5 — P5 — Build the evidence-based test harness](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/6) | epic | None |
| [P5-01 — Implement test metadata, immutable snapshots and trusted profiles](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/51) | story | [P3-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/46) |
| [P5-02 — Build durable test-run coordinator and recovery](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/52) | story | [P5-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/51) |
| [P5-03 — Implement bounded declarative assertions and evidence retrieval](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/53) | story | [P5-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/52) |
| [P5-04 — Implement test-owned cleanup and failed-evidence retention](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/54) | story | [P5-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/53) |
| [P5-05 — Build approved AI fixtures and repeated quality evaluation](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/55) | task | [P5-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/53), [P2-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/35) |
| [P5-06 — Implement the full reference regression suite](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/56) | task | [P5-04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/54), [P5-05](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/55), [P4-04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/50) |
| [G15 — Acceptance gate: Test isolation](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/84) | gate | [P5-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/51), [P5-04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/54), [P5-06](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/56) |
| [G16 — Acceptance gate: Test evidence](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/85) | gate | [P5-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/53), [P5-06](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/56) |
| [G17 — Acceptance gate: AI extraction](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/86) | gate | [P5-05](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/55), [P5-06](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/56) |

## P6

| Work item | Type | Prerequisites |
|---|---|---|
| [E6 — P6 — Build the local MCP development workflow](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/7) | epic | None |
| [P6-01 — Build environment-bound local stdio MCP foundation](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/57) | task | [P5-06](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/56) |
| [P6-02 — Publish inspect tools and versioned contract resources](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/58) | story | [P6-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/57) |
| [P6-03 — Build pinned-release install planning and preflight](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/59) | story | [P6-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/58) |
| [P6-04 — Build approved install and queue plan/apply operations](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/60) | story | [P6-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/59) |
| [P6-05 — Build supported process scaffolding and static validation](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/61) | story | [P6-04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/60), [P2-06](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/38) |
| [P6-06 — Expose test evidence and restricted operator tools](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/62) | story | [P6-05](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/61) |
| [P6-07 — Verify supported agent hosts and full development workflow](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/63) | task | [P6-06](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/62) |
| [G20 — Acceptance gate: Agent disconnection](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/89) | gate | [P5-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/52), [P6-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/63) |

## P7

| Work item | Type | Prerequisites |
|---|---|---|
| [E7 — P7 — Harden and release the MVP](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/8) | epic | None |
| [P7-01 — Build reproducible managed release pipeline and compatibility manifest](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/64) | task | [P6-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/63) |
| [P7-02 — Validate additive upgrade, queue migration and recovery procedures](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/65) | task | [P7-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/64) |
| [P7-03 — Run separate-identity security and untrusted-content tests](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/66) | task | [P7-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/64) |
| [P7-04 — Implement bounded retention and storage maintenance](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/67) | task | [P7-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/64) |
| [P7-05 — Measure capacity, throttling and per-item cost](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/68) | task | [P7-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/64) |
| [P7-06 — Validate operational failure scenarios and write runbooks](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/69) | task | [P7-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/65), [P7-04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/67), [P7-05](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/68) |
| [P7-07 — Run independent clean install and MVP release review](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/92) | task | [P7-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/65), [P7-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/66), [P7-04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/67), [P7-05](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/68), [P7-06](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/69), [G01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/70), [G02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/71), [G03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/72), [G04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/73), [G05](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/74), [G06](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/75), [G07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/76), [G08](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/77), [G09](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/78), [G10](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/79), [G11](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/80), [G12](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/81), [G13](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/82), [G14](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/83), [G15](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/84), [G16](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/85), [G17](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/86), [G18](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/87), [G19](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/88), [G20](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/89), [G21](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/90), [G22](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/91) |
| [G01 — Acceptance gate: Clean install](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/70) | gate | [P7-01](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/64), [P0-06](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/17) |
| [G18 — Acceptance gate: Authorization](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/87) | gate | [P7-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/66) |
| [G19 — Acceptance gate: Lifecycle bypass](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/88) | gate | [P0-05](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/16), [P7-03](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/66) |
| [G21 — Acceptance gate: Upgrade](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/90) | gate | [P7-02](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/65) |
| [G22 — Acceptance gate: Capacity](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/91) | gate | [P7-05](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/68) |

## Future

| Work item | Type | Prerequisites |
|---|---|---|
| [EF — Deferred roadmap — outside MVP](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/93) | epic | None |
| [F01 — Read-only Teams notifications](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/94) | discovery | [P7-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/92) |
| [F02 — Interactive Teams retry cards and group chats](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/95) | discovery | [P7-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/92) |
| [F03 — Generic webhook notification package](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/96) | discovery | [P7-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/92) |
| [F04 — Public connector distribution](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/97) | discovery | [P7-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/92) |
| [F05 — Hosted multi-tenant MCP](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/98) | discovery | [P7-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/92) |
| [F06 — Desktop-worker certification](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/99) | discovery | [P7-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/92) |
| [F07 — General external-effect ledger](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/100) | discovery | [P7-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/92) |
| [F08 — Advanced circuit breakers](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/101) | discovery | [P7-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/92) |
| [F09 — Large operations dashboards](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/102) | discovery | [P7-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/92) |
| [F10 — Large attachment storage adapters](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/103) | discovery | [P7-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/92) |
| [F11 — Automatic flow repair](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/104) | discovery | [P7-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/92) |
| [F12 — Long-lived approval orchestration](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/105) | discovery | [P7-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/92) |
