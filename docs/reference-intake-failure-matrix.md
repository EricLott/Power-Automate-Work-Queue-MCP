# Reference intake and failure-window matrix

This matrix is the current P2-07 boundary record. It separates the installed synthetic snapshot path from the real shared-mailbox trigger and distinguishes native API response-discard evidence from a connector fault inside the installed flow.

| Scenario | Evidence | Boundary actually exercised | Current result |
|---|---|---|---|
| Real synthetic email through Intake | No authorized run; `Intake` remains Draft and no mailbox connection was enabled | Outlook trigger, HTML conversion and mailbox-to-queue handoff were not exercised | Open |
| Equivalent injected snapshot | [reference-quality-2026-09-19.json](evidence/reference-quality-2026-09-19.json), six synthetic cases through installed `SweepQueue` → `ProcessOne` → `TestCoordinator` | Dataverse queue, prompt, validation, business write, completion and coordinator assertions; Intake and EmailSender remained Draft | Three positives produced one verified record each; three negatives produced zero records |
| Malformed harness input | [harness-input-2026-09-12.json](evidence/harness-input-2026-09-12.json) | Public test-run input validation before run/item creation | Five invalid cases returned `INPUT_INVALID`; no new run or queue item |
| Missing/unsupported source content | [reference-quality-2026-09-19.json](evidence/reference-quality-2026-09-19.json) | Synthetic missing-sender and unsupported/ambiguous content through installed validation | Expected `Exception` results with no business record |
| Prompt/provider rejection | [reference-quality-proof.md](reference-quality-proof.md) and the retained original failed evaluation | Prompt action and validation behavior in the installed synthetic path; not a mailbox/provider outage | Provider rejection and earlier ambiguous-input defect remain visible; no general model-quality claim |
| Pre-write validation failure | [intent-validator-fault-2026-09-12.json](evidence/intent-validator-fault-2026-09-12.json) | Installed `ValidateIntent` fault before business write | `VALIDATEINTENT_FAILED`, one attempt, no business row and no Complete receipt |
| Post-write failure before Complete | [post-write-recovery-2026-09-20.json](evidence/post-write-recovery-2026-09-20.json) | Authorized synthetic Dataverse business write followed by abandoned completion and lease recovery | One target row was reused after review/retry; final native outcome `Processed` |
| Lost completion response | [contract-completion-2026-09-20.json](evidence/contract-completion-2026-09-20.json) | Native completion response deliberately discarded, then identical command replayed | One completion receipt, one business row and `Processed`; changed arguments rejected |
| Flow-specific lost connector response | No approved installed-flow fault injection exists | The generated `CompleteRetry`/`CompletionUnknown` wiring is statically checked, but the connector response-loss window inside `ProcessOne` is not injected | Open |

## Reconciliation

The controlled synthetic source and Dataverse failure windows provide reviewable evidence for the bounded reference path. The local simulator now also injects a response loss after durable `Complete`; its regression verifies one committed business record and no duplicate worker pass. This still does not satisfy the real-mailbox comparison criterion or prove that a connector timeout/lost response in the installed ProcessOne flow behaves identically to the native API response-discard proof. Those gaps remain linked to [P2-04](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/36), [P2-07](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/39), and [G17](https://github.com/EricLott/Power-Automate-Work-Queue-MCP/issues/86).
