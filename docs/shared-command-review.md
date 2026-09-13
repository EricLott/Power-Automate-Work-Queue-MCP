# Shared command and global-action review

On 2026-09-13, installed metadata returned 24 qmcp_WQ APIs with bindingtype 0 and isfunction false. An authenticated POST to qmcp_WQ_GetQueueHealth containing only QueueKey, RequestId and DataJson returned ResultJson with Outcome Health. The [evidence](evidence/unbound-api-2026-09-13.json) records the verified organization, exact request/response and metadata at runtime baseline a976940.

Microsoft describes global actions as operations that are not bound to a table, with explicitly defined parameters; entity-bound actions automatically introduce Target. See [Custom API binding types and invocation](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/custom-api#select-a-binding-type).

The current LifecyclePlugin reads named InputParameters and writes ResultJson. Its Engine separates policy/authorization, validation, command identity, dispatch and persistence through IStore/DataverseStore. Receipt identity includes actor, operation and request ID; stored data includes the input fingerprint, actor, operation, reason, timestamp and durable result. The installed [completion replay proof](contract-completion-proof.md) verifies same-request results and exact REQUEST_CONFLICT for changed arguments, with one stored receipt and one event intent.

No external HTTP client or sleep is used in the runtime or API entrypoint. HTTP transport in proof scripts belongs to the development client, outside the installed plug-in. The separate native item guards/post-handler correctly consume Target from native Update contexts; that is not a requirement on callers of the global APIs. A global declaration does not make direct AcceptAcquire usable: [its ancestor guard remains enforced](direct-acquisition-proof.md).

To reproduce the read-only metadata check through the authenticated Dataverse CLI request wrapper, query:

```text
GET customapis?$select=uniquename,bindingtype,isfunction&$filter=startswith(uniquename,'qmcp_WQ_')
POST qmcp_WQ_GetQueueHealth
{"QueueKey":"<allowlisted synthetic queue>","RequestId":"<new UUID>","DataJson":"{}"}
```

Verify WhoAmI against the development binding first. Require the expected API set, no pagination left unread, and global action metadata for every result; then inspect ResultJson. This review does not replace separate-user security, managed upgrade or connector failure tests. The API entrypoint source was unchanged from the previously tested runtime; all 102 Python tests passed at the preceding checkpoint.
