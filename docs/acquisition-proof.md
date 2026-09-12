# Acquisition handoff proof

Run `python scripts/prove_acquisition_handoff.py --binding <development-binding.json> --fixture-ledger <synthetic-fixtures.json> --output-dir <new-directory> --run-id <unique-run>` to validate local inputs without live calls. Add `--execute` for an authorized online experiment.

The binding requires `environmentUrl`, `organizationId`, and `environmentClass: development`. The fixture ledger requires UUID values for `queue`, `team`, `principal`, and `user`, plus a registered `queueKey` beginning `qmcp-proof-`. The fixture must already have the `mail.v1` contract, safe retry policy, suitable lease/delay settings, synthetic principal and owner-team access used by the reference proof. Use an isolated idle synthetic queue and an operator profile not shared with other concurrent work.

The utility verifies the organization and user before writes, rejects a previously used run ID and any existing output directory, and retains test-owned records as evidence. It temporarily sets the non-production principal's receipt fault injection and restores its original document in `finally`. If the process is forcibly terminated or restoration fails, use the retained `original-principal.json` to restore that exact synthetic profile before further work.

The proof checks rollback, concurrent claim ownership, receipt replay, output creation, completion replay and delayed retry with reacquisition. It allows a bounded delay of at most 55 seconds and fails if the selected fixture policy cannot meet that bound. No flow is activated and no external message is sent.

Both the original scratch implementation and the committed parameterized wrapper passed in the development tenant. The wrapper repeat used the freshly deployed package and completed both synthetic items after checking rollback, concurrency, replay and delayed retry. See [recorded results](evidence/acquisition-handoff-2026-09-12.json). This focused experiment does not close the full acceptance matrix.
