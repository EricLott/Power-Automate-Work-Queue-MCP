# Installed reference prompt proof

On 2026-09-12, the generated customer `ProcessOne` completed synthetic mail through the installed scheduled flow and AI Builder Predict action in the authorized development environment. The installed test coordinator independently passed run `7310d600-2863-4605-90bc-4908e6fbf0d3`. No CLI acquisition, completion, or coordinator advance call performed the work.

[Machine-readable evidence](evidence/reference-prompt-integration-2026-09-12.json) preserves the failed original run as well as the successful revised run. The original AI response wrapped valid-looking fields in a Markdown JSON fence; the item moved to review and no target record existed. Its generic failure code does not independently identify the exact failed action. The revised prompt requests raw JSON, and the flow can remove one exact lowercase JSON fence followed by LF before applying strict output validation. This successful run does not prove that optional normalization branch executed.

The revised worker validates the sender, reconciles the protected business key, source key, content hash and queue, and then calls Complete. Completion is outside the business failure scope: an uncertain response retries identical command parameters before leaving an unresolved outcome for recovery. This run did not inject a lost connector response; that flow-specific failure window remains open.

Independent reads found one native Processed item, one attempt, no review flag, and one business record. The record contained the expected contact/category and a summary grounded in this synthetic message, prompt version `mail-extraction-v1.1`, model `gpt-41-mini-2025-04-14`, and prediction ID. This single example is not an extraction-quality certification. The six-case fixture includes ambiguous input, missing sender and embedded instructions; its repeated tenant evaluation remains separate work.

The prompt model ID remains an explicit environment binding. This tenant exposes a builtin prompt model with a `requestv2.prompt` contract; compatibility must be checked for another environment. The generated candidates remain unbound and disabled. The test saved generated clientdata directly with temporary synthetic bindings; it did not reimport the rebuilt solution packages. Local package build, round trips and all 223 tests passed at this checkpoint.

The mailbox intake and notification sender were never activated. Test records are retained as evidence. Reference test flows are returned to Draft between experiments.

API references: [Dataverse Predict](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/webapi/reference/predict?view=dataverse-latest), [PredictionSchema](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/webapi/reference/predictionschema?view=dataverse-latest), and [documented requestv2/responsev2 examples](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/code-interpreter).
