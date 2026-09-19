# Notification failure proof

The durable outbox keeps notification delivery separate from the business outcome. The runtime test `LifecycleTests.NotificationFailurePreservesWork` processes one synthetic item, claims its delivery event, finishes the event as rejected with `MAIL_OFFLINE`, and verifies that the native business outcome remains `Processed` while the event row remains durable for retry/failure handling.

The focused verification on 2026-09-19 passed:

```powershell
dotnet test tests/runtime/QueueFramework.Tests.csproj --no-restore --filter FullyQualifiedName~NotificationFailurePreservesWork --verbosity minimal
```

This is local synthetic runtime evidence. It does not prove a native Outlook connector timeout, provider acceptance, mailbox delivery, or the installed `EmailSender` flow's behavior. G14 remains open for those tenant connector checks.
