# Notification failure proof

The durable outbox keeps notification delivery separate from the business outcome. The runtime test `LifecycleTests.NotificationFailurePreservesWork` processes one synthetic item, claims its delivery event, finishes the event as rejected with `MAIL_OFFLINE`, and verifies that the native business outcome remains `Processed` while the event row remains durable for retry/failure handling.

The focused verification on 2026-09-19 passed:

```powershell
dotnet test tests/runtime/QueueFramework.Tests.csproj --no-restore --filter FullyQualifiedName~NotificationFailurePreservesWork --verbosity minimal
```

This is local synthetic runtime evidence. It does not by itself prove a native Outlook connector timeout, provider acceptance, mailbox delivery, or the installed `EmailSender` flow's behavior; the native failure checkpoint below supplies the tenant-backed failure observation.

The companion [notification rules proof](notification-rules-proof.md) covers safe destination-key validation, event-specific selection, raw-content exclusion, and non-recursive sender failure behavior in the runtime model.

The runtime boundary suite also covers an expired sender lease being reclaimed, a throttling rejection retaining the event while the business item remains `Processed`, and a lost-provider-response replaying the same durable delivery intent. These are deterministic delivery-state regressions, not native Outlook throttling, connection-loss, connector-acceptance, or recipient-delivery evidence.

## Optional-package independence checkpoint — 2026-09-20

The candidate package boundary was independently checked. [WQCore](evidence/optional-package-independence-2026-09-20.json) contains the Dataverse connection reference but no Outlook connector or notification sender reference; `WQNotificationsEmail` owns the Outlook connection and sender flow. The source invariant is enforced by `FlowInvariantTests.test_optional_sender_connector_is_not_required_by_core`, and the package hashes/entry counts are recorded in the redacted evidence.

This advances P4-04's Core-without-mail-credentials criterion and does not imply live sender validation. Provider throttling, expired sender leases, connection loss, lost provider responses, Outlook acceptance and recipient delivery remain open.

## Native EmailSender failure checkpoint — 2026-09-20

The reusable [native notification failure probe](../scripts/prove_native_notification_failure.py) temporarily activated only the installed `EmailSender` flow against the bound synthetic queue and an intentionally invalid recipient. The native flow returned through its failure branch: the selected durable event remained `Pending`, its retry count advanced from 2 to 3, and its error code became `SENDER_FAILED`. An independent native item read was byte/version unchanged before and after the sender attempt. The runner restored the original client data and Draft state with zero restoration errors. Redacted observations are in [native-notification-failure-2026-09-20.json](evidence/native-notification-failure-2026-09-20.json).

This closes the G14 acceptance criterion that a native delivery failure remains visible without changing the business result. It does not claim successful recipient delivery, provider acceptance, or timeout behavior; those are separate operational observations.
