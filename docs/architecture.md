# Power Automate Work Queue Framework
## Architectural design and implementation plan

**Design version:** 0.1
**Date:** September 12, 2026
**Status:** Proposed architecture. Not yet implemented or validated in a tenant.
**Working name:** Work Queue Framework (WQF)
**Publisher prefix:** `qmcp_`

## 1. Executive summary

Build an open-source framework that makes native Power Automate work queues a standard boundary for reliable, testable, agent-assisted automation.

The framework has three parts:

1. **An installed runtime:** managed Dataverse solutions with lifecycle APIs, processing-attempt records, recovery, operational controls, and optional notification and testing packages.
2. **Customer automation:** solution-aware intake flows and worker flows that contain the customer's business logic.
3. **A development interface:** an MCP server, versioned instructions, schemas, templates, and validation tools that help a developer's agent install, configure, build, test, and inspect the automation.

The central pattern is:

```text
External event -> Intake adapter -> Native work queue
                                      |
                          Wake-up flow / scheduled sweep
                                      |
                             Customer worker flow
                                      |
                          Framework lifecycle APIs
                                      |
                 Attempts + results + notification outbox
```

An agent can insert a valid test input at the queue boundary and inspect durable results without recreating the original external event for every test. Separate integration tests still exercise the real trigger and source connector.

**The MCP server is not the production runtime.** Queue processing, retry scheduling, recovery, and notifications must continue after the developer closes the agent host.

**The delivery model is retryable processing, not universal exactly-once execution.** Queue uniqueness prevents duplicate intake when used correctly. It does not make an email send, an approval request, or a downstream record write part of the same transaction as queue completion. Each business process must declare how its effects remain safe during a retry.

The first release should prove one complete scenario: **shared-mailbox email -> structured extraction -> one Dataverse business record**, with queue-injection tests, a real-mailbox integration test, durable diagnostics, safe recovery, and one notification channel.

## 2. Verified platform foundation and design corrections

The following are documented platform capabilities, not framework inventions. The reference identifiers point to the primary-source register at the end.

| Area | Documented foundation | Consequence for this design |
|---|---|---|
| Queue processing | Microsoft documents cloud-flow processing through the Dataverse `Dequeue` bound action. [R01, R02] | Wrap native dequeue. Do not implement a competing list-then-update claim mechanism. |
| Queue input validation | Queues support a fixed JSON or XSD schema. The documented JSON dialect is draft 3, and the schema cannot be changed after it is added. [R03] | Separate a stable queue envelope from versioned business contracts. |
| Native history | `workqueueitem.executioncontext` is system-managed processing history. A processing-history action also exists. [R04, R05] | Add structured framework attempts for a clear purpose. Do not claim Microsoft has no history. |
| Cloud run history | The optional Dataverse `FlowRun` store includes run metadata but is not fully lossless. Microsoft advises against triggering flows on `FlowRun` or `FlowLog`. [R06] | Treat native run data as diagnostic enrichment, not the authoritative test ledger. |
| Retry and SLA | Work queues expose SLA settings. The documented queue auto-retry option applies to desktop-flow processing. [R03] | Reuse native SLA features. Define a separate cloud retry policy. |
| Child flows | Microsoft documents parent and child flows in the same solution. Child flows also have connection requirements. [R07] | Do not use shared framework child flows as the cross-solution API. Local customer child flows remain useful. |
| Custom APIs | Dataverse custom APIs can expose actions to the Dataverse connector. [R08] | Use C#-backed custom actions as the runtime contract. |
| Custom connector hosts | Solution custom connectors can use environment variables for host and authentication settings. Values are resolved when the connector is saved. [R09] | Customer-specific host URLs are solvable, but do not justify a connector in the MVP. |
| Scale | Microsoft recommends moderate dequeue concurrency, up to five parallel operations per queue, and identifies high-throughput scenarios as a poor fit. [R10] | Position WQF for business-process automation, not as a replacement for a high-throughput message broker. |

These documents establish the platform surface. They do **not** establish that every proposed combination below has been tested. Native dequeue transaction behavior, supported extension points, and end-to-end deployment remain explicit validation gates.

## 3. Architectural decisions

### 3.1 Runtime API, not connector-first packaging

Implement framework operations as **Dataverse Custom API actions with C# plug-ins**. Customer flows call them through the existing Dataverse connector using **Perform an unbound action**. The MCP server calls the same operations through the Dataverse Web API.

Publish task-specific actions such as `AcquireNext`, `Complete`, and `Fail`. Do not expose a general `SetStatus` action that lets a caller bypass lifecycle rules.

A solution-level custom connector can later provide a more convenient action picker. An independent public connector is outside the first release.

### 3.2 Native queues remain the work store

Use `workqueue` and `workqueueitem`. Do not replace them with custom work-item tables. Add companion tables for framework metadata, attempts, contracts, command receipts, notifications, and test evidence.

The native item holds the current queue state. The framework attempt records explain each processing attempt. The framework item context holds ownership and control metadata, not a second independent queue status.

### 3.3 Separate product runtime from customer business logic

The installed framework must not know how to classify an email, select an AI prompt, create a customer-specific record, or route an approval.

Customer solutions own these business decisions. Framework updates must not overwrite their flows.

### 3.4 Instructions guide; code enforces

MCP instructions explain the pattern. API validation, Dataverse security, generated-flow checks, and test gates enforce it. A tool description that says “do not retry unsafe work” is not an authorization or concurrency control.

### 3.5 Queue-first is a supported default, not a universal rule

Use this pattern for asynchronous work with a meaningful work item, retries, independent processing, or replay requirements. Do not automatically convert synchronous validation, trivial one-step notifications, or subsecond workloads into queued processes.

## 4. Release scope and package boundaries

### 4.1 MVP scope

| Capability | MVP decision |
|---|---|
| Native queue creation and registration | Included, using stable friendly keys. |
| Versioned JSON input contracts | Included, with server-side validation and immutable contract revisions. |
| Intake and worker templates | Included for shared-mailbox and Dataverse intake. |
| Native dequeue wrapper | Included, subject to concurrency and transaction proof. |
| Attempt ownership and lifecycle operations | Included, including stale-attempt rejection. |
| Duplicate command and intake protection | Included. Business-effect protection is required per workflow. |
| Cloud retry policy | Included for explicitly safe retry cases, with bounded attempts and delays. |
| Crash and timeout recovery | Included. Unknown outcomes require review by default. |
| Basic operations console | Included: queues, attempts, failures, retry requests, and health. |
| Notifications | Email delivery included as an optional package. |
| Test suite | Queue injection, deterministic assertions, test run evidence, and cleanup controls. |
| AI extraction evaluation | Small fixture suite, structured-output checks, field assertions, and repeat-run results. |
| MCP experience | Inspect, plan, provision, scaffold, validate, test, and diagnose. |
| Installation and upgrade controls | Explicit plan/apply, pinned releases, approval, health checks, and compatibility checks. |
| Release pipeline | Source, managed artifacts, checksums, automated tests, and installation documentation. |

### 4.2 Deferred features

Defer interactive Teams retry cards, Teams group-chat support, generic webhook delivery, a public connector, remote multi-tenant MCP hosting, desktop-worker certification, a general external-effect ledger, advanced circuit breakers, large dashboards, large attachment storage adapters, automatic flow repair, and comprehensive approval orchestration.

A read-only Teams card is a smaller follow-on than an interactive retry card. The latter requires responder authorization, stale-card checks, and command deduplication.

### 4.3 Explicit non-goals

WQF is not a general flow execution engine, a replacement for Azure Service Bus, an automatic licensing solution, a promise of zero-configuration installation, or a universal exactly-once transaction manager. It will not automatically resume an arbitrary failed cloud-flow run at a particular action.

### 4.4 Deployable packages

| Package | Contents and dependency |
|---|---|
| `WQ.Core` | Core tables, lifecycle APIs, queue guards, watchdog, maintenance flow, security roles, and basic operations app. |
| `WQ.Testing` | Depends on Core. Test case/run/result tables, coordinator, assertion APIs, and test-specific permissions. Optional in production. |
| `WQ.Notifications.Email` | Depends on Core. Email sender flow and its connection references. Optional. |
| `WQ.Reference.SharedMailbox` | Reference business solution and source templates. Not part of the runtime dependency graph. |
| `wq-mcp` | Local MCP server, resource files, instructions, template compiler, and validation tools. Distributed separately from Dataverse. |

Future Teams and webhook senders should be separate packages. A Boolean that disables a branch does not eliminate the need to manage that branch's packaged connection dependencies. The package split prevents the Dataverse-only core from requiring Outlook or Teams credentials.

## 5. Runtime flow design

### 5.1 Intake adapter

For the reference scenario, the intake flow runs when a message reaches the configured shared mailbox.

It establishes the source identity, extracts or reads the required message fields, normalizes the input, assigns a correlation ID, and calls `qmcp_WQ_Enqueue`. It then records the enqueue result.

It must not run the extraction prompt or create the final business record. Those operations belong to the worker.

A repeated source event with the same deduplication key and content hash returns the existing item. The same key with different content is a conflict, not a silent overwrite.

**Before-enqueue failures need their own path.** An invalid payload or missing connection can fail before there is a queue item. `ReportIntakeFailure` must accept a source reference and correlation ID without requiring a work-item ID. A complete Dataverse outage also prevents this report, so native flow failure alerts remain a fallback.

### 5.2 One customer processing implementation, two wake-up paths

The recommended scaffold contains four small customer-owned flows:

| Flow | Purpose |
|---|---|
| `Intake` | Normalize the external event and enqueue work. |
| `ProcessOne` | Same-solution child flow. Acquire and process at most one eligible item. |
| `OnQueueChanged` | Dataverse event trigger that calls `ProcessOne` when work may be available. |
| `SweepQueue` | Scheduled parent that repeatedly calls `ProcessOne` within a bounded batch and time budget. |

All four belong to the customer's solution. Both parents reference the same local child flow, consistent with the documented child-flow model. [R07]

The event is a **wake-up hint**, not proof that its triggering item belongs to this worker. `ProcessOne` calls native dequeue through the framework and processes the item returned. This preserves a queue-oriented processing model.

The scheduled path is necessary because a delayed item becoming eligible does not itself require a new Dataverse row update. It also recovers available backlog after disabled flows, deployment gaps, or missed wake-ups. The framework must not depend exclusively on event delivery.

Configure the event filter for the registered queue and queued status. Limit selected update columns to those needed for availability changes. Still recheck eligibility during acquisition. Dataverse triggers can evaluate repeated updates, including updates that write an existing value. [R11]

Start with one worker concurrency slot per queue. Validate aggregate behavior when both parents call the child. Separate dequeue concurrency from the number of downstream actions that may run concurrently.

### 5.3 Worker execution sequence

`ProcessOne` follows this sequence:

1. Capture the environment ID, flow ID, run ID, and template version.
2. Call `AcquireNext` with a unique request ID generated once for this acquisition.
3. Exit normally on `NoWork` or `QueuePaused`.
4. Parse the returned envelope and verify the declared contract.
5. Establish whether the business result already exists for this source key.
6. Run the extraction prompt only when necessary.
7. Validate its structured result and apply deterministic business rules.
8. Create or obtain the target record through the workflow's declared idempotent write pattern.
9. Call `Complete` with the current attempt identity, lease generation, output reference, and evidence summary.
10. Return an outcome to the parent.

Use explicit scopes for acquisition, business work, completion, and error reporting. Do not put completion in an unconditional “finally” path.

A failure in completion after the business write is different from a business-operation failure. Retry the same completion command first. Do not rerun the business action merely because the completion response was lost.

### 5.4 Error reporting

Pass caller metadata and a normalized error directly to the framework. Use `workflow()` for current run metadata and scope results for failure details. Microsoft documents these error-handling mechanisms. [R12]

A custom API does not automatically receive the parent flow's connector errors. A child flow's `workflow()` describes that child, not a magical view of the caller's complete action history.

Filter failed and timed-out actions. Nested scopes require explicit handling. Never assume the first result entry is the error, and never copy a complete action result containing email bodies, credentials, or headers into an alert.

For expected business rejection, record a business-exception outcome. For an unhandled technical failure, record the error and deliberately report a failed worker run. Attempt outcome and native flow outcome remain separate evidence fields.

## 6. Input, output, and error contracts

### 6.1 Versioned input envelope

The following is a proposed example, not an existing Microsoft API contract:

```json
{
  "envelopeVersion": "1.0",
  "contract": "shared-mailbox.email-request.v1",
  "correlationId": "6d66ff08-6040-4eab-8abf-927dfaa50ea7",
  "deduplicationKey": "mail-v1:sha256-hex-digest",
  "source": {
    "type": "outlook.shared-mailbox",
    "mailbox": "requests@example.com",
    "messageId": "source-connector-message-id",
    "messageIdType": "outlook-connector",
    "receivedAt": "2026-09-12T15:00:00Z"
  },
  "payload": {
    "subject": "Request for service",
    "bodyText": "Please contact Alex about an installation.",
    "senderAddress": "alex@example.com"
  },
  "provenance": {
    "adapterVersion": "1.0.0"
  }
}
```

The API validates the requested queue against its registered contracts. It does not trust a payload to select a different environment, connection, endpoint, prompt, or destination table.

Set framework limits for payload bytes, JSON depth, property counts, string lengths, and allowed schema features. A proposed initial input limit is 128 KiB of UTF-8 JSON, subject to the reference workload test. This is a framework limit, not Microsoft's maximum.

The native unique-reference field is limited to 100 characters. Use a short stable digest for long source identifiers and retain the original source identity separately. [R04]

### 6.2 Schema strategy

Use a conservative draft-3-compatible envelope for native queue validation. Validate the business payload against a versioned framework contract in the API.

For MVP, select and pin a JSON-schema dialect supported by the chosen plug-in validator, and publish that exact subset. Avoid arbitrary remote schema references, dynamic schema downloads, and schema changes during a run.

Contracts are immutable once activated. A changed schema receives a new version and hash. Additive revisions require compatibility tests. A breaking envelope change creates a new physical queue version, such as `shared-mailbox-requests.v2`, followed by a controlled cutover.

`Parse JSON` helps the flow access fields, but the server-side enqueue and acquisition validations define framework acceptance.

### 6.3 Durable input and replay

The preferred reference template enqueues the normalized message snapshot needed by the business logic. The source ID remains for audit and integration checks.

A pointer-only payload is an optional reference mode. Label it as dependent on external state, not deterministic replay. The source email might be moved, changed, or deleted. Graph supports an immutable-ID mode, but it must be explicitly used through an integration that supports it; an Outlook connector ID must not simply be relabeled as immutable. [R13]

Snapshots reproduce the input, not necessarily the result of a changing AI model. A replay report must state both the input identity and the model/prompt information available for that execution.

Do not put binary attachments into queue JSON in the MVP. Reject unsupported sizes or use an explicitly approved external storage extension later. Do not silently truncate a source message.

### 6.4 Output and error contracts

A completion response stores a bounded output summary and references to real records. For example:

```json
{
  "resultVersion": "1.0",
  "businessOutcome": "created",
  "record": {
    "table": "qmcp_emailrequest",
    "id": "89d78d1e-6960-4f93-a29d-5420d622ab74"
  },
  "sourceContentHash": "sha256-hex-digest",
  "promptVersion": "email-extraction-v1"
}
```

A normalized error includes category, code, safe message, failed stage, action name, retry-safety assessment, whether an external result is known, and a run reference. The server determines retry eligibility from policy and evidence; a worker-provided `retryable: true` does not override queue policy.

Use stable codes such as `INPUT_INVALID`, `KEY_CONTENT_CONFLICT`, `NO_WORK`, `STALE_ATTEMPT`, `SOURCE_UNAVAILABLE`, `BUSINESS_VALIDATION_FAILED`, and `OUTCOME_UNKNOWN`.

## 7. Dataverse data model

Use standard custom tables for the MVP so command processing can participate in normal transactional operations. Do not store arbitrary execution state in processing notes.

| Logical table | Purpose and key fields |
|---|---|
| Native `workqueue` | Queue identity, native lifecycle controls, ordering, and native schema. |
| Native `workqueueitem` | Work payload and current native processing state. |
| `qmcp_wqdefinition` | Stable framework queue key, native queue reference, owner team, worker registration, enabled state, policy revision, retry policy, processing deadline, and allowed contracts. |
| `qmcp_wqcontract` | Contract ID/version, schema, dialect, content hash, activation state, and compatible envelope version. |
| `qmcp_wqitemcontext` | One row per native item: correlation ID, source/content hashes, active attempt, lease generation, test-run reference, output reference, and review-required flag. |
| `qmcp_wqattempt` | One row per attempt: sequence, start/end, lease expiry, checkpoint, caller/run IDs, policy and contract snapshots, outcome, normalized error, and result. |
| `qmcp_wqcommand` | Idempotent command receipt: caller, request ID, operation, input fingerprint, durable result, completion time, and audit details. |
| `qmcp_wqnotificationrule` | Queue-specific event selection, destination key, channel, enabled state, cooldown, and redaction level. |
| `qmcp_wqevent` | Durable outbox/delivery record: event kind, item/attempt or intake reference, destination key, event key, delivery state, next attempt time, and safe payload. |
| `qmcp_wqtestcase` | Versioned input fixture, contract, assertion definitions, allowed test profile, expected exception, and ownership. |
| `qmcp_wqtestrun` | Requested suite/cases, manifest hashes, environment, status, deadline, execution profile, start/end, and summary. |
| `qmcp_wqtestresult` | One row per case execution/repetition: case snapshot, associated item, assertion evidence, outcome, timing, and cleanup status. |

### 7.1 Keys and relationships

Define alternate keys for the framework queue key, contract ID/version, native item identity in the context table, item/attempt sequence, caller/request/operation command identity, notification event/destination identity, and test-run/case/repetition identity.

Dataverse alternate keys provide an API-oriented unique identity. Their indexes must finish activation before provisioning proceeds. [R14]

A native item has one context and many attempts. A test result references the item created for that case execution. An outbox event may reference an attempt, or an intake failure with no item.

Store essential keys and run identifiers as scalar snapshots as well as usable lookups where supported. A deleted native run record must not invalidate framework test evidence.

### 7.2 State ownership and retention

The native item owns queue state. The context owns active-attempt identity and framework controls. Completed attempts are append-only except for separately audited redaction or retention operations.

Do not edit Microsoft's system-managed `executioncontext`. Do not build against undocumented structures inside that field.

Deletion must be controlled. Define relationship behavior and verify cascade effects before release. Retain command receipts and source deduplication identities for at least the supported retry/replay window. Deleting the only duplicate marker reopens the possibility of reprocessing an old event.

Retention settings for message snapshots, errors, attempts, test evidence, and command receipts can differ. A purge must not remove active work or records under a review hold.

## 8. Runtime API contract

All names below are proposed framework APIs. Use Actions rather than Functions for the Power Automate-facing surface. Set public discovery and managed properties deliberately. Microsoft's custom API guidance distinguishes discoverability, action support, and privilege checks. [R08]

### 8.1 Principal operations

| Proposed action | Required purpose |
|---|---|
| `qmcp_WQ_Enqueue` | Validate contract, enforce intake deduplication, create native item and context, return item identity. |
| `qmcp_WQ_AcquireNext` | Validate queue/worker, dequeue natively, establish an attempt and lease, and return a processing contract. |
| `qmcp_WQ_Checkpoint` | Validate current ownership and record bounded progress; optionally extend a lease within the maximum processing deadline. |
| `qmcp_WQ_Complete` | Validate ownership, store result, complete the attempt and native item, and create required events. |
| `qmcp_WQ_Fail` | Record the error, close the attempt, apply safe retry policy, and create required events. |
| `qmcp_WQ_RequestRetry` | Accept an authorized retry request with reason and expected current version; reject stale or unsafe requests. |
| `qmcp_WQ_ReportIntakeFailure` | Record a failure before successful enqueue. |
| `qmcp_WQ_GetItemStatus` | Return a bounded, redacted status/attempt/result view. |
| `qmcp_WQ_GetQueueHealth` | Return queue configuration checks, backlog age, failed attempts, and maintenance status. |
| `qmcp_WQ_RecoverExpiredAttempt` | Watchdog-only operation that checks expiry and ownership again before recovery. |

Provisioning and testing packages add queue/contract registration, event-delivery coordination, test-run creation, test-result evaluation, and bounded maintenance actions. Do not expose these internals to all MCP users.

### 8.2 Common request and response rules

Every mutating operation includes a request ID. Item mutations also include queue key, item ID, attempt ID where applicable, and the expected ownership generation or record version.

Use typed scalar inputs for the common fields and bounded JSON strings for structured payloads. Maintain one canonical schema for each operation and generate the MCP tool schema and documentation from it.

A request with the same identity and fingerprint returns its recorded result. Reusing a request ID with different arguments fails. A duplicate `Complete` must not create a second notification. A duplicate `AcquireNext` must not silently acquire another item.

The acquisition response has an explicit outcome: `Acquired`, `NoWork`, `QueuePaused`, or a documented failure. `NoWork` is a normal result, not an exception that creates alerts.

### 8.3 Native claim and transaction boundary

Preferred implementation: a short synchronous Custom API calls native `Dequeue` through `IOrganizationService`, then creates the attempt, context update, and command receipt inside the same platform transaction.

This is a **Phase 0 proof requirement**, not an assumed guarantee. Validate native message invocation, `IsInTransaction`, concurrent requests, rollback after dequeue, and behavior after a lost API response.

Microsoft documents transaction participation through the Dataverse SDK and advises against calling the same organization's Web API from inside a plug-in. It also advises against batch request types inside synchronous plug-ins. [R15, R16]

If the native operation cannot be composed transactionally, evaluate a two-step native-dequeue/attempt-registration path. No business action may start until registration succeeds. Orphaned processing items require quarantine or reconciliation. Do not fall back to an unsafe list-and-patch claim.

### 8.4 Ownership and stale-worker protection

Each attempt receives an ownership generation. Completion, failure, and checkpoint operations must match the current generation. Use optimistic concurrency on framework control rows to make competing updates detect conflicts. [R17]

A generation check protects framework state. It does not cancel a connector call already running elsewhere. Business-effect safety remains a separate requirement.

Guard create/update/delete operations for registered queues against unauthorized direct lifecycle writes, without affecting unrelated queues. Validate whether the required native-table plug-in registrations are supported and whether native dequeue still works through the guard. If that enforcement cannot be provided, document the boundary accurately and redesign permissions before release.

### 8.5 C# structure

Separate plug-in entry points, contract validation, queue policy, native queue access, attempt operations, authorization, and event persistence.

Use a generic service/context abstraction for plug-in components; choose or implement the pattern within this independent project. Custom API entry points read `Context.InputParameters` and set `Context.OutputParameters`; they must not require `IsValidTargetEntity` when the API has no entity Target.

Keep external HTTP calls, prompt execution, mailbox access, notification delivery, and long waits out of synchronous plug-ins.

## 9. Lifecycle, retries, and recovery

### 9.1 Native state mapping

Use the native lifecycle: Queued -> Processing -> Processed or an exception. Requeue and hold operations must follow supported transitions. Native exception reasons include generic, IT, business, and processing timeout. Do not add invented native statuses such as “Testing” or “AwaitingApproval.” [R03, R04]

Keep framework dispositions such as `ReviewRequired`, `RetryScheduled`, and `TestFixture` in framework data. For MVP, exhausted attempts remain in an exception state and appear in a review view. Do not depend on a native dead-letter transition until it is verified.

### 9.2 Retry policy

Define three separate layers:

- **Action retry:** retries one connector/API action.
- **Work retry:** creates a new processing attempt for the same work item.
- **Operator replay:** explicit re-execution or creation of a new item, depending on intent.

Avoid multiplying retry counts across these layers. Generate a command request ID once, outside the action's automatic retry loop.

Default business exceptions and uncertain outcomes to no automatic retry. Permit technical retries only when the workflow declares a safe effect strategy and the failure evidence meets policy.

Use a bounded attempt count, increasing delay with jitter, a maximum delay, and a deadline. Set the native availability delay using a validated transition sequence. Recheck delay, expiration, and queue pause controls when acquiring.

Custom dequeue filters can affect native ordering and eligibility behavior. Keep the native request minimal and validate delay/expiry handling in the integration suite. [R18]

### 9.3 Idempotency at the business boundary

For the reference Dataverse output, add a stable source key protected by an alternate key. A retry must create the record once or obtain the already-created record. It must not overwrite the first result with a new AI output without a deliberate business rule.

Test the failure window immediately after record creation but before `Complete`. On recovery, use the source key to find and validate the existing result.

Sending an email or creating an approval requires a different strategy. A local “sent” flag alone does not close the gap between the remote operation succeeding and the local receipt being saved. Without a provider idempotency mechanism or reliable reconciliation, mark an ambiguous result for review.

### 9.4 Watchdog behavior

The watchdog scans bounded pages of expired framework leases and native processing items without a valid framework attempt. It rechecks ownership immediately before changing anything.

For a lost attempt, invalidate its generation and record a timeout or unknown outcome. Default to review rather than automatic replay. A late worker must not overwrite the recovered state.

Use checkpoints only where they prove real progress. Do not run an unconditional heartbeat loop that can keep a hung business action alive forever. A lease extension cannot exceed the queue's configured maximum processing deadline.

Waiting for a human approval is not a heartbeat failure. Long-lived approval orchestration is outside MVP and needs a separate continuation design. Cloud-flow duration limits must be considered for that extension. [R19]

## 10. Agent-friendly testing

### 10.1 What a test proves

A queue-injection test proves behavior after the queue boundary. It does not prove that a mailbox trigger fires, that a source permission is valid, or that the intake mapper handles the real connector response.

Separate the suite into framework contract tests, worker tests, external integration tests, and AI quality evaluations. Report coverage by layer.

### 10.2 Execution and persistence

`StartTestRun` validates the environment and permission, snapshots test definitions and versions, and creates a durable run. A managed coordinator advances case executions through preparation, enqueue, observation, assertions, and cleanup.

The agent receives a test-run ID and can query progress. Closing the MCP host must not lose the run. Do not keep one synchronous tool call open for the entire suite.

Test outcomes include `Passed`, `Failed`, `Inconclusive`, and `Cancelled`. A missing permission, expired observation deadline, or unavailable evidence must not count as a pass.

The coordinator needs its own command deduplication and recovery controls. A completed business item is not the same as a completed test case.

### 10.3 Test isolation

Use a separate non-production Dataverse environment and test mailbox by default. Test workers use the same source version and business logic as production, but connection references bind them to approved test resources.

Store the execution profile in trusted server configuration. A payload field such as `isTest: true` must not authorize a different destination or suppress required actions.

Mock or fixture providers are allowed for fast component tests, but reports must label the skipped boundary. Such tests do not replace real-connector integration tests. Never describe a stubbed prompt test as an evaluation of the live prompt.

Namespace fixture deduplication keys by test-run/case identity, while preserving the original source key as provenance. Store test ownership outside the business payload where possible.

### 10.4 MVP assertions

Support a small declarative assertion language:

| Assertion | Evidence |
|---|---|
| Item outcome matches | Native final state and framework disposition. |
| Attempt bound holds | Attempt count and the absence of multiple active owners. |
| Output exists | Authorized read of the referenced target record. |
| Record count matches | Bounded, test-scoped query of an allowlisted table. |
| Field predicate holds | Exact value, non-null, allowed set, range, or bounded text rule. |
| Error matches | Stable category and code, not a fragile full connector error string. |
| Notification was recorded | Expected outbox event and delivery state. |
| No unwanted effect occurred | Test-scoped evidence in the known destination or sink. |

The runtime keeps these checks bounded and declarative: record-count evidence is read only from the registered `business` table for the current test run and case source identity, and unwanted-effect evidence counts additional test-owned business records for that same identity. The store adapter owns the fixed query shape; test definitions cannot supply a table, URL, FetchXML, or deletion expression. A saturated evidence page is inconclusive rather than silently passing.

An outbox event proves an alert was recorded. A sender success proves the connector accepted delivery. Neither alone proves the recipient read or even received the message in their inbox.

Do not allow arbitrary code, unrestricted FetchXML, arbitrary URLs, or arbitrary deletion expressions in test definitions. Assertions and setup actions must stay within registered tables and allowed fields.

### 10.5 AI extraction evaluation

Treat schema conformance and extraction quality as different tests. Validate required fields, allowed values, source-grounded facts, and missing-information behavior with deterministic rules where possible.

Run selected fixtures multiple times. Record prompt version, available model/deployment identifier, parameters that the platform exposes, timestamps, and all outcomes. Do not invent a model version the provider does not expose.

Use approved expected results. The same agent must not revise the expected answer after seeing a failure and then report the test as a success without review.

An LLM judge is optional later and must be separately versioned. It is not the sole MVP pass condition.

### 10.6 Reference test cases

At minimum, cover a valid email, required information missing, invalid JSON, unsupported contract version, duplicate intake, conflicting duplicate content, invalid prompt output, source unavailable in reference mode, transient failure before a write, failure after a successful write, lost completion response, stale-worker completion, lost wake-up, delayed retry, queue pause, authorization denial, notification failure, and test cleanup failure.

Add a real-mailbox test that sends a synthetic message, observes intake, and verifies exactly one target record for the controlled source key.

Cleanup must target only recorded fixture IDs. Wait for or reconcile active attempts before cleanup. Keep failed-test evidence by default until a retention policy permits removal.

## 11. Notifications and operations

### 11.1 Durable outbox

Persist the attempt outcome and its notification intent in the same lifecycle transaction where possible. A separate sender acquires pending outbox records and delivers them.

Use one unique event/destination key for each intended delivery. Sender retries have their own lease and delay. A lost provider response can still produce a duplicate external alert; document that limit and include a visible event ID.

Notification failure must not change a successful business item into a failed item. It must also not recursively create an unbounded chain of failure notifications.

For MVP, email notifications contain queue key, item/attempt IDs, safe error summary, disposition, and a link to the operations record or native flow run. Do not include raw email bodies or extracted personal data by default.

### 11.2 Configuration

Use environment variables for installation-level defaults and connection references for connections. Use queue configuration and notification-rule rows for per-queue policy.

Examples of installation defaults are maintenance enablement, default retention, portal base location, and the default notification destination key. Examples of queue policy are retry bounds, processing deadline, allowed contracts, and failure-notification rules.

Validate policy changes and store the effective policy revision on each attempt. A configuration edit must not silently change the rules applied halfway through that attempt.

Do not store secrets in ordinary text environment variables. Use supported secret/connection facilities. Microsoft's connector documentation specifically warns that text values used for client secrets are not secure. [R09]

### 11.3 Operations console

Provide a small model-driven app, not a separate dashboard project. Include views for available work, old backlog, processing attempts, review-required failures, pending notifications, and recent test runs.

An authorized operator can request a retry with a reason. The API rechecks item state, policy, and the expected current version before accepting the command.

A future Teams card should call that same controlled operation. A user ID inside card payload JSON is not proof of the responder's identity. The card's original attempt might also be stale by the time someone selects Retry.

## 12. MCP and agent development experience

### 12.1 Server scope

Start with a local stdio MCP server and a pinned official SDK. A TypeScript implementation is a reasonable default for schema and template tooling; keep the Dataverse business logic in C#.

Use delegated sign-in for local interactive development and a separate approved application identity for deployment automation where supported. Bind every session to an explicit tenant and environment profile. Credentials never enter tool arguments or logs.

The server calls the installed runtime, reads approved release metadata, and performs governed solution/template operations. It is not an unrestricted Dataverse or shell tool.

MCP provides tools, resources, and prompts with different control models. Resource availability does not ensure a host injects it into every task, and prompts require host/user support. [R20]

### 12.2 Proposed tool groups

| Group | Example tools |
|---|---|
| Inspect | `wq_get_environment`, `wq_get_framework_status`, `wq_list_queues`, `wq_get_item`, `wq_get_queue_health`. |
| Provision | `wq_plan_install`, `wq_apply_install`, `wq_plan_queue`, `wq_apply_queue`. |
| Build | `wq_get_template`, `wq_scaffold_process`, `wq_validate_process`, `wq_plan_deployment`. |
| Test | `wq_validate_payload`, `wq_start_test_run`, `wq_get_test_run`, `wq_get_test_evidence`. |
| Operate | `wq_request_retry`, restricted to the operator role and approved environments. |

Keep tools focused. Normal development agents do not need arbitrary `Complete` or `AcquireNext` access to production items. Customer workers use those runtime operations through their own connections.

Mutations return the tenant/environment identity, affected resource IDs, request ID, and result. Expensive queries paginate and redact payloads by default.

### 12.3 Installation and bootstrap

The bootstrap sequence is:

1. Inspect the selected tenant/environment and existing solution versions.
2. Check Dataverse, permissions, required metadata, connection readiness, and installed package compatibility.
3. Select an approved release from an allowlisted repository and verify its checksum/provenance.
4. Produce an installation plan with package versions, connection requirements, permissions, and any activation steps.
5. Obtain approval through a trusted human or deployment control, not a Boolean the agent can set itself.
6. Import packages in dependency order.
7. Bind approved connection references and environment values, then provision queue/configuration data.
8. Run health checks and a sandbox smoke test.
9. Enable the relevant flows only after checks pass.
10. Return a deployment record and any remaining manual actions.

Do not automatically install whatever happens to be the newest release. Prefer the configured compatible version. Upgrades are separate, approved operations.

Do not assume the MCP can create delegated Outlook/Teams connections, grant mailbox access, consent to an application, or buy/assign licenses. The installer reports these dependencies explicitly.

### 12.4 Agent instructions and validation

Ship short startup instructions plus versioned resources for architecture, API contracts, flow patterns, input schemas, testing, troubleshooting, and deployment.

The build workflow is: inspect -> plan -> scaffold -> implement business logic -> validate -> deploy to development -> run tests -> inspect evidence -> propose promotion.

`wq_validate_process` checks required lifecycle actions, failure paths, queue bindings, approved API versions, connection references, request-ID handling, schema references, and declared side-effect strategy.

It also detects production test destinations, raw queue-state writes, silent error handling, unconditional completion, and missing cleanup boundaries where these patterns are statically identifiable. Static validation is not a proof of arbitrary flow correctness.

Flow generation must use tested templates and documented solution-flow APIs. Microsoft documents managing solution-aware cloud flows through Dataverse, including flow definitions and connection references. [R21]

Do not use undocumented maker-portal endpoints or depend on browser automation for the supported installation path. If PAC CLI is used, isolate or serialize authentication-profile operations so concurrent agents cannot change each other's target environment.

## 13. Security and operational limits

### 13.1 Roles and authorization

Define separate framework administrator, deployment operator, producer, worker, operations reader, retry operator, and test operator roles. Test execution is denied in production by default.

Use Dataverse privileges and record access, queue ownership/sharing, and API-side checks. A friendly queue key is an address, not a secret or a permission.

Use existing table privileges for Custom API execution gates where appropriate; do not assume the solution can define arbitrary standalone privileges. [R08]

A queue worker cannot select arbitrary output tables or another tenant through payload JSON. A test assertion cannot turn a privileged coordinator into an unrestricted data reader. A retry operator cannot reset a currently processing item through an unchecked table edit.

Cloud/API work-queue access also needs Dataverse role controls; Microsoft identifies RBAC as the relevant control for those paths. [R10]

### 13.2 Untrusted content and supply chain

Treat emails, queue payloads, extracted text, diagnostics, and test fixtures as data, never as instructions for the development agent. A malicious email must not be able to request a solution import, change a webhook destination, or obtain credentials.

Pin release versions and schema hashes. Verify package integrity before import. Do not commit customer payloads, tenant secrets, mailbox content, or generated diagnostic bundles to the public repository.

For a future remote MCP service, perform a separate authorization and tenant-isolation design. Do not forward an MCP access token to Dataverse as though token audiences were interchangeable.

### 13.3 Capacity, licenses, and cost

Installation must report required Dataverse and Power Automate entitlements, connector dependencies, AI prompt capacity, and operational ownership. Licenses and request limits depend on the actual deployment. [R22, R19]

Measure the cost per work item as business actions plus lifecycle calls, test assertions, retries, polling, and notifications. Do not claim the framework is cost-neutral.

Load-test expected queue volumes, burst behavior, and record-storage growth. Default to bounded batches and conservative concurrency. Respect server throttling and retry guidance rather than continuously polling.

Monitor maintenance-flow liveness, sender backlog, old queued work, expired leases, and owner/connection failures. A watchdog cannot notify through the same environment when that environment is completely unavailable; native platform alerts and a separately operated external monitor can cover that larger failure domain.

## 14. ALM, upgrades, and repository design

### 14.1 Solution lifecycle

Develop framework assets in an unmanaged source environment and distribute managed runtime releases. Develop customer business flows in a separate customer solution, then use that customer's normal managed deployment process for higher environments. This follows Microsoft's solution lifecycle model. [R23]

Keep framework and customer publishers, component identities, and solution dependencies explicit. Never regenerate component IDs for every build.

Connection references and environment values are deployment inputs. Microsoft supports deployment-settings files to map them during automated solution imports. [R24]

Treat queue registrations and policy rows as provisioned configuration data unless a specific native component deployment path is verified. Preserve friendly keys across environments while allowing native GUIDs to differ.

### 14.2 Upgrade policy

Maintain compatibility across the framework solution, API contract, MCP package, templates, and business payload contracts. Publish a supported-version matrix in the release manifest.

Prefer additive changes. Breaking API changes receive new action names or a major version. Queue envelope changes use a new physical queue version.

Before an upgrade, inspect active attempts and policy compatibility. Drain or pause dispatch where required, without discarding incoming source events. During a business-worker cutover, prevent two incompatible worker versions from competing for the same queue.

Run post-import checks for connection bindings, enabled flows, roles, queue mappings, and smoke tests. Uninstalling and reinstalling the managed solution is not a rollback plan. Use a validated forward fix or an approved environment recovery plan.

### 14.3 Proposed repository layout

```text
/docs/
  architecture.md
  decisions/
  operations/
/src/
  plugins/
  mcp/
/solutions/
  core/
  testing/
  notifications-email/
/templates/
  shared-mailbox/
  dataverse-trigger/
/contracts/
  envelopes/
  operations/
  business-samples/
/tests/
  unit/
  dataverse-integration/
  flow-integration/
  mcp/
  fixtures/
/deploy/
  release-manifest/
  deployment-settings/
  validation/
```

Public fixtures must be synthetic. Package build logs and release reports must not contain customer connection tokens or raw production payloads.

## 15. Implementation plan

Build vertical slices with explicit completion gates. Do not start by producing a large MCP tool catalog before proving the runtime behavior.

### Phase 0: Prove the platform assumptions

| ID | Investigation | Required evidence before approval |
|---|---|---|
| P0-01 | Call native `Dequeue` through a cloud flow and a Custom API plug-in. | Recorded request/response contract and supported empty-queue behavior. |
| P0-02 | Compose dequeue, context update, attempt creation, and command receipt. | Rollback and lost-response tests establish the actual transaction boundary. |
| P0-03 | Run concurrent acquisition and duplicate request tests. | One active owner per item, and no second claim on a repeated acquisition request. |
| P0-04 | Exercise delay, expiry, pause, and every intended state transition. | Tested transition matrix and no early retry. |
| P0-05 | Verify native-table guards and framework security. | Direct-write denial for managed queues without breaking native operations or unrelated queues. |
| P0-06 | Import Core into a clean environment. | Actions are discoverable and callable without a custom connector or cross-solution child dependency. |
| P0-07 | Generate and deploy the local child/parent flow scaffold. | Both wake-up paths call the same implementation, with measured concurrency behavior. |
| P0-08 | Validate schemas, alternate keys, and metadata availability. | Schema dialect behavior, activated keys, supported native references, and input limits are documented. |

**Exit gate:** Resolve every blocking uncertainty. If the preferred atomic acquisition cannot be proved, select and test the safe fallback before the contract is frozen.

### Phase 1: Runtime foundation

Create the Core solution, source project structure, table definitions, keys, security roles, and policy model. Implement enqueue, queue/contract registration, command receipts, acquisition, status reads, completion, and failure.

Add plug-in unit tests for validation, command identity, policy resolution, authorization, and state rules. Add real Dataverse integration tests for native behavior; mocks cannot establish platform transaction or concurrency guarantees.

**Exit gate:** A controlled item can complete through the public APIs, and duplicate commands do not duplicate work or events.

### Phase 2: Reference business process

Build the shared-mailbox adapter, `ProcessOne`, event wake-up, and scheduled sweep. Add the extraction prompt, structured validation, sample target table, stable source key, and create-or-obtain behavior.

Capture caller/run metadata and complete the output/error contracts. Test malformed input and every failure point before and after the target write.

**Exit gate:** A real synthetic email and an injected equivalent snapshot both create the correct target record. A replay after a successful write does not create a second record.

### Phase 3: Recovery and operations

Implement leases, checkpoints, stale-generation checks, safe retry scheduling, watchdog recovery, intake-failure reporting, and the operations app.

Test cancellation, disabled wake-up flows, delayed work, lost completion responses, configuration changes, and orphaned processing items.

**Exit gate:** Work does not remain silently stuck. Unknown business outcomes are visible and do not trigger unsafe automatic replay.

### Phase 4: Durable notifications

Implement outbox creation and email delivery as an optional package. Add per-queue rules, redaction, destination validation, cooldown, sender retry, and delivery status.

**Exit gate:** A failed item produces one notification intent. Sender failures do not change business outcomes or cause recursive alert storms. Removing the optional sender does not break Core.

### Phase 5: Test harness

Build Testing tables, immutable test snapshots, run coordinator, fixture enqueueing, bounded assertions, evidence capture, repeat-run evaluation, and scoped cleanup.

Add independent golden results for the reference process. Deny production execution and arbitrary assertion queries by default.

**Exit gate:** Tests continue without an MCP connection, failures produce inspectable evidence, and incomplete evidence cannot yield a pass.

### Phase 6: MCP development workflow

Implement environment-bound authentication, read tools, contract resources, plan/apply provisioning, scaffolding, static validation, test execution, evidence retrieval, and restricted retry operations.

Keep installer logic separate from work-item operations. Add approval and release-integrity checks. Test supported agent hosts rather than assuming uniform resource/prompt support.

**Exit gate:** A developer can start with a clean development environment and an approved release, deploy the reference pattern, run tests, inspect evidence, and produce a promotion plan without undocumented platform endpoints.

### Phase 7: Release hardening

Build the managed release pipeline, compatibility manifest, upgrade tests, least-privilege tests, load tests, retention jobs, documentation, and operator runbooks.

Validate missing connections, insufficient licensing/capacity, owner departure, throttling, a failed upgrade, environment copy behavior, and uninstall dependencies.

**Exit gate:** Another developer can install the release from the published instructions. All mandatory acceptance tests pass, and documented limitations match observed behavior.

### 15.1 Workstream dependencies

The contract/runtime owner leads Phases 0 and 1. The flow/template owner can begin the reference scaffold during Phase 1 after the API contract stabilizes. Testing and security work start in Phase 0 and continue through every phase. The MCP build depends on a proven runtime and template contract, not the reverse.

Record each major choice as an architecture decision: native claim strategy, schema versioning, state authority, retry semantics, notification outbox, test isolation, child-flow boundaries, identity model, and upgrade compatibility.

## 16. Acceptance and release gates

| Gate | Required result |
|---|---|
| Clean install | Supported packages import, keys activate, API actions resolve, and health checks explain all missing prerequisites. |
| Intake duplicate | Same source/key/content produces one item. |
| Intake conflict | Same key with changed content is rejected and observable. |
| Acquisition concurrency | Parallel requests cannot process the same item as current owner. |
| Acquisition replay | Repeating one request returns the same result, not another item. |
| Completion replay | Lost response and retry preserve one completion and one event intent. |
| Delayed work | Item is not acquired early and is discovered after its delay without needing a fresh source event. |
| Missed wake-up | Scheduled sweep processes eligible backlog. |
| Paused queue | No new business processing starts. |
| Unsupported payload | Rejected before business effects. |
| Post-write failure | Existing target record is reused or reconciled without duplication. |
| Stale worker | Old attempt cannot complete, fail, or extend a newer attempt. |
| Unknown outcome | No unsafe automatic replay. |
| Notification failure | Business result is unchanged; delivery failure remains visible. |
| Test isolation | Production destinations and unrestricted cleanup are blocked. |
| Test evidence | A pass includes assertions against actual authorized output, not only a worker-reported status. |
| AI extraction | Structured and field-level quality checks pass against approved fixtures; repeat-run failures remain visible. |
| Authorization | Producer, worker, reader, operator, and installer boundaries are tested with separate identities. |
| Lifecycle bypass | Direct writes cannot invalidate framework invariants for supported managed queues. |
| Agent disconnection | Runtime and initiated tests continue without the MCP process. |
| Upgrade | Existing customer flows and retained evidence remain usable through a supported version transition. |
| Capacity | The reference load test publishes measured throughput, request usage, and known limits without extrapolating guarantees. |

No performance, latency, concurrency, or availability figures in this document are benchmark results. Initial settings are proposed defaults until measured.

## 17. Principal risks and final decisions

| Risk | Required response |
|---|---|
| Microsoft changes an underlying behavior | Keep native operations behind an adapter and run compatibility tests against supported environments. |
| The claim/receipt sequence is not atomic | Resolve in Phase 0; use a validated registration/reconciliation path, not an optimistic assumption. |
| A stale worker performs an external action | Require effect-specific idempotency or reconciliation. A lease is not remote cancellation. |
| Framework complexity exceeds its benefit | Keep the first business scenario narrow and optional integrations separate. |
| Queue schemas block evolution | Stable envelope plus versioned business contracts; new queue for a breaking envelope. |
| Agent claims a deployment or test passed without proof | Require deployment IDs, validation results, test IDs, and assertion evidence in completion reports. |
| Optional connectors block installation | Separate sender packages and validate each connection explicitly. |
| Cleanup removes deduplication or diagnostic evidence | Separate retention windows and respect active/review holds. |
| Framework notifications fail with the same environment | Keep native failure alerts and document the external-monitoring boundary. |

The first implementation decisions to finalize are the dequeue transaction strategy, the schema validator/dialect, the direct-write guard, supported authentication profiles, and the first release's host compatibility list.

The product promise should remain specific: **an agent can build and test a supported queue-based Power Automate process using documented contracts, while the installed runtime controls lifecycle state, recovery, and evidence.**

## 18. Primary-source register

Sources were checked on September 12, 2026. References support platform facts; the framework names, contracts, defaults, package structure, and implementation sequence are proposed design decisions.

- **R01.** Microsoft Learn, [Process work queues](https://learn.microsoft.com/en-us/power-automate/desktop-flows/work-queues-process).
- **R02.** Microsoft Learn, [Dequeue Action](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/webapi/reference/dequeue?view=dataverse-latest).
- **R03.** Microsoft Learn, [Manage work queues](https://learn.microsoft.com/en-us/power-automate/desktop-flows/work-queues-manage).
- **R04.** Microsoft Learn, [Work Queue Item table reference](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/reference/entities/workqueueitem).
- **R05.** Microsoft Learn, [AddWorkQueueItemProcessingHistoryEntry Action](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/webapi/reference/addworkqueueitemprocessinghistoryentry?view=dataverse-latest).
- **R06.** Microsoft Learn, [Manage cloud flow run history in Dataverse](https://learn.microsoft.com/en-us/power-automate/dataverse/cloud-flow-run-metadata).
- **R07.** Microsoft Learn, [Create child flows](https://learn.microsoft.com/en-us/power-automate/create-child-flows).
- **R08.** Microsoft Learn, [Create and use custom APIs](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/custom-api).
- **R09.** Microsoft Learn, [Use environment variables in solution custom connectors](https://learn.microsoft.com/en-us/connectors/custom-connectors/environment-variables).
- **R10.** Microsoft Learn, [Known limitations for work queues](https://learn.microsoft.com/en-us/power-automate/desktop-flows/work-queues-known-limitations).
- **R11.** Microsoft Learn, [Trigger flows when a row is added, modified, or deleted](https://learn.microsoft.com/en-us/power-automate/dataverse/create-update-delete-trigger).
- **R12.** Microsoft Learn, [Employ robust error handling](https://learn.microsoft.com/en-us/power-automate/guidance/coding-guidelines/error-handling).
- **R13.** Microsoft Learn, [Obtain immutable identifiers for Outlook resources](https://learn.microsoft.com/en-us/graph/outlook-immutable-id).
- **R14.** Microsoft Learn, [Work with alternate keys](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/define-alternate-keys-entity).
- **R15.** Microsoft Learn, [Database transactions](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/scalable-customization-design/database-transactions).
- **R16.** Microsoft Learn, [Do not use batch request types in plug-ins and workflow activities](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/best-practices/business-logic/avoid-batch-requests-plugin).
- **R17.** Microsoft Learn, [Optimistic concurrency](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/optimistic-concurrency).
- **R18.** Microsoft Learn, [Work queues actions](https://learn.microsoft.com/en-us/power-automate/desktop-flows/actions-reference/workqueues).
- **R19.** Microsoft Learn, [Limits of automated, scheduled, and instant flows](https://learn.microsoft.com/en-us/power-automate/limits-and-config).
- **R20.** Model Context Protocol, [Understanding MCP servers](https://modelcontextprotocol.io/docs/learn/server-concepts).
- **R21.** Microsoft Learn, [Work with cloud flows using code](https://learn.microsoft.com/en-us/power-automate/manage-flows-with-code).
- **R22.** Microsoft Learn, [Types of Power Automate licenses](https://learn.microsoft.com/en-us/power-platform/admin/power-automate-licensing/types).
- **R23.** Microsoft Learn, [Solution concepts](https://learn.microsoft.com/en-us/power-platform/alm/solution-concepts-alm).
- **R24.** Microsoft Learn, [Pre-populate connection references and environment variables for automated deployments](https://learn.microsoft.com/en-us/power-platform/alm/conn-ref-env-variables-build-tools).
