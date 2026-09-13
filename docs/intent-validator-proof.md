# Installed intent validator fault test

The installed flow rejected a schema-valid extraction whose intent quote was absent from the message. Run `78554eef-566c-448d-a255-89a1af12aa6a` passed its expected-failure assertion with `VALIDATEINTENT_FAILED`. Independent reads verified one attempt, native Exception/review, an empty output reference, no business row and no Complete command receipt. [Evidence](evidence/intent-validator-fault-2026-09-12.json) includes the exact injected value and runtime identifiers.

This is **validator fault injection, not AI-quality evidence**. Predict still ran, but `NormalizeExtraction` deliberately returned fixed JSON instead of the prediction. Sender, category and schema remained valid so the absent quote exercised `ValidateIntent`. The successful repeated AI-quality runs remain [separate](reference-quality-proof.md).

Generate the local candidate and test manifest:

```powershell
python scripts/generate_reference_fault.py --output-dir artifacts/intent-fault
```

The generator makes no tenant calls and refuses to overwrite an existing directory. It changes only `NormalizeExtraction.inputs`; the candidate retains the ordinary unbound template parameters. For an authorized synthetic development experiment, save the normal flow, bind the test queue and model, deploy this candidate as ProcessOne, and activate the worker/sweep/coordinator. Do not activate mailbox intake or notification delivery. Start the emitted manifest through the existing proof runner:

```powershell
python scripts/prove_reference_quality.py --binding artifacts/live/mcp-binding.json --fixture-ledger artifacts/live/fixture-ids.json --cases artifacts/intent-fault/intent-fault-cases.json --output artifacts/intent-fault-run.json --execute
# Reuse the unchanged manifest and output with --observe until terminal.
```

Stop the test flows afterward, restore the generated normal definitions with unbound parameters, and read back both definitions and Draft state. The recorded experiment completed that restoration. Its deployed fault candidate matched the generator output after removing only the three temporary binding values.

All 75 Python checks passed for the proof/generator change. Runtime and MCP code were unchanged from the preceding 235-test checkpoint. This test covers an absent intent quote, not every malformed output, provider behavior or remaining reference regression.
