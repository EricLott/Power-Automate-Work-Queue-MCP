# Reference prompt binding

`ProcessOne` uses the Dataverse `Predict` bound action for the customer-owned
reference worker. The prompt model is an explicit flow parameter,
`qmcp_PromptModelId`; it must be supplied by the operator for the target
development environment. The generated candidate leaves this parameter empty,
and the flow remains Draft until its binding and the other live prerequisites
have been validated.

The action targets the `msdyn_aimodels` row selected by
`qmcp_PromptModelId`, calls `Microsoft.Dynamics.CRM.Predict`, and sends a
`requestv2` object with `@@odata.type` in the flow template (escaped so the actual request contains `@odata.type`) set to
`Microsoft.Dynamics.CRM.expando`. The Predict request uses version
`2.0` and a string in `requestv2.prompt` containing the v1.1 extraction prompt
followed by the acquired payload. Confirm that the selected tenant model
actually accepts this action, schema version, and request shape. A builtin
model is tenant-discovered configuration, not a globally portable hardcoded
model.

The generated flow reads the prediction text from
`body('Prompt')?['responsev2']?['predictionOutput']?['text']`. It trims the
text and optionally removes one exact lowercase Markdown JSON fence with an LF
after `json` and a closing fence. Multiple fences, prose, other fence labels,
and malformed content remain subject to strict Parse JSON failure. The schema
requires exactly `contact`, `category`, and `summary`; contact is a non-empty
string of at most 320 characters, category is `service` or `question`, and
summary is at most 4000 characters. `ValidateSender` also requires contact to
match the normalized sender address and the prediction operation status to be
`Success`.

The worker first looks for an existing record by protected business key. If absent, it extracts and creates the record. It then rereads and reconciles the single result against the source key, content hash and queue before completion. It calls `Complete` with the current attempt identity and one stable
record ID. A failed or timed-out completion retries the identical command once;
remaining uncertainty is left for watchdog recovery rather than calling `Fail`
after a possibly successful server write.

For a tenant experiment, save the original flow records and parameters first.
Bind only a synthetic development queue and approved prompt model, activate
the worker for the bounded test, and record the actual response path and model
metadata exposed by the tenant. Restore the original client data and
parameters, remove temporary bindings, and verify the framework flow is Draft
by readback. Keep mailbox intake, notification sender, and production
destinations disabled during this reference test.

The installed proof and its limitations are recorded in
[`reference-prompt-proof.md`](reference-prompt-proof.md). It demonstrates one
synthetic installed execution and does not certify prompt quality, portability
to another tenant, mailbox integration, clean or managed installation, or the
remaining acceptance gates.

Primary references: [Dataverse Predict](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/webapi/reference/predict?view=dataverse-latest), [PredictionSchema](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/webapi/reference/predictionschema?view=dataverse-latest), and [requestv2/responsev2 examples](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/code-interpreter).
