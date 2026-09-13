# Direct acquisition rejection

The installed public qmcp_WQ_AcceptAcquire API rejected a direct request with exact ACQUISITION_HANDOFF_REQUIRED on 2026-09-13. Independent native reads matched including ETag; there were zero attempts for the synthetic item and zero acceptance receipts for the attempted request. [Evidence](evidence/direct-acquisition-2026-09-13.json) records the organization, item and request IDs. Runtime baseline was 7483de7 and the installed solution version was 0.1.0.0.

This verifies the production plug-in requires its registered acquisition post-handler ancestry. Positive acquisition, durable resolution/replay and concurrent ownership are covered by [the handoff proof](acquisition-proof.md) and the subsequent installed reference flow runs. It does not claim to prevent arbitrary external business actions performed outside the framework or prove separate-user authorization.

```powershell
python scripts/prove_direct_acquisition.py --binding artifacts/live/mcp-binding.json --fixture-ledger artifacts/live/native-pause-fixture.json --output artifacts/live/direct-acquisition-new.json
# Add --execute for the authorized synthetic tenant check.
```

The fixture ledger must contain the exact synthetic itemId, native queue and registered user. Default mode makes no tenant calls. Execution verifies organization/user, seven Draft flows, matching native queue and queued item, then attempts direct acceptance. It makes no preparation, native dequeue, business write or cleanup call. Evidence paths cannot be overwritten. Only the exact structured rejection passes; generic failure, changed item, unexpected attempts or receipts fail.

Four targeted tests cover exact-fault parsing, dry run, mocked successful rejection, generic failure and changed ETag rejection. The full Python checkpoint passed after these changes. The synthetic item remains queued, and no flow definition or queue policy changed.
