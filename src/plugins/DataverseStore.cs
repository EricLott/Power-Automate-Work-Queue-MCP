using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Messages;
using Microsoft.Xrm.Sdk.Query;
namespace QueueFramework.Plugins;
public sealed class DataverseStore : IStore
{
    public string ProofFault { get; set; } = "";
    readonly IOrganizationService service; readonly IPluginExecutionContext context;
    public DataverseStore(IOrganizationService service, IPluginExecutionContext context) { this.service = service; this.context = context; }
    public static readonly IReadOnlyDictionary<string, string> Tables = new Dictionary<string, string>
    {
        ["definition"] = "qmcp_wqdefinition",
        ["queuebinding"] = "qmcp_wqqueuebinding",
        ["contract"] = "qmcp_wqcontract",
        ["itemcontext"] = "qmcp_wqitemcontext",
        ["attempt"] = "qmcp_wqattempt",
        ["command"] = "qmcp_wqcommand",
        ["event"] = "qmcp_wqevent",
        ["cursor"] = "qmcp_wqcursor",
        ["intakefailure"] = "qmcp_wqintakefailure",
        ["testcase"] = "qmcp_wqtestcase",
        ["testrun"] = "qmcp_wqtestrun",
        ["testresult"] = "qmcp_wqtestresult",
        ["business"] = "qmcp_emailrequest",
        ["principal"] = "qmcp_wqprincipal"
    };
    // Keep reads narrow: qmcp_document can contain large snapshots and is the
    // only payload column the adapter needs. versionnumber is mapped to the
    // SDK Entity.RowVersion used by optimistic concurrency.
    static readonly string[] RowColumns = { "qmcp_key", "qmcp_queuekey", "qmcp_document", "modifiedon", "overriddencreatedon", "versionnumber" };
    static readonly string[] NativeColumns = { "workqueueid", "uniqueidbyqueue", "input", "statecode", "delayuntil", "expirydate", "createdon", "versionnumber" };
    public T Atomic<T>(Func<T> operation)
    {
        // Fail closed until the Custom API transaction composition is observed during live import testing.
        if (!context.IsInTransaction) throw new Fault("TRANSACTION_REQUIRED");
        return operation();
    }
    Entity? Find(string kind, string key)
    {
        var query = new QueryExpression(Tables[kind]) { ColumnSet = new ColumnSet(RowColumns), TopCount = 2 };
        if (kind == "business")
        {
            if (!Guid.TryParse(key, out var id)) throw new Fault("INPUT_INVALID");
            query.Criteria.AddCondition("qmcp_emailrequestid", ConditionOperator.Equal, id);
        }
        else query.Criteria.AddCondition("qmcp_key", ConditionOperator.Equal, key);
        var records = service.RetrieveMultiple(query).Entities;
        if (records.Count > 1) throw new Fault("DUPLICATE_KEY");
        return records.FirstOrDefault();
    }
    static Row Row(string kind, Entity e)
    {
        var body = e.GetAttributeValue<string>("qmcp_document") ?? "{}";
        var fixtureCreated = Json.Object(body)["_qmcpFixtureCreated"];
        var updated = DateTime.TryParse((string?)fixtureCreated, out var fixtureDate) ? fixtureDate : e.GetAttributeValue<DateTime>("modifiedon");
        return new Row { Kind = kind, Key = kind == "business" ? e.Id.ToString() : e.GetAttributeValue<string>("qmcp_key"), Queue = e.GetAttributeValue<string>("qmcp_queuekey"), Body = body, Version = long.Parse(e.RowVersion ?? throw new Fault("ROW_VERSION_REQUIRED")), Updated = updated };
    }
    public Row? Get(string kind, string key) { var e = Find(kind, key); return e == null ? null : Row(kind, e); }
    public IReadOnlyList<Row> Page(string kind, string queue, string after, int limit)
    {
        var query = new QueryExpression(Tables[kind]) { ColumnSet = new ColumnSet(RowColumns), TopCount = Math.Min(100, limit) };
        query.Criteria.AddCondition("qmcp_queuekey", ConditionOperator.Equal, queue);
        if (kind == "business")
        {
            Guid cursor = default;
            if (after != "" && !Guid.TryParse(after, out cursor)) throw new Fault("INPUT_INVALID");
            if (after != "") query.Criteria.AddCondition("qmcp_emailrequestid", ConditionOperator.GreaterThan, cursor);
            query.AddOrder("qmcp_emailrequestid", OrderType.Ascending);
        }
        else
        {
            if (after != "") query.Criteria.AddCondition("qmcp_key", ConditionOperator.GreaterThan, after);
            query.AddOrder("qmcp_key", OrderType.Ascending);
        }
        return service.RetrieveMultiple(query).Entities.Select(e => Row(kind, e)).ToList();
    }
    public IReadOnlyList<Row> PageBusinessEvidence(string queue, string testRun, string sourceKey, string after, int limit)
    {
        var query = new QueryExpression(Tables["business"]) { ColumnSet = new ColumnSet(RowColumns), TopCount = Math.Min(100, limit) };
        query.Criteria.AddCondition("qmcp_queuekey", ConditionOperator.Equal, queue);
        query.Criteria.AddCondition("qmcp_testrun", ConditionOperator.Equal, testRun);
        if (sourceKey != "") query.Criteria.AddCondition("qmcp_sourcekey", ConditionOperator.Equal, sourceKey);
        Guid cursor = default;
        if (after != "" && !Guid.TryParse(after, out cursor)) throw new Fault("INPUT_INVALID");
        if (after != "") query.Criteria.AddCondition("qmcp_emailrequestid", ConditionOperator.GreaterThan, cursor);
        query.AddOrder("qmcp_emailrequestid", OrderType.Ascending);
        return service.RetrieveMultiple(query).Entities.Select(e => Row("business", e)).ToList();
    }
    public Row Add(Row row)
    {
        if (row.Kind == "command" && ProofFault == "before-receipt") throw new Fault("INJECTED_PROOF_FAILURE");
        var e = new Entity(Tables[row.Kind]); e["qmcp_key"] = row.Key; e["qmcp_name"] = row.Key; e["qmcp_queuekey"] = row.Queue; e["qmcp_document"] = row.Body;
        if (row.Kind != "principal")
        {
            var policy = row.Kind == "definition" ? Json.Read<QueuePolicy>(row.Body) : Policy(row.Queue);
            if (!Guid.TryParse(policy.OwnerTeamId, out var team)) throw new Fault("OWNER_TEAM_REQUIRED");
            e["ownerid"] = new EntityReference("team", team);
        }
        Project(e, row.Body);
        if (context.MessageName == "qmcp_WQ_SeedRetentionFixture" && row.Updated != default)
            e["overriddencreatedon"] = row.Updated.ToUniversalTime();
        if (row.Kind == "business") e.Id = Guid.Parse(row.Key);
        service.Create(e);
        InjectAfterWrite(row.Kind);
        return Get(row.Kind, row.Key) ?? throw new Fault("WRITE_NOT_VISIBLE");
    }
    public Row Put(Row row, long expectedVersion)
    {
        var old = Find(row.Kind, row.Key) ?? throw new Fault("NOT_FOUND");
        var update = new Entity(old.LogicalName, old.Id) { RowVersion = expectedVersion.ToString() }; update["qmcp_document"] = row.Body;
        Project(update, row.Body);
        service.Execute(new UpdateRequest { Target = update, ConcurrencyBehavior = ConcurrencyBehavior.IfRowVersionMatches });
        InjectAfterWrite(row.Kind);
        return Get(row.Kind, row.Key)!;
    }

    void InjectAfterWrite(string kind)
    {
        if (context.MessageName != "qmcp_WQ_AcceptAcquire") return;
        if ((kind == "attempt" && ProofFault == "after-attempt") ||
            (kind == "itemcontext" && ProofFault == "after-context") ||
            (kind == "cursor" && ProofFault == "after-intent") ||
            (kind == "command" && ProofFault == "after-receipt"))
            throw new Fault("INJECTED_PROOF_FAILURE");
    }
    public void Delete(string kind, string key, long expectedVersion)
    {
        var old = Find(kind, key) ?? throw new Fault("NOT_FOUND");
        service.Execute(new DeleteRequest { Target = new EntityReference(old.LogicalName, old.Id) { RowVersion = expectedVersion.ToString() }, ConcurrencyBehavior = ConcurrencyBehavior.IfRowVersionMatches });
    }
    QueuePolicy Policy(string queue) => Json.Read<QueuePolicy>(Get("definition", queue)?.Body ?? throw new Fault("QUEUE_NOT_FOUND"));
    static void Project(Entity entity, string body)
    {
        var data = Json.Object(body, 1048576);
        entity["qmcp_outcome"] = (string?)data["Outcome"] ?? (string?)data["State"] ?? "";
        entity["qmcp_itemid"] = (string?)data["ItemId"] ?? "";
        entity["qmcp_attemptid"] = (string?)data["ActiveAttempt"] ?? "";
        entity["qmcp_sourcekey"] = (string?)data["SourceKey"] ?? (string?)data["sourceKey"] ?? "";
        entity["qmcp_testrun"] = (string?)data["TestRun"] ?? (string?)data["testRun"] ?? "";
        entity["qmcp_reviewrequired"] = (bool?)data["ReviewRequired"] == true ? "true" : "false";
    }
    string QueueKey(Guid nativeQueue)
    {
        return Get("queuebinding",nativeQueue.ToString())?.Queue??throw new Fault("QUEUE_NOT_REGISTERED");
    }
    NativeItem Native(Entity e) => new NativeItem
    {
        Id = e.Id.ToString(),
        Queue = QueueKey(e.GetAttributeValue<EntityReference>("workqueueid").Id),
        UniqueKey = e.GetAttributeValue<string>("uniqueidbyqueue"),
        Input = e.GetAttributeValue<string>("input"),
        Status = FromState(e.GetAttributeValue<OptionSetValue>("statecode").Value),
        Created = e.GetAttributeValue<DateTime>("createdon"),
        Available = e.GetAttributeValue<DateTime?>("delayuntil") ?? DateTime.MinValue,
        Expires = e.GetAttributeValue<DateTime?>("expirydate") ?? DateTime.MaxValue
    };
    static string FromState(int code) => code == 0 ? "Queued" : code == 1 ? "Processing" : code == 2 ? "Processed" : code == 3 ? "OnHold" : code == 4 ? "Exception" : throw new Fault("NATIVE_STATE_UNSUPPORTED");
    public NativeItem? NativeGet(string id)
    {
        if (!Guid.TryParse(id, out var guid)) throw new Fault("INPUT_INVALID");
        var q = new QueryExpression("workqueueitem") { ColumnSet = new ColumnSet(NativeColumns), TopCount = 1 }; q.Criteria.AddCondition("workqueueitemid", ConditionOperator.Equal, guid);
        var e = service.RetrieveMultiple(q).Entities.FirstOrDefault(); return e == null ? null : Native(e);
    }
    public NativeItem NativeCreate(NativeItem item)
    {
        var e = new Entity("workqueueitem", Guid.Parse(item.Id)); e["workqueueid"] = new EntityReference("workqueue", Guid.Parse(Policy(item.Queue).NativeQueueId));
        e["name"] = item.UniqueKey; e["uniqueidbyqueue"] = item.UniqueKey; e["input"] = item.Input; e["delayuntil"] = item.Available; e["expirydate"] = item.Expires;
        if (context.MessageName == "qmcp_WQ_SeedRetentionFixture" && item.Created != default)
            e["overriddencreatedon"] = item.Created.ToUniversalTime();
        service.Create(e); return NativeGet(item.Id) ?? throw new Fault("WRITE_NOT_VISIBLE");
    }
    public NativeItem? NativeDequeue(string queue, DateTime now)
    {
        // Use the documented bound-action name. The short SDK label does not
        // resolve reliably in the live Dataverse service.
        var request = new OrganizationRequest("Microsoft.Dynamics.CRM.Dequeue"); request["Target"] = new EntityReference("workqueue", Guid.Parse(Policy(queue).NativeQueueId));
        var response = service.Execute(request);
        if (ProofFault == "after-dequeue") throw new Fault("INJECTED_PROOF_FAILURE");
        var entity = response.Results.Values.OfType<Entity>().SingleOrDefault();
        if (entity == null) { if (response.Results.Count == 0) return null; throw new Fault("DEQUEUE_RESPONSE_UNVALIDATED"); }
        var item = NativeGet(entity.Id.ToString()) ?? throw new Fault("DEQUEUE_RESPONSE_UNVALIDATED");
        if (item.Queue != queue || item.Status != "Processing" || item.Available > now || item.Expires <= now) throw new Fault("DEQUEUE_ELIGIBILITY_FAILED");
        return item;
    }
    public void NativeSet(NativeItem item)
    {
        int state = item.Status == "Queued" ? 0 : item.Status == "Processing" ? 1 : item.Status == "Processed" ? 2 : item.Status == "OnHold" ? 3 : item.Status == "Exception" ? 4 : throw new Fault("NATIVE_STATE_UNSUPPORTED");
        var e = new Entity("workqueueitem", Guid.Parse(item.Id)); e["statecode"] = new OptionSetValue(state); e["statuscode"] = new OptionSetValue(state);
        // Supplying delayuntil invokes native requeue validation even for a
        // terminal transition. Do not resend an item's historical availability.
        // A due operator retry is a status reset from Error, without a requeue
        // payload. A delayed automatic retry arrives directly from Processing.
        if (state == 0 && item.Available > DateTime.UtcNow) e["delayuntil"] = item.Available;
        if (state == 2) e["completedon"] = DateTime.UtcNow; service.Update(e);
    }
    public void NativeRedactInput(string id) { var entity = new Entity("workqueueitem", Guid.Parse(id)); entity["input"] = "{}"; service.Update(entity); }
    public IReadOnlyList<NativeItem> NativePage(string queue, string after, int limit)
    {
        var q = new QueryExpression("workqueueitem") { ColumnSet = new ColumnSet(NativeColumns), TopCount = Math.Min(100, limit) };
        q.Criteria.AddCondition("workqueueid", ConditionOperator.Equal, Guid.Parse(Policy(queue).NativeQueueId));
        if (after != "") q.Criteria.AddCondition("workqueueitemid", ConditionOperator.GreaterThan, Guid.Parse(after));
        q.AddOrder("workqueueitemid", OrderType.Ascending); return service.RetrieveMultiple(q).Entities.Select(Native).ToList();
    }
}
