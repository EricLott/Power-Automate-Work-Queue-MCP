# Contract snapshots and completion replay

New attempts persist the full effective contract (`Id`, `Dialect`, `Schema`, `Hash`) and policy. `ContractHash` remains available for compatibility. Attempts created before this change deserialize with `Contract: null`; their missing snapshots are not fabricated from today's contract registry. Both acquisition paths deep-copy the effective schema before persistence.

The opt-in development proof uses the registered synthetic queue and requires all seven framework/reference flows to be Draft. It rejects an in-place contract change, acquires one synthetic item, verifies the full contract and policy snapshot, then changes the current policy. The existing attempt must retain its original settings.

It creates one synthetic Dataverse business record, calls `Complete` and deliberately discards the successful response, then replays the same request twice. Native item state, business output, command receipt and outbox rows supply independent evidence. A changed output with the same completion request must return `REQUEST_CONFLICT`. No sender flow is activated. The synthetic output and pending event are retained; the original queue policy is restored with optimistic concurrency, apart from its monotonically increasing revision.

```powershell
python scripts/prove_contract_completion.py --binding artifacts/live/mcp-binding.json --fixture-ledger artifacts/live/fixture-ids.json --output artifacts/live/contract-completion-new.json --execute
```

Use a new evidence path for each run. Request IDs and original policy are saved before mutations. A failed or interrupted run requires inspection of that evidence and current tenant state before retrying; do not blindly restart. The runner intentionally discards a known successful response. It does not simulate an actual network outage or prove every connector timeout behavior.

## Installed result

The [tenant evidence](evidence/contract-completion-2026-09-12.json) passed the full focused sequence: immutable contract rejection, stored full contract/policy snapshot, later policy changes leaving that attempt unchanged, completion replay matching the persisted receipt, changed replay rejection, one Processed native item, one business record and one Pending outbox event. The queue policy was restored. All 211 local tests and eight archive round trips passed before the plug-in update and live proof.
