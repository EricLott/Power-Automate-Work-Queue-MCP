# Event parent and child-flow proof

The scheduled parent path is independently covered by the installed reference checkpoint. This document records the separate event-parent attempt required by P0-07.

## 2026-09-19 authorized tenant attempts

Using the explicit development binding, the harness saved the installed `ProcessOne` and `OnQueueChanged` workflow records, bound both to the synthetic queue, activated them temporarily, and called only the public `qmcp_WQ_Enqueue` API. It did not call Acquire, Complete, or any business connector directly. The first attempt and a second attempt with a 30-second activation settle plus active-state readback both left the synthetic item `Queued`; each had zero matching `workflowlogs` rows and no observed child `ProcessOne` run.

The harness restored both workflow records after each attempt. Independent readback confirmed `ProcessOne` is Draft with a Request trigger and `OnQueueChanged` is Draft with an `OpenApiConnectionWebhook` trigger. Both synthetic items were reconciled through PrepareAcquire, native Dequeue, ResolveAcquire and Fail, ending in `Exception`/`ReviewRequired` with no business output and no active attempt. Redacted details are in [event-parent-2026-09-19.json](evidence/event-parent-2026-09-19.json).

This is an inconclusive tenant observation, not a pass or a claim that webhook triggers are unsupported. P0-07 remains In Progress because the event wake-up path and aggregate concurrency requirement are still unproven.

## Callback-registration inspection

The follow-up read-only inspection temporarily set the installed `OnQueueChanged` and `ProcessOne` workflow rows to Active, waited 30 seconds, and read back the `callbackregistrations` entity for `workqueueitem`. Both workflow rows reported Active, but the callback-registration query returned zero rows. The records were restored to Draft and independently verified after the inspection; no queue item was enqueued and no business data was changed.

This separates a workflow-row state from a materialized Dataverse event subscription. Direct workflow-row activation is therefore not sufficient evidence for P0-07. A supported activation/import path that creates the callback registration is still required; the preflight now fails `observableComplete` when an Active event flow has no `workqueueitem` registration. Redacted details are in [event-callback-registration-2026-09-19.json](evidence/event-callback-registration-2026-09-19.json).

## Supported solution-import attempt

The authorized tenant also received the scoped `WQReferenceSharedMailbox.zip` package with PAC `solution import --activate-plugins --publish-changes --force-overwrite`. PAC reported a successful import and publish, but the four reference workflow rows (`Intake`, `OnQueueChanged`, `ProcessOne`, and `SweepQueue`) all read back Draft and the `workqueueitem` callback-registration query remained empty. No queue item or business row was created by this attempt. Redacted details are in [event-activation-import-2026-09-19.json](evidence/event-activation-import-2026-09-19.json).

This records that the tested PAC import option did not establish an active cloud-flow subscription in this tenant; it does not rule out a maker-supported activation sequence or a different deployment package. P0-07 remains In Progress.

## Maker activation permission boundary

The authenticated Power Automate maker surface was opened at the exact authorized environment ID. The portal rejected the flow page with a permission error stating that the signed-in operator is not permitted to make flows in this environment and must switch to an environment where maker permissions are granted. No flow action was attempted and no state changed through the portal. Redacted details are in [event-maker-activation-2026-09-19.json](evidence/event-maker-activation-2026-09-19.json).

The Dataverse CLI identity can read and mutate the explicitly authorized records used by the tenant probes, but that does not establish Power Automate maker permission. P0-07 and follow-up #107 therefore remain open; the next supported activation attempt requires an operator with maker permission in this environment or an approved deployment path that creates the subscription.

The minimal supported remediation was then applied: PAC assigned the existing `Environment Maker` security role to the user-supplied operator in the authorized environment, and a direct Dataverse role readback confirmed the association. After a bounded propagation wait and a fresh authenticated maker session, the exact flow URL continued to return the same maker-permission denial. No flow action was attempted. This narrows the remaining blocker to Power Automate environment/licensing or service-side maker access propagation rather than the Dataverse role row alone. Evidence is in [event-maker-role-2026-09-19.json](evidence/event-maker-role-2026-09-19.json).
