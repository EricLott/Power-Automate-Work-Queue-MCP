using Newtonsoft.Json.Linq;
namespace QueueFramework;
public sealed partial class Engine
{
    static readonly HashSet<string> NotificationKinds = new(StringComparer.Ordinal) { "Processed", "RetryScheduled", "ReviewRequired", "IntakeFailure" };
    readonly IStore store;
    readonly Func<DateTime> clock;
    public Engine(IStore store, Func<DateTime>? clock = null) { this.store = store; this.clock = clock ?? (() => DateTime.UtcNow); }
    public static readonly IReadOnlyDictionary<string, string> Roles = new Dictionary<string, string>
    {
        ["RegisterQueue"] = "deployment",
        ["RegisterContract"] = "deployment",
        ["Enqueue"] = "producer",
        ["AcquireNext"] = "worker",
        ["PrepareAcquire"] = "worker",
        ["AcceptAcquire"] = "worker",
        ["ResolveAcquire"] = "worker",
        ["Checkpoint"] = "worker",
        ["Complete"] = "worker",
        ["Fail"] = "worker",
        ["RequestRetry"] = "retry",
        ["ReportIntakeFailure"] = "producer",
        ["GetItemStatus"] = "reader",
        ["GetQueueHealth"] = "reader",
        ["RecoverExpiredAttempt"] = "watchdog",
        ["RunMaintenance"] = "watchdog",
        ["ApplyRetention"] = "watchdog",
        ["ClaimEvent"] = "sender",
        ["FinishEvent"] = "sender",
        ["StartTestRun"] = "tester",
        ["SeedRetentionFixture"] = "tester",
        ["CancelTestRun"] = "tester",
        ["GetTestRun"] = "tester",
        ["AdvanceTestRun"] = "coordinator",
        ["CleanupTestRun"] = "coordinator"
    };
    public string Execute(Command command, Actor actor)
    {
        if (command == null || actor == null || command.Operation == null || command.QueueKey == null || command.DataJson == null || actor.Roles == null) throw new Fault("INPUT_INVALID");
        if (!Roles.TryGetValue(command.Operation, out var role) || !actor.Has(role) || string.IsNullOrWhiteSpace(actor.Id)) throw new Fault("FORBIDDEN");
        if (command.QueueKey.Length < 1 || command.QueueKey.Length > 100) throw new Fault("INPUT_INVALID");
        var data = Json.Object(command.DataJson);
        var read = command.Operation == "GetItemStatus" || command.Operation == "GetQueueHealth" || command.Operation == "GetTestRun" || command.Operation == "ResolveAcquire";
        if (!read && !Guid.TryParse(command.RequestId, out _)) throw new Fault("REQUEST_ID_INVALID");
        return store.Atomic(() =>
        {
            var policy = Get<QueuePolicy>("definition", command.QueueKey);
            if (command.Operation != "RegisterQueue" && policy == null) throw new Fault("QUEUE_NOT_FOUND");
            if (policy != null && !actor.Has("deployment") && !actor.Roles.Contains("administrator") &&
                (!policy.Grants.TryGetValue(actor.Id, out var rights) || !rights.Contains(role))) throw new Fault("FORBIDDEN");
            string key = Json.Hash(actor.Id + "|" + command.Operation + "|" + command.RequestId);
            string fingerprint = Json.Fingerprint(command);
            if (!read)
            {
                var previous = Get<Receipt>("command", key);
                if (previous != null) { if (previous.Fingerprint != fingerprint) throw new Fault("REQUEST_CONFLICT"); return previous.Result; }
            }
            object result = Dispatch(command, actor, data, policy);
            string output = Json.Write(result);
            if (!read) Add("command", key, command.QueueKey, new Receipt { Fingerprint = fingerprint, Result = output, ActorId = actor.Id, Operation = command.Operation, Reason = (string?)data["reason"] ?? "", Created = clock() });
            return output;
        });
    }
    object Dispatch(Command c, Actor a, JObject d, QueuePolicy? p)
    {
        switch (c.Operation)
        {
            case "RegisterQueue": return RegisterQueue(c, d);
            case "RegisterContract": return RegisterContract(c, d);
            case "Enqueue": return Enqueue(c, d, p!);
            case "AcquireNext": return Acquire(c, a, d, p!);
            case "PrepareAcquire": return PrepareAcquire(c, a, d, p!);
            case "AcceptAcquire": return AcceptAcquire(c, a, d, p!);
            case "ResolveAcquire": return ResolveAcquire(c, a, p!);
            case "Checkpoint": return Checkpoint(c, a, d);
            case "Complete": return Complete(c, a, d);
            case "Fail": return Fail(c, a, d);
            case "RequestRetry": return Retry(c, d, p!);
            case "GetItemStatus": return Status(c);
            case "GetQueueHealth": return Health(c, p!);
            case "RecoverExpiredAttempt": return Recover(c);
            case "ReportIntakeFailure": return IntakeFailure(c, d, p!);
            case "RunMaintenance": return Maintenance(c, d);
            case "ApplyRetention": return Retention(c, p!);
            case "ClaimEvent": return ClaimEvent(c, a);
            case "FinishEvent": return FinishEvent(c, a, d);
            case "StartTestRun": return StartTest(c, a, d);
            case "SeedRetentionFixture": return SeedRetentionFixture(c, a, d, p!);
            case "CancelTestRun": return CancelTest(c);
            case "GetTestRun": return GetTest(c);
            case "AdvanceTestRun": return AdvanceTest(c);
            case "CleanupTestRun": return CleanupTest(c);
            default: throw new Fault("OPERATION_UNSUPPORTED");
        }
    }
    T? Get<T>(string kind, string key) where T : class { var r = store.Get(kind, key); return r == null ? null : Json.Read<T>(r.Body); }
    Row Add(string kind, string key, string queue, object body) => store.Add(new Row { Kind = kind, Key = key, Queue = queue, Body = Json.Write(body), Updated = clock() });
    Row AddAt(string kind, string key, string queue, object body, DateTime updated)
    {
        var document = Json.Object(Json.Write(body));
        document["_qmcpFixtureCreated"] = updated;
        return store.Add(new Row { Kind = kind, Key = key, Queue = queue, Body = document.ToString(Newtonsoft.Json.Formatting.None), Updated = updated });
    }
    void Save<T>(string kind, string key, T body)
    {
        var r = store.Get(kind, key) ?? throw new Fault("NOT_FOUND");
        // Cancellation is a durable safety bit. A stale worker snapshot must
        // never clear it while persisting a later attempt outcome.
        if (kind == "itemcontext" && body is ItemContext context && Json.Read<ItemContext>(r.Body).TestCancelled) context.TestCancelled = true;
        long version = r.Version; r.Body = Json.Write(body!); r.Updated = clock(); store.Put(r, version);
    }
    static string Required(JObject data, string name, int max = 200) { var t = data[name]; if (t?.Type != JTokenType.String || string.IsNullOrWhiteSpace((string?)t) || ((string)t!).Length > max) throw new Fault("INPUT_INVALID"); return (string)t!; }
    object RegisterQueue(Command c, JObject d)
    {
        QueuePolicy p;
        try { p = Json.ToObject<QueuePolicy>(d); }
        catch (Fault) { throw new Fault("POLICY_INVALID"); }
        if (p.Contracts == null || p.Destinations == null || p.NotificationRules == null || p.Grants == null || p.Grants.Any(g => g.Value == null)) throw new Fault("POLICY_INVALID");
        if (!Guid.TryParse(p.NativeQueueId, out _) || p.MaxAttempts < 1 || p.MaxAttempts > 20 || p.LeaseSeconds < 1 || p.DeadlineSeconds < p.LeaseSeconds || p.DeadlineSeconds > 86400 ||
           p.RetryBaseSeconds < 1 || p.RetryMaxSeconds < p.RetryBaseSeconds || p.RetryMaxSeconds > 86400 || p.Contracts.Length == 0 || p.Destinations.Length > 5 || p.Grants.Count == 0 || p.NotificationRules.Length > 20 || !SafeOperationsBaseUrl(p.OperationsBaseUrl) ||
           p.Retention == null || p.Retention.PayloadDays < 1 || p.Retention.PayloadDays > 3650 || p.Retention.ReceiptDays < 1 || p.Retention.ReceiptDays > 3650 ||
           p.Retention.AttemptDays < 1 || p.Retention.AttemptDays > 3650 || p.Retention.EvidenceDays < 1 || p.Retention.EvidenceDays > 3650 || p.Retention.ErrorDays < 1 || p.Retention.ErrorDays > 3650) throw new Fault("POLICY_INVALID");
        if (p.Grants.Any(g => g.Value.Any(r => !Roles.Values.Contains(r))) || p.Destinations.Any(x => !SafeDestinationKey(x)) || p.NotificationRules.Any(rule =>
            rule.Events == null || rule.Events.Length == 0 || rule.Events.Length > 4 || rule.Events.Any(kind => !NotificationKinds.Contains(kind)) ||
            !SafeDestinationKey(rule.Destination) || rule.CooldownSeconds < 0 || rule.CooldownSeconds > 86400 || rule.Redaction != "Safe")) throw new Fault("POLICY_INVALID");
        p.NativeQueueId=Guid.Parse(p.NativeQueueId).ToString();
        var previous = store.Get("definition", c.QueueKey);
        if (previous == null) { p.Revision = 1; Add("definition", c.QueueKey, c.QueueKey, p);Add("queuebinding",p.NativeQueueId,c.QueueKey,new { QueueKey=c.QueueKey }); }
        else
        {
            if (previous.Version != c.ExpectedVersion) throw new Fault("VERSION_CONFLICT");
            var old = Json.Read<QueuePolicy>(previous.Body);
            if (old.NativeQueueId != p.NativeQueueId) throw new Fault("QUEUE_MIGRATION_REQUIRED");
            p.Revision = old.Revision + 1; Save("definition", c.QueueKey, p);
        }
        return new { Outcome = "Registered", Revision = p.Revision, Version = store.Get("definition", c.QueueKey)!.Version };
    }
    object RegisterContract(Command c, JObject d)
    {
        Contract contract;
        try { contract = Json.ToObject<Contract>(d); }
        catch (Fault) { throw new Fault("SCHEMA_UNSUPPORTED"); }
        if (contract.Id == null || contract.Schema == null) throw new Fault("SCHEMA_UNSUPPORTED");
        if (contract.Id.Length < 1 || contract.Id.Length > 100 || contract.Dialect != "http://json-schema.org/draft-07/schema#") throw new Fault("SCHEMA_UNSUPPORTED");
        Schema.CheckDefinition(contract.Schema);
        contract.Hash = Json.Fingerprint(contract.Schema);
        var key = Json.Hash(c.QueueKey + "|" + contract.Id); var existing = Get<Contract>("contract", key);
        if (existing != null && existing.Hash != contract.Hash) throw new Fault("CONTRACT_IMMUTABLE");
        if (existing == null) Add("contract", key, c.QueueKey, contract);
        return new { Outcome = "Registered", contract.Hash };
    }
    Contract ValidateEnvelope(string queue, JObject envelope, QueuePolicy policy)
    {
        if (envelope.Properties().Any(p => !new[] { "envelopeVersion", "contract", "correlationId", "deduplicationKey", "source", "payload" }.Contains(p.Name))) throw new Fault("INPUT_INVALID");
        if ((string?)envelope["envelopeVersion"] != "1.0") throw new Fault("INPUT_INVALID");
        Required(envelope, "correlationId", 100); Required(envelope, "deduplicationKey", 1024);
        string id = Required(envelope, "contract", 100);
        if (!(envelope["source"] is JObject) || !(envelope["payload"] is JObject)) throw new Fault("INPUT_INVALID");
        if (!policy.Contracts.Contains(id)) throw new Fault("CONTRACT_UNSUPPORTED");
        var contract = Get<Contract>("contract", Json.Hash(queue + "|" + id)) ?? throw new Fault("CONTRACT_UNSUPPORTED");
        Schema.Validate(envelope["payload"]!, contract.Schema); return contract;
    }
    static Contract Snapshot(Contract contract) => new Contract
    {
        Id = contract.Id,
        Dialect = contract.Dialect,
        Schema = (JObject)contract.Schema.DeepClone(),
        Hash = contract.Hash
    };
    object Enqueue(Command c, JObject envelope, QueuePolicy policy)
    {
        ValidateEnvelope(c.QueueKey, envelope, policy);
        string source = Required(envelope, "deduplicationKey", 1024);
        string hash = Json.Fingerprint(new { contract = envelope["contract"], source = envelope["source"], payload = envelope["payload"] });
        string key = Json.Hash(c.QueueKey + "|" + source);
        var duplicate = Get<ItemContext>("itemcontext", key);
        if (duplicate != null)
        {
            if (duplicate.ContentHash != hash) throw new Fault("KEY_CONTENT_CONFLICT");
            return new { Outcome = "Existing", duplicate.ItemId };
        }
        var now = clock(); var native = store.NativeCreate(new NativeItem { Id = Guid.NewGuid().ToString(), Queue = c.QueueKey, UniqueKey = key, Input = envelope.ToString(Newtonsoft.Json.Formatting.None), Created = now, Available = now, Expires = now.AddDays(7) });
        Add("itemcontext", key, c.QueueKey, new ItemContext { ItemId = native.Id, SourceKey = Json.Hash(source), ContentHash = hash, CorrelationId = (string)envelope["correlationId"]! });
        return new { Outcome = "Enqueued", ItemId = native.Id };
    }
    string AcquisitionKey(string queue, string actor) => Json.Hash("acquire|" + actor + "|" + queue);
    object PrepareAcquire(Command c, Actor actor, JObject data, QueuePolicy policy)
    {
        if (!policy.Enabled) return new { Outcome = "QueuePaused" };
        var key = AcquisitionKey(c.QueueKey, actor.Id); var now = clock(); var row = store.Get("cursor", key);
        if (row != null)
        {
            var prior = Json.Read<AcquisitionIntent>(row.Body);
            if (prior.Status == "Prepared" && prior.Expires > now)
            {
                if (prior.RequestId != c.RequestId) throw new Fault("ACQUIRE_BUSY");
                return new { Outcome = "Prepared", NativeQueueId = policy.NativeQueueId, prior.Expires, prior.RequestId };
            }
            var replacement = new AcquisitionIntent { RequestId = c.RequestId, ActorId = actor.Id, Expires = now.AddSeconds(policy.LeaseSeconds), Status = "Prepared", Caller = Caller(data) };
            store.Put(new Row { Kind = "cursor", Key = key, Queue = c.QueueKey, Body = Json.Write(replacement), Updated = now }, row.Version);
            return new { Outcome = "Prepared", NativeQueueId = policy.NativeQueueId, replacement.Expires, replacement.RequestId };
        }
        var intent = new AcquisitionIntent { RequestId = c.RequestId, ActorId = actor.Id, Expires = now.AddSeconds(policy.LeaseSeconds), Caller = Caller(data) };
        Add("cursor", key, c.QueueKey, intent);
        return new { Outcome = "Prepared", NativeQueueId = policy.NativeQueueId, intent.Expires, intent.RequestId };
    }
    object AcceptAcquire(Command c, Actor actor, JObject data, QueuePolicy policy)
    {
        if (!policy.Enabled) throw new Fault("QUEUE_PAUSED");
        var key = AcquisitionKey(c.QueueKey, actor.Id); var row = store.Get("cursor", key) ?? throw new Fault("ACQUIRE_INTENT_NOT_FOUND");
        var intent = Json.Read<AcquisitionIntent>(row.Body);
        if (intent.ActorId != actor.Id || intent.RequestId != c.RequestId || intent.Status != "Prepared") throw new Fault("ACQUIRE_INTENT_INVALID");
        if (intent.Expires <= clock()) throw new Fault("ACQUIRE_INTENT_EXPIRED");
        var native = store.NativeGet(c.ItemId) ?? throw new Fault("ITEM_NOT_FOUND");
        if (native.Queue != c.QueueKey || native.Status != "Processing") throw new Fault("NATIVE_ITEM_INVALID");
        if (native.Expires <= clock()) throw new Fault("ITEM_EXPIRED");
        if (native.Available > clock()) throw new Fault("ITEM_NOT_AVAILABLE");
        var item = Item(c); JObject envelope = Json.Object(native.Input); var contract = ValidateEnvelope(c.QueueKey, envelope, policy);
        if (item.context.TestCancelled) throw new Fault("TEST_CANCELLED");
        if (item.context.ActiveAttempt != "" || item.context.ReviewRequired || item.context.AttemptCount >= policy.MaxAttempts) throw new Fault("ITEM_INELIGIBLE");
        var now = clock(); int generation = item.context.Generation + 1;
        var attempt = new Attempt { Id = Guid.NewGuid().ToString(), ItemId = native.Id, Worker = actor.Id, Generation = generation, Started = now, LeaseExpires = now.AddSeconds(policy.LeaseSeconds), Deadline = now.AddSeconds(policy.DeadlineSeconds), Policy = policy, Contract = Snapshot(contract), ContractHash = contract.Hash, Caller = (JObject?)intent.Caller?.DeepClone() ?? new JObject() };
        Add("attempt", attempt.Id, c.QueueKey, attempt); item.context.ActiveAttempt = attempt.Id; item.context.Generation = generation; item.context.AttemptCount++;
        // Compare against the versions that were validated, not a fresh read that
        // could silently overwrite a concurrently replaced intent or item context.
        item.row.Body = Json.Write(item.context); item.row.Updated = now;
        store.Put(item.row, item.row.Version);
        var result = new { Outcome = "Acquired", ItemId = native.Id, AttemptId = attempt.Id, Generation = generation, attempt.LeaseExpires, Envelope = envelope, SourceKey = item.context.SourceKey, BusinessKey = native.UniqueKey, ContentHash = item.context.ContentHash, TestRun = item.context.TestRun };
        intent.Status = "Consumed"; intent.Result = Json.Write(result);
        row.Body = Json.Write(intent); row.Updated = now; store.Put(row, row.Version); return result;
    }
    static JObject Caller(JObject data) => new JObject { ["flowId"] = (string?)data["flowId"], ["runId"] = (string?)data["runId"], ["templateVersion"] = (string?)data["templateVersion"] };
    object ResolveAcquire(Command c, Actor actor, QueuePolicy policy)
    {
        var receiptRow = store.Get("command", Json.Hash(actor.Id + "|AcceptAcquire|" + c.RequestId));
        if (receiptRow != null && receiptRow.Queue == c.QueueKey) return Json.Read<object>(Json.Read<Receipt>(receiptRow.Body).Result);
        var row = store.Get("cursor", AcquisitionKey(c.QueueKey, actor.Id));
        if (row == null) return new { Outcome = "NoAcquisition" };
        var intent = Json.Read<AcquisitionIntent>(row.Body);
        if (intent.RequestId != c.RequestId) return new { Outcome = "NoAcquisition" };
        if (intent.Status == "Consumed" && intent.Result != "") return Json.Read<object>(intent.Result);
        return intent.Expires <= clock() ? new { Outcome = "Expired" } : new { Outcome = "Pending" };
    }
    (NativeItem native, Row row, ItemContext context) Item(Command c)
    {
        var native = store.NativeGet(c.ItemId) ?? throw new Fault("ITEM_NOT_FOUND");
        if (native.Queue != c.QueueKey) throw new Fault("FORBIDDEN");
        var row = store.Get("itemcontext", native.UniqueKey) ?? throw new Fault("ORPHAN_ITEM");
        return (native, row, Json.Read<ItemContext>(row.Body));
    }
    object Acquire(Command c, Actor actor, JObject data, QueuePolicy policy)
    {
        if (!policy.Enabled) return new { Outcome = "QueuePaused" };
        var now = clock(); var native = store.NativeDequeue(c.QueueKey, now);
        if (native == null) return new { Outcome = "NoWork" };
        c = new Command { ItemId = native.Id, QueueKey = c.QueueKey };
        (NativeItem native, Row row, ItemContext context) item;
        JObject envelope; Contract contract;
        try
        {
            item = Item(c); envelope = Json.Object(native.Input); contract = ValidateEnvelope(c.QueueKey, envelope, policy);
            if (item.context.TestCancelled) { native.Status = "Exception"; store.NativeSet(native); return new { Outcome = "TestCancelled", ItemId = native.Id }; }
            if (item.context.ActiveAttempt != "" || item.context.ReviewRequired || item.context.AttemptCount >= policy.MaxAttempts) throw new Fault("ITEM_INELIGIBLE");
        }
        catch (Fault error) when (new[] { "ORPHAN_ITEM", "INPUT_INVALID", "INPUT_TOO_LARGE", "CONTRACT_UNSUPPORTED", "ITEM_INELIGIBLE" }.Contains(error.Code))
        {
            native.Status = "Exception"; store.NativeSet(native);
            var context = Get<ItemContext>("itemcontext", native.UniqueKey);
            if (context == null) { context = new ItemContext { ItemId = native.Id, ContentHash = Json.Hash(native.Input), ReviewRequired = true }; Add("itemcontext", native.UniqueKey, c.QueueKey, context); }
            else { context.ReviewRequired = true; context.Generation++; Save("itemcontext", native.UniqueKey, context); }
            Events(c.QueueKey, native.Id, "validation", "ReviewRequired", policy);
            return new { Outcome = "ReviewRequired", ItemId = native.Id, Code = error.Code };
        }
        int generation = item.context.Generation + 1;
        var attempt = new Attempt { Id = Guid.NewGuid().ToString(), ItemId = native.Id, Worker = actor.Id, Generation = generation, Started = now, LeaseExpires = now.AddSeconds(policy.LeaseSeconds), Deadline = now.AddSeconds(policy.DeadlineSeconds), Policy = policy, Contract = Snapshot(contract), ContractHash = contract.Hash, Caller = new JObject { ["flowId"] = (string?)data["flowId"], ["runId"] = (string?)data["runId"], ["templateVersion"] = (string?)data["templateVersion"] } };
        Add("attempt", attempt.Id, c.QueueKey, attempt);
        item.context.ActiveAttempt = attempt.Id; item.context.Generation = generation; item.context.AttemptCount++;
        Save("itemcontext", native.UniqueKey, item.context);
        return new { Outcome = "Acquired", ItemId = native.Id, AttemptId = attempt.Id, Generation = generation, attempt.LeaseExpires, Envelope = envelope, SourceKey = item.context.SourceKey, BusinessKey = native.UniqueKey, ContentHash = item.context.ContentHash, TestRun = item.context.TestRun };
    }
    (NativeItem native, Row row, ItemContext context, Attempt attempt) Owned(Command c, Actor actor)
    {
        var item = Item(c);
        if (item.native.Status != "Processing" || item.context.ActiveAttempt != c.AttemptId || item.context.Generation != c.Generation) throw new Fault("STALE_ATTEMPT");
        var attempt = Get<Attempt>("attempt", c.AttemptId) ?? throw new Fault("STALE_ATTEMPT");
        if (attempt.Worker != actor.Id) throw new Fault("FORBIDDEN");
        if (attempt.Outcome != "Processing" || clock() >= attempt.LeaseExpires || clock() >= attempt.Deadline) throw new Fault("STALE_ATTEMPT");
        return (item.native, item.row, item.context, attempt);
    }
    object Checkpoint(Command c, Actor a, JObject d)
    {
        var item = Owned(c, a); string progress = Required(d, "progress", 500);
        if (progress == item.attempt.Checkpoint) throw new Fault("NO_PROGRESS");
        item.attempt.Checkpoint = progress;
        item.attempt.LeaseExpires = Min(clock().AddSeconds(item.attempt.Policy.LeaseSeconds), item.attempt.Deadline);
        Save("attempt", c.AttemptId, item.attempt);
        return new { Outcome = "Checkpointed", item.attempt.LeaseExpires };
    }
    static DateTime Min(DateTime a, DateTime b) => a < b ? a : b;
    object Complete(Command c, Actor actor, JObject d)
    {
        var item = Owned(c, actor); Required(d, "table", 100); if (!Guid.TryParse(Required(d, "recordId"), out _)) throw new Fault("OUTPUT_INVALID");
        if (d.ToString().Length > 8192) throw new Fault("OUTPUT_INVALID");
        item.context.OutputJson = Json.Write(d); item.context.ReviewRequired = false;
        Close(item.native, item.row, item.context, item.attempt, "Processed", "");
        Events(c.QueueKey, item.context.ItemId, item.attempt.Id, "Processed", item.attempt.Policy);
        return new { Outcome = "Processed", ItemId = item.native.Id };
    }
    void Close(NativeItem native, Row contextRow, ItemContext context, Attempt attempt, string status, string error, string? nativeStatus = null)
    {
        native.Status = nativeStatus ?? status; store.NativeSet(native);
        attempt.Outcome = status; attempt.ErrorCode = error; context.LastAttempt = attempt.Id; context.ActiveAttempt = "";
        Save("attempt", attempt.Id, attempt); contextRow.Body = Json.Write(context); contextRow.Updated = clock(); store.Put(contextRow, contextRow.Version);
    }
    object Fail(Command c, Actor actor, JObject d)
    {
        var item = Owned(c, actor); var now = clock(); string category = Required(d, "category", 40), code = Required(d, "code", 100);
        if (!new[] { "Technical", "Business", "Unknown" }.Contains(category)) throw new Fault("INPUT_INVALID");
        bool cancelled = item.context.TestCancelled || Json.Read<ItemContext>((store.Get("itemcontext", item.native.UniqueKey) ?? throw new Fault("ORPHAN_ITEM")).Body).TestCancelled;
        bool safe = !cancelled && category == "Technical" && (string?)d["effect"] == "None" && item.attempt.Policy.SafeEffects && item.context.AttemptCount < item.attempt.Policy.MaxAttempts && now < item.attempt.Deadline;
        if (safe)
        {
            var delay = Math.Min(item.attempt.Policy.RetryMaxSeconds, item.attempt.Policy.RetryBaseSeconds * Math.Pow(2, item.context.AttemptCount - 1));
            var jitter = Convert.ToInt32(Json.Hash(item.attempt.Id).Substring(0, 2), 16) % Math.Max(1, item.attempt.Policy.RetryBaseSeconds / 4);
            item.native.Available = now.AddSeconds(Math.Min(item.attempt.Policy.RetryMaxSeconds, delay + jitter));
            if (item.native.Available >= item.attempt.Deadline) safe = false;
        }
        item.context.ReviewRequired = !safe;
        Close(item.native, item.row, item.context, item.attempt, "Exception", code, safe ? "Queued" : null);
        safe = safe && item.native.Status == "Queued";
        Events(c.QueueKey, item.native.Id, item.attempt.Id, safe ? "RetryScheduled" : "ReviewRequired", item.attempt.Policy);
        return new { Outcome = safe ? "RetryScheduled" : "ReviewRequired", ItemId = item.native.Id };
    }
    object Retry(Command c, JObject d, QueuePolicy policy)
    {
        Required(d, "reason", 500);
        var item = Item(c);
        if (item.context.TestCancelled) throw new Fault("RETRY_UNSAFE");
        if (item.row.Version != c.ExpectedVersion) throw new Fault("VERSION_CONFLICT");
        if (item.native.Expires <= clock()) throw new Fault("ITEM_EXPIRED");
        if (item.native.Status != "Exception" || item.context.ActiveAttempt != "" || !policy.SafeEffects || item.context.AttemptCount >= policy.MaxAttempts || (string?)d["reconciliation"] != "VerifiedSafe") throw new Fault("RETRY_UNSAFE");
        item.context.ReviewRequired = false; item.context.Generation++;
        // The adapter resets an Error item to Queued without a delayed-requeue payload.
        item.native.Status = "Queued"; item.native.Available = clock(); store.NativeSet(item.native);
        item.row.Body = Json.Write(item.context); item.row.Updated = clock(); store.Put(item.row, item.row.Version);
        return new { Outcome = "RetryScheduled", ItemId = item.native.Id };
    }
    object Recover(Command c)
    {
        var item = Item(c);
        if (item.context.ActiveAttempt == "" || item.context.Generation != c.Generation || item.context.ActiveAttempt != c.AttemptId) throw new Fault("STALE_ATTEMPT");
        var attempt = Get<Attempt>("attempt", c.AttemptId) ?? throw new Fault("ORPHAN_ITEM");
        if (clock() < attempt.LeaseExpires && clock() < attempt.Deadline) throw new Fault("LEASE_ACTIVE");
        item.context.Generation++; item.context.ReviewRequired = true;
        Close(item.native, item.row, item.context, attempt, "Exception", "OUTCOME_UNKNOWN");
        Events(c.QueueKey, item.native.Id, attempt.Id, "ReviewRequired", attempt.Policy);
        return new { Outcome = "ReviewRequired" };
    }
    object Status(Command c)
    {
        var i = Item(c);
        var storedOutput = Json.Object(i.context.OutputJson, 8192);
        // Status is a reader-facing diagnostic view. Complete accepts a bounded
        // result object, but arbitrary caller fields must not become a payload
        // disclosure through a reader. Preserve only the stable business-record
        // reference fields and expose the last framework attempt separately.
        var output = new JObject();
        if (storedOutput["table"]?.Type == JTokenType.String) output["table"] = (string?)storedOutput["table"];
        if (storedOutput["recordId"]?.Type == JTokenType.String) output["recordId"] = (string?)storedOutput["recordId"];
        return new { Outcome = i.native.Status, ItemId = i.native.Id, i.context.ActiveAttempt, LastAttempt = i.context.LastAttempt, i.context.Generation, i.context.AttemptCount, i.context.ReviewRequired, Version = i.row.Version, Output = output };
    }
    object Health(Command c, QueuePolicy policy)
    {
        var page = store.NativePage(c.QueueKey, c.ItemId, 100);
        return new { Outcome = "Health", policy.Enabled, policy.Revision, CountInPage = page.Count, OldestInPage = page.Count == 0 ? (DateTime?)null : page.Min(x => x.Created), Items = page.Select(i => new { i.Id, i.Status, i.Available, i.Expires }), NextCursor = page.Count == 100 ? page.Last().Id : null };
    }
    static bool SafeDestinationKey(string value) => value.Length is >= 1 and <= 100 && value.All(ch => (ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') || ch is '-' or '_');
    static bool SafeOperationsBaseUrl(string value)
    {
        if (value == "") return true;
        if (!Uri.TryCreate(value, UriKind.Absolute, out var uri)) return false;
        return uri.Scheme == Uri.UriSchemeHttps && uri.UserInfo == "" && uri.Query == "" && uri.Fragment == "";
    }
    static string OperationsLink(string baseUrl, string queue, string item, string attempt, string kind)
    {
        if (baseUrl == "") return "";
        return baseUrl.TrimEnd('/') + "/notifications?queue=" + Uri.EscapeDataString(queue) + "&item=" + Uri.EscapeDataString(item) + "&attempt=" + Uri.EscapeDataString(attempt) + "&kind=" + Uri.EscapeDataString(kind);
    }
    static IEnumerable<NotificationRule> NotificationRulesFor(QueuePolicy policy, string kind)
    {
        if (policy.NotificationRules.Length == 0) return policy.Destinations.Distinct(StringComparer.Ordinal).Select(destination => new NotificationRule { Events = new[] { kind }, Destination = destination });
        return policy.NotificationRules.Where(rule => rule.Enabled && rule.Events.Contains(kind, StringComparer.Ordinal));
    }
    static string[] NotificationDestinations(QueuePolicy policy, string kind)
    {
        return NotificationRulesFor(policy, kind).Select(rule => rule.Destination).Distinct(StringComparer.Ordinal).ToArray();
    }
    bool InNotificationCooldown(string queue, string item, string attempt, string kind, NotificationRule rule)
    {
        if (rule.CooldownSeconds == 0) return false;
        var cutoff = clock().AddSeconds(-rule.CooldownSeconds); var after = "";
        for (var pageNumber = 0; pageNumber < 10; pageNumber++)
        {
            var page = store.Page("event", queue, after, 100);
            foreach (var row in page)
            {
                var prior = Json.Read<Delivery>(row.Body);
                if (prior.ItemId == item && prior.AttemptId != attempt && prior.Kind == kind && prior.Destination == rule.Destination && row.Updated >= cutoff) return true;
            }
            if (page.Count < 100) return false;
            after = page.Last().Key;
        }
        return true;
    }
    void Events(string queue, string item, string attempt, string kind, QueuePolicy policy)
    {
        foreach (var rule in NotificationRulesFor(policy, kind))
        {
            if (InNotificationCooldown(queue, item, attempt, kind, rule)) continue;
            var dest = rule.Destination;
            string key = Json.Hash(queue + "|" + item + "|" + attempt + "|" + kind + "|" + dest);
            if (store.Get("event", key) == null) Add("event", key, queue, new Delivery { Id = key, ItemId = item, AttemptId = attempt, Kind = kind, Destination = dest, OperationsLink = OperationsLink(policy.OperationsBaseUrl, queue, item, attempt, kind), NextAttempt = clock() });
        }
    }
    object IntakeFailure(Command c, JObject d, QueuePolicy p)
    {
        string source = Required(d, "source", 500), correlation = Required(d, "correlationId", 100), code = Required(d, "code", 100);
        var id = Json.Hash(c.QueueKey + "|" + source + "|" + correlation + "|" + code);
        if (store.Get("intakefailure", id) == null) Add("intakefailure", id, c.QueueKey, new { SourceHash = Json.Hash(source), CorrelationId = correlation, Code = code, Destinations = NotificationDestinations(p, "IntakeFailure") });
        Events(c.QueueKey, "", id, "IntakeFailure", p);
        return new { Outcome = "Recorded", FailureId = id };
    }
    object ClaimEvent(Command c, Actor a)
    {
        var page = store.Page("event", c.QueueKey, Cursor(c.QueueKey, "events"), 100);
        foreach (var row in page)
        {
            var e = Json.Read<Delivery>(row.Body);
            if (e.State == "Delivered" || e.State == "Failed" || e.NextAttempt > clock() || (e.State == "Sending" && e.LeaseExpires > clock())) continue;
            e.State = "Sending"; e.Owner = a.Id; e.LeaseToken = Guid.NewGuid().ToString(); e.LeaseExpires = clock().AddMinutes(2); e.Tries++;
            Save("event", row.Key, e);
            SetCursor(c.QueueKey, "events", row.Key);
            return new { Outcome = "Claimed", Event = e };
        }
        var next = page.Count == 100 ? page.Last().Key : ""; SetCursor(c.QueueKey, "events", next);
        return new { Outcome = "NoWork", NextCursor = next };
    }
    object FinishEvent(Command c, Actor a, JObject d)
    {
        string id = Required(d, "eventId"), lease = Required(d, "leaseToken");
        var row = store.Get("event", id) ?? throw new Fault("NOT_FOUND");
        if (row.Queue != c.QueueKey) throw new Fault("FORBIDDEN");
        var e = Json.Read<Delivery>(row.Body);
        if (e.Owner != a.Id || e.LeaseToken != lease || e.State != "Sending" || e.LeaseExpires <= clock()) throw new Fault("STALE_DELIVERY");
        bool delivered = (bool?)d["accepted"] == true;
        e.State = delivered ? "Delivered" : e.Tries >= 5 ? "Failed" : "Pending";
        e.ErrorCode = delivered ? "" : Required(d, "code", 100); e.NextAttempt = clock().AddSeconds(Math.Min(900, 30 * Math.Pow(2, e.Tries)));
        Save("event", id, e); return new { Outcome = e.State };
    }
    object Maintenance(Command c, JObject d)
    {
        int changed = 0; var page = store.NativePage(c.QueueKey, Cursor(c.QueueKey, "maintenance"), 50);
        foreach (var native in page.Where(x => x.Status == "Processing"))
        {
            var context = Get<ItemContext>("itemcontext", native.UniqueKey);
            if (context == null || context.ActiveAttempt == "") { native.Status = "Exception"; store.NativeSet(native); if (context == null) { context = new ItemContext { ItemId = native.Id, ContentHash = Json.Hash(native.Input), ReviewRequired = true }; Add("itemcontext", native.UniqueKey, c.QueueKey, context); } else { context.ReviewRequired = true; Save("itemcontext", native.UniqueKey, context); } changed++; continue; }
            var attempt = Get<Attempt>("attempt", context.ActiveAttempt);
            if (attempt == null) { native.Status = "Exception"; store.NativeSet(native); context.ActiveAttempt = ""; context.Generation++; context.ReviewRequired = true; Save("itemcontext", native.UniqueKey, context); changed++; continue; }
            if (attempt != null && (attempt.LeaseExpires <= clock() || attempt.Deadline <= clock())) { Recover(new Command { QueueKey = c.QueueKey, ItemId = native.Id, AttemptId = attempt.Id, Generation = context.Generation }); changed++; }
        }
        var next = page.Count == 50 ? page.Last().Id : ""; SetCursor(c.QueueKey, "maintenance", next);
        return new { Outcome = "Swept", Changed = changed, NextCursor = next };
    }
    string Cursor(string queue, string purpose) => (string?)Get<JObject>("cursor", Json.Hash(queue + "|" + purpose))?["value"] ?? "";
    bool HasActiveDelivery(string queue, string itemId, string attemptId, string kind, IEnumerable<string> destinations)
    {
        foreach (var destination in destinations.Distinct(StringComparer.Ordinal))
        {
            var key = Json.Hash(queue + "|" + itemId + "|" + attemptId + "|" + kind + "|" + destination);
            var row = store.Get("event", key);
            if (row == null) continue;
            var delivery = Json.Read<Delivery>(row.Body);
            if (delivery.State == "Pending" || delivery.State == "Sending") return true;
        }
        return false;
    }
    bool HasActiveDelivery(string queue, string itemId, string attemptId, string kind, QueuePolicy policy) => HasActiveDelivery(queue, itemId, attemptId, kind, NotificationDestinations(policy, kind));
    bool AttemptCanBePurged(string queue, Attempt attempt, QueuePolicy policy)
    {
        if (attempt.Outcome == "Processing") return false;
        var native = store.NativeGet(attempt.ItemId);
        if (native == null) return false;
        var context = Get<ItemContext>("itemcontext", native.UniqueKey);
        if (context == null || context.ActiveAttempt != "" || context.ReviewRequired || context.LastAttempt == attempt.Id) return false;
        if (native.Status != "Processed" && native.Status != "Exception") return false;
        var effectivePolicy = attempt.Policy?.NotificationRules?.Length > 0 || attempt.Policy?.Destinations?.Length > 0 ? attempt.Policy : policy;
        return !new[] { "Processed", "RetryScheduled", "ReviewRequired" }.Any(kind => HasActiveDelivery(queue, native.Id, attempt.Id, kind, effectivePolicy));
    }
    bool TestRunCanBePurged(string queue, TestRun run, QueuePolicy policy)
    {
        if (run.State == "Running" || run.Results.Any(result => result.State == "Pending")) return false;
        foreach (var result in run.Results)
        {
            if (store.Get("testresult", result.Id) == null) return false;
            var native = store.NativeGet(result.ItemId);
            if (native == null || native.Status == "Queued" || native.Status == "Processing") return false;
            var context = Get<ItemContext>("itemcontext", native.UniqueKey);
            if (context == null || context.ActiveAttempt != "" || context.ReviewRequired) return false;
            if (context.LastAttempt != "")
            {
                var attempt = Get<Attempt>("attempt", context.LastAttempt);
                if (attempt == null) return false;
                var effectivePolicy = attempt.Policy?.NotificationRules?.Length > 0 || attempt.Policy?.Destinations?.Length > 0 ? attempt.Policy : policy;
                if (new[] { "Processed", "RetryScheduled", "ReviewRequired" }.Any(kind => HasActiveDelivery(queue, native.Id, attempt.Id, kind, effectivePolicy))) return false;
            }
        }
        foreach (var caseId in run.Results.Select(result => result.CaseId).Distinct(StringComparer.Ordinal))
            if (store.Get("testcase", Json.Hash(run.Id + "|" + caseId)) == null) return false;
        return true;
    }
    object Retention(Command c, QueuePolicy policy)
    {
        int inputs = 0, receipts = 0, attempts = 0, evidence = 0, errors = 0, protectedRows = 0;
        var retention = policy.Retention;
        var payloadCutoff = clock().AddDays(-retention.PayloadDays);
        var receiptCutoff = clock().AddDays(-retention.ReceiptDays);
        var attemptCutoff = clock().AddDays(-retention.AttemptDays);
        var evidenceCutoff = clock().AddDays(-retention.EvidenceDays);
        var errorCutoff = clock().AddDays(-retention.ErrorDays);
        var items = store.NativePage(c.QueueKey, Cursor(c.QueueKey, "input-retention"), 50);
        foreach (var item in items)
        {
            var context = Get<ItemContext>("itemcontext", item.UniqueKey);
            bool terminalForRetention = item.Status == "Processed" || (item.Status == "OnHold" && context?.TestCancelled == true);
            if (terminalForRetention && item.Created < payloadCutoff && context != null && !context.ReviewRequired && context.ActiveAttempt == "" && item.Input != "{}") { store.NativeRedactInput(item.Id); inputs++; }
            else if (item.Created < payloadCutoff && item.Input != "{}") protectedRows++;
        }
        SetCursor(c.QueueKey, "input-retention", items.Count == 50 ? items.Last().Id : "");
        var commands = store.Page("command", c.QueueKey, Cursor(c.QueueKey, "receipt-retention"), 100);
        foreach (var row in commands.Where(r => r.Updated < receiptCutoff))
        {
            var receipt = Json.Read<Receipt>(row.Body); var result = Json.Object(receipt.Result, 1048576);
            if ((string?)result["Outcome"] == "ReplayExpired") continue;
            var id = (string?)result["ItemId"];
            if (id != null) { var native = store.NativeGet(id); var context = native == null ? null : Get<ItemContext>("itemcontext", native.UniqueKey); if (native == null || native.Status != "Processed" || context == null || context.ReviewRequired || context.ActiveAttempt != "") continue; }
            receipt.Result = Json.Write(new { Outcome = "ReplayExpired" }); receipt.Reason = ""; Save("command", row.Key, receipt); receipts++;
        }
        SetCursor(c.QueueKey, "receipt-retention", commands.Count == 100 ? commands.Last().Key : "");
        var attemptRows = store.Page("attempt", c.QueueKey, Cursor(c.QueueKey, "attempt-retention"), 50);
        foreach (var row in attemptRows)
        {
            var attempt = Json.Read<Attempt>(row.Body);
            if (row.Updated < attemptCutoff && AttemptCanBePurged(c.QueueKey, attempt, policy)) { store.Delete("attempt", row.Key, row.Version); attempts++; }
            else if (row.Updated < attemptCutoff) protectedRows++;
        }
        SetCursor(c.QueueKey, "attempt-retention", attemptRows.Count == 50 ? attemptRows.Last().Key : "");
        var errorRows = store.Page("intakefailure", c.QueueKey, Cursor(c.QueueKey, "error-retention"), 50);
        foreach (var row in errorRows)
        {
            var failure = Json.Object(row.Body);
            var destinations = failure["Destinations"]?.Values<string>().Where(destination => destination != null).Select(destination => destination!).ToArray();
            if (destinations == null) { if (row.Updated < errorCutoff) protectedRows++; continue; }
            if (row.Updated < errorCutoff && !HasActiveDelivery(c.QueueKey, "", row.Key, "IntakeFailure", destinations)) { store.Delete("intakefailure", row.Key, row.Version); errors++; }
            else if (row.Updated < errorCutoff) protectedRows++;
        }
        SetCursor(c.QueueKey, "error-retention", errorRows.Count == 50 ? errorRows.Last().Key : "");
        var testRuns = store.Page("testrun", c.QueueKey, Cursor(c.QueueKey, "evidence-retention"), 50);
        foreach (var row in testRuns)
        {
            var run = Json.Read<TestRun>(row.Body);
            if (row.Updated >= evidenceCutoff) continue;
            if (!TestRunCanBePurged(c.QueueKey, run, policy)) { protectedRows++; continue; }
            foreach (var result in run.Results)
            {
                var resultRow = store.Get("testresult", result.Id);
                if (resultRow != null) { store.Delete("testresult", resultRow.Key, resultRow.Version); evidence++; }
            }
            foreach (var caseId in run.Results.Select(result => result.CaseId).Distinct(StringComparer.Ordinal))
            {
                var caseRow = store.Get("testcase", Json.Hash(run.Id + "|" + caseId));
                if (caseRow != null) { store.Delete("testcase", caseRow.Key, caseRow.Version); evidence++; }
            }
            store.Delete("testrun", row.Key, row.Version); evidence++;
        }
        SetCursor(c.QueueKey, "evidence-retention", testRuns.Count == 50 ? testRuns.Last().Key : "");
        return new { Outcome = "RetentionApplied", InputsRedacted = inputs, ReceiptsRedacted = receipts, AttemptsPurged = attempts, ErrorsPurged = errors, EvidenceRowsPurged = evidence, ProtectedRows = protectedRows, ReplayWindowDays = retention.ReceiptDays,
            Retention = new { PayloadDays = retention.PayloadDays, ReceiptDays = retention.ReceiptDays, AttemptDays = retention.AttemptDays, EvidenceDays = retention.EvidenceDays, ErrorDays = retention.ErrorDays },
            ProtectedArtifacts = new[] { "active-attempts", "queued-or-processing-items", "review-held-item-evidence", "current-attempt-snapshot", "active-notification-deliveries" } };
    }
    void SetCursor(string queue, string purpose, string value)
    {
        var key = Json.Hash(queue + "|" + purpose); var body = new { value };
        if (store.Get("cursor", key) == null) Add("cursor", key, queue, body); else Save("cursor", key, body);
    }
}
