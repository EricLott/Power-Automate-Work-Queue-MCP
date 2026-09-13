# Reference quality evaluation

The first six-case installed evaluation did **not** pass: four cases passed and two failed. [The evidence](evidence/reference-quality-2026-09-12.json) retains its original manifest, actual outcomes, independent native/business checks and the run ID. The test coordinator executed independently of the development client.

The explicit service request, explicit question, missing sender and longer service request met their expected outcomes. The embedded-instruction case failed at Predict: a separate call with the same synthetic input returned `InputContentFiltered`. The ambiguous message was incorrectly processed and created a business record. That is an abstention defect, not a passing result or an expectation to revise away. The AI-quality gate remains open.

The run also exposed a child-response routing gap. `Respond` previously depended only on successful `HasWork`, even when a failed business scope had been handled by `Fail`. The revised response handles all terminal/skipped statuses and returns the actual lifecycle outcome or `Unknown`. Uncertain completion remains owned by recovery and does not call business failure after a potentially successful completion. After the test flows were stopped, updated and resumed, the remaining cases finished, including a positive item after a rejected missing-sender item. This supports failure-path continuation; exact response latency and lost connector responses remain separate tests.

`scripts/prove_reference_quality.py` checks exact case membership, the native queue and deduplication identity, unchanged fixture input, native outcome, one matching business row for success, no business row for expected failure, expected fields, source/content hashes, run ownership and prompt provenance. A failed or incomplete coordinator run cannot pass. Observation clears a previous completion flag before making tenant calls; failures do not preserve a stale success. Summary grounding still requires review, and the script reports that limitation.

Prepare a synthetic development binding and fixture ledger, explicitly bind the reference worker/model and coordinator, then run:

```powershell
python scripts/prove_reference_quality.py --binding artifacts/live/mcp-binding.json --fixture-ledger artifacts/live/fixture-ids.json --cases templates/tests/mail-extraction-quality.json --output artifacts/live/quality-new.json
# Add --execute only for the approved tenant experiment.
# Reuse the same output and unchanged case manifest with --observe to read its run.
```

Default mode makes no tenant calls. The script never activates flows, sends mail, or calls `AdvanceTestRun`. Exit status 1 means the observations do not prove a passing run; inspect the persisted evidence. Use a new evidence filename for each independent run. Preserve a manifest copy if later refining fixtures: observation rejects a changed fixture hash. The first run's original manifest is embedded in the evidence document; the current fixture additionally requires a specific extraction-validation error for missing or ambiguous information.

At this checkpoint all 233 local tests and package round trips passed. Local success does not override the two tenant failures. Further work must enforce supported intent before business writes, distinguish provider rejection safely, and repeat the full cases without hiding earlier results. Mailbox integration remains separate.
