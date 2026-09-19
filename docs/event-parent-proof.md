# Event parent and child-flow proof

The scheduled parent path is independently covered by the installed reference checkpoint. This document records the separate event-parent attempt required by P0-07.

## 2026-09-19 authorized tenant attempt

Using the explicit development binding, the harness saved the installed `ProcessOne` and `OnQueueChanged` workflow records, bound both to the synthetic queue, activated them temporarily, and called only the public `qmcp_WQ_Enqueue` API. It did not call Acquire, Complete, or any business connector directly. The synthetic item remained `Queued` through the bounded observation window; no matching `workflowlogs` row was found and no child `ProcessOne` run was observed.

The harness restored both workflow records. Independent readback confirmed `ProcessOne` is Draft with a Request trigger and `OnQueueChanged` is Draft with an `OpenApiConnectionWebhook` trigger. The synthetic item was then reconciled through PrepareAcquire, native Dequeue, ResolveAcquire and Fail, ending in `Exception`/`ReviewRequired` with no business output and no active attempt. Redacted details are in [event-parent-2026-09-19.json](evidence/event-parent-2026-09-19.json).

This is an inconclusive tenant observation, not a pass or a claim that webhook triggers are unsupported. P0-07 remains In Progress because the event wake-up path and aggregate concurrency requirement are still unproven.
