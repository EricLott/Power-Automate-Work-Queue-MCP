# Acquisition concurrency and replay

The installed runtime passed the bounded acquisition identity experiment on 2026-09-13 UTC. Two distinct PrepareAcquire requests ran concurrently: one returned Prepared and the other returned the exact ACQUIRE_BUSY fault on the initial calls. Two concurrent identical replays returned the original Prepared result. Changed arguments under the winning request ID returned REQUEST_CONFLICT. Independent native item reads, including row versions, were unchanged by preparation and replay.

The proof then deliberately discarded the native Dequeue response. Independent reads found one Processing item and one Queued item. ResolveAcquire and its identical replay returned the same item, attempt and ownership generation. Independent attempt queries found exactly one attempt for the acquired item and none for the second. A synthetic business record was independently read before Complete; the final native states were Processed and Queued. The second item remains queued as evidence and must be accounted for before another idle-queue experiment.

[Tenant evidence](evidence/acquisition-identity-2026-09-13.json) includes exact synthetic request/item identifiers, environment and runtime version metadata. The earlier [handoff experiment](acquisition-proof.md) additionally exercised concurrent native dequeue and rollback before receipt persistence. Together these cover the bounded concurrency/replay criteria of #14, #73 and #74. The broader transaction-boundary and exhaustive fault-injection work in #13 remains open; these results do not close it or establish every crash boundary. The implemented guarded handoff in completed #29 provides the tested acquisition path for this experiment.

This was one authenticated development actor, two concurrent requests and two synthetic items. It is not a multi-user security test, load test, real connector timeout or network outage. The native response was lost deliberately at the client boundary. All seven flows were verified Draft before execution and were not changed; no sender ran. The first preflight attempt stopped before enqueue because its idle check included retained terminal history. The corrected preflight checks Queued and Processing rows; the final run passed without transport-error retries.

```powershell
python scripts/prove_acquisition_identity.py --binding artifacts/live/mcp-binding.json --fixture-ledger artifacts/live/fixture-ids.json --output-dir artifacts/live/acquisition-identity-new --run-id identity-new
# Add --execute for an authorized synthetic tenant run.
```

Use a fresh run ID and evidence directory and an allowlisted queue with no Queued or Processing items. The script records request and ownership identifiers before dependent work; inspect saved evidence and tenant state before recovering a failed execution. It does not automatically resume uncertain ownership. The default validates inputs without tenant calls.

All 105 Python tests passed, including the full mocked experiment and a negative case proving that generic transport failures cannot pass the distinct-request assertion. Those tests verify the proof script; the linked tenant evidence establishes the observed platform behavior. The deployed runtime was unchanged from the previous 266-test runtime/package checkpoint (93 runtime, 40 plug-in, 102 Python, 31 MCP).
