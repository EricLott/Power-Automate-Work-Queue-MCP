# Notification failure proof

The durable outbox keeps notification delivery separate from the business outcome. The runtime test `LifecycleTests.NotificationFailurePreservesWork` processes one synthetic item, claims its delivery event, finishes the event as rejected with `MAIL_OFFLINE`, and verifies that the native business outcome remains `Processed` while the event row remains durable for retry/failure handling.

The focused verification on 2026-09-19 passed:

```powershell
dotnet test tests/runtime/QueueFramework.Tests.csproj --no-restore --filter FullyQualifiedName~NotificationFailurePreservesWork --verbosity minimal
```

This is local synthetic runtime evidence. It does not prove a native Outlook connector timeout, provider acceptance, mailbox delivery, or the installed `EmailSender` flow's behavior. G14 remains open for those tenant connector checks.

The companion [notification rules proof](notification-rules-proof.md) covers safe destination-key validation, event-specific selection, raw-content exclusion, and non-recursive sender failure behavior in the runtime model.

## Optional-package independence checkpoint — 2026-09-20

The candidate package boundary was independently checked. [WQCore](evidence/optional-package-independence-2026-09-20.json) contains the Dataverse connection reference but no Outlook connector or notification sender reference; `WQNotificationsEmail` owns the Outlook connection and sender flow. The source invariant is enforced by `FlowInvariantTests.test_optional_sender_connector_is_not_required_by_core`, and the package hashes/entry counts are recorded in the redacted evidence.

This advances P4-04's Core-without-mail-credentials criterion and does not imply live sender validation. Provider throttling, expired sender leases, connection loss, lost provider responses, Outlook acceptance and recipient delivery remain open.
