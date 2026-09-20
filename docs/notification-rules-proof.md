# Notification rules and safe destinations

Queue policy now supports bounded `NotificationRules` with event selection, enabled state, safe destination keys, cooldown enforcement, and an explicit `Safe` redaction mode. Existing policies that only contain `Destinations` remain compatible and use those keys for the historical event set. Rule destinations are selected per event, and disabled or nonmatching rules create no delivery intent.

Delivery records contain only stable queue/item/attempt references, event kind, destination key, lease state, retry state, a validated HTTPS operations link, and safe error codes. They do not copy the source envelope, raw message body, extracted personal data, or connector payload. `FinishEvent` records a rejected delivery without creating another notification event, preventing a sender failure from recursively generating an alert storm.

Local coverage is in `LifecycleTests.NotificationRulesRejectUnsafeDestinationKeys`, `LifecycleTests.NotificationRulesSelectEventsExcludeRawContentAndRenderOperationsLink`, `LifecycleTests.NotificationRulesRejectUnsafeOperationsBaseUrl`, `LifecycleTests.NotificationRulesApplyCooldownAcrossFailureEvents`, and `LifecycleTests.NotificationFailureDoesNotCreateRecursiveAlert`. The runtime suite passed 116 tests and the plug-in suite passed 49 after this change.

This is implementation and local safety evidence. A live tenant validation of persisted notification-rule configuration, cooldown behavior across multiple attempts, connector acceptance, recipient delivery, and restricted configuration identities remains open under #48, #49, #50, and G14.
