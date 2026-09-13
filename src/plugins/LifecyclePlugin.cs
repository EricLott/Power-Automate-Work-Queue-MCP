using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Query;
using Newtonsoft.Json.Linq;
namespace QueueFramework.Plugins;
public sealed class LifecyclePlugin : IPlugin
{
    public void Execute(IServiceProvider provider)
    {
        var context = (IPluginExecutionContext)provider.GetService(typeof(IPluginExecutionContext));
        var factory = (IOrganizationServiceFactory)provider.GetService(typeof(IOrganizationServiceFactory));
        var service = factory.CreateOrganizationService(context.InitiatingUserId);
        var trace = (ITracingService)provider.GetService(typeof(ITracingService));
        try
        {
            if (!context.MessageName.StartsWith("qmcp_WQ_", StringComparison.Ordinal)) throw new Fault("OPERATION_UNSUPPORTED");
            var requestedOperation = context.MessageName.Substring("qmcp_WQ_".Length);
            if (requestedOperation == "AcquireNext") throw new Fault("ACQUISITION_HANDOFF_REQUIRED");
            if (requestedOperation == "AcceptAcquire" && !HasAcquisitionPostAncestor(context, service)) throw new Fault("ACQUISITION_HANDOFF_REQUIRED");
            var store = new DataverseStore(service, context);
            var principal = store.Get("principal", context.InitiatingUserId.ToString()) ?? throw new Fault("PRINCIPAL_NOT_REGISTERED");
            var profile = Json.Object(principal.Body);
            var actor = new Actor { Id = context.InitiatingUserId.ToString(), Production = (bool?)profile["production"] ?? true, Roles = new HashSet<string>((profile["roles"] as JArray ?? new JArray()).Values<string>().Where(x => x != null).Select(x => x!)) };
            var proofFault = (string?)profile["proofFault"] ?? "";
            if (proofFault != "")
            {
                if (actor.Production || !actor.Has("deployment") || !new[] { "before-receipt", "after-dequeue", "after-attempt", "after-context", "after-intent", "after-receipt", "after-native-claim" }.Contains(proofFault)) throw new Fault("PROOF_FAULT_DENIED");
                store.ProofFault = proofFault;
            }
            trace.Trace("qmcp operation {0}; correlation {1}; transaction {2}; depth {3}", context.MessageName, context.CorrelationId, context.IsInTransaction, context.Depth);
            string Text(string name) => context.InputParameters.Contains(name) ? Convert.ToString(context.InputParameters[name]) ?? "" : "";
            var c = new Command
            {
                Operation = context.MessageName.Substring("qmcp_WQ_".Length),
                QueueKey = Text("QueueKey"),
                RequestId = Text("RequestId"),
                ItemId = Text("ItemId"),
                AttemptId = Text("AttemptId"),
                Generation = int.TryParse(Text("Generation"), out var gen) ? gen : 0,
                ExpectedVersion = long.TryParse(Text("ExpectedVersion"), out var version) ? version : 0,
                DataJson = Text("DataJson") == "" ? "{}" : Text("DataJson")
            };
            context.SharedVariables["qmcp.runtime"] = true;
            if (requestedOperation == "AcceptAcquire" && proofFault == "after-native-claim") throw new Fault("INJECTED_PROOF_FAILURE");
            context.OutputParameters["ResultJson"] = new Engine(store).Execute(c, actor);
        }
        catch (Fault e) { trace.Trace("qmcp failure {0}; correlation {1}", e.Code, context.CorrelationId); throw new InvalidPluginExecutionException(e.Code); }
        catch (Exception error)
        {
            // Keep the public fault deliberately generic. These diagnostics help identify
            // an SDK/registration failure without copying exception messages or payloads.
            trace.Trace($"qmcp unexpected failure; correlation {context.CorrelationId}; exceptionType {error.GetType().FullName ?? error.GetType().Name}; stackTrace {error.StackTrace ?? ""}; innerTypes {InnerTypes(error)}; organizationServiceErrorCode {OrganizationServiceErrorCode(error)?.ToString() ?? ""}");
            throw new InvalidPluginExecutionException("RUNTIME_FAILURE");
        }
    }

    static string InnerTypes(Exception error)
    {
        var types = new List<string>();
        for (var current = error.InnerException; current != null; current = current.InnerException)
            types.Add(current.GetType().FullName ?? current.GetType().Name);
        return string.Join(" -> ", types);
    }

    static int? OrganizationServiceErrorCode(Exception error)
    {
        // SDK faults are commonly wrapped in FaultException<T>; use properties by name so
        // this adapter remains compatible with the sandbox SDK reference assemblies.
        for (var current = error; current != null; current = current.InnerException)
        {
            try
            {
                var direct = current.GetType().GetProperty("ErrorCode")?.GetValue(current, null);
                if (direct is int directCode) return directCode;
                var detail = current.GetType().GetProperty("Detail")?.GetValue(current, null);
                var nested = detail?.GetType().GetProperty("ErrorCode")?.GetValue(detail, null);
                if (nested is int nestedCode) return nestedCode;
            }
            catch (Exception) { }
        }
        return null;
    }

    internal static bool HasAcquisitionPostAncestor(IPluginExecutionContext current, IOrganizationService metadata)
    {
        if (!current.IsInTransaction || current.Mode != 0) return false;
        for (var parent = current.ParentContext; parent != null; parent = parent.ParentContext)
        {
            if (!parent.IsInTransaction || parent.Stage != 40 || parent.Mode != 0 || parent.MessageName != "Update" ||
                parent.PrimaryEntityName != "workqueueitem" || parent.InitiatingUserId != current.InitiatingUserId) continue;
            var extension = parent.OwningExtension;
            if (extension == null || extension.LogicalName != "sdkmessageprocessingstep" || extension.Id == Guid.Empty) continue;
            try
            {
                var step = metadata.Retrieve("sdkmessageprocessingstep", extension.Id, new ColumnSet("stage", "mode", "eventhandler"));
                if (step.GetAttributeValue<OptionSetValue>("stage")?.Value != 40 || step.GetAttributeValue<OptionSetValue>("mode")?.Value != 0) continue;
                var handler = step.GetAttributeValue<EntityReference>("eventhandler");
                if (handler == null || handler.LogicalName != "plugintype" || handler.Id == Guid.Empty) continue;
                var type = metadata.Retrieve("plugintype", handler.Id, new ColumnSet("typename", "assemblyname"));
                if (type.GetAttributeValue<string>("typename") == typeof(AcquisitionPostPlugin).FullName &&
                    type.GetAttributeValue<string>("assemblyname") == typeof(AcquisitionPostPlugin).Assembly.GetName().Name) return true;
            }
            catch (Exception) { }
        }
        return false;
    }
}

/// <summary>Completes the native queue acquisition handoff after Dataverse has applied its claim update.</summary>
public sealed class AcquisitionPostPlugin : IPlugin
{
    static readonly HashSet<string> Allowed = new HashSet<string>(StringComparer.Ordinal)
    {
        "machineuser", "processorid", "processortype", "statecode", "statuscode", "workqueueitemid",
        "modifiedby", "modifiedon", "modifiedonbehalfby",
        // Observed additions from the native core operation. The pre-operation
        // guard deliberately does not allow callers to supply these fields.
        "processingstarttime", "processinguser"
    };

    public void Execute(IServiceProvider provider)
    {
        var context = (IPluginExecutionContext)provider.GetService(typeof(IPluginExecutionContext));
        var factory = (IOrganizationServiceFactory)provider.GetService(typeof(IOrganizationServiceFactory));
        var service = factory.CreateOrganizationService(null);
        var caller = factory.CreateOrganizationService(context.InitiatingUserId);
        var trace = (ITracingService)provider.GetService(typeof(ITracingService));
        try
        {
            if (!context.IsInTransaction || context.Stage != 40 || context.Mode != 0 || context.MessageName != "Update" || context.PrimaryEntityName != "workqueueitem")
                throw new Fault("ACQUISITION_HANDOFF_REQUIRED");
            var target = context.InputParameters.Contains("Target") ? context.InputParameters["Target"] as Entity : null;
            var pre = context.PreEntityImages.Contains("Before") ? context.PreEntityImages["Before"] : null;
            if (target == null || pre == null || target.Id != context.PrimaryEntityId) throw new Fault("ACQUISITION_HANDOFF_REQUIRED");
            var native = service.Retrieve("workqueueitem", context.PrimaryEntityId, new ColumnSet("processinguser", "statecode", "statuscode", "workqueueid"));
            var queue = native.GetAttributeValue<EntityReference>("workqueueid");
            if (queue == null) throw new Fault("QUEUE_NOT_REGISTERED");
            var bindingQuery = new QueryExpression("qmcp_wqqueuebinding") { ColumnSet = new ColumnSet("qmcp_queuekey"), TopCount = 2 }; bindingQuery.Criteria.AddCondition("qmcp_key", ConditionOperator.Equal, queue.Id.ToString());
            var bindingRows = service.RetrieveMultiple(bindingQuery).Entities;
            if (bindingRows.Count == 0) return;
            if (bindingRows.Count != 1) throw new Fault("QUEUE_NOT_REGISTERED");
            if (!ClaimTransition(pre, target, native, context.InitiatingUserId)) return;
            if (context.InitiatingUserId == Guid.Empty || context.UserId != context.InitiatingUserId || context.PrimaryEntityId == Guid.Empty)
                throw new Fault("ACQUISITION_HANDOFF_REQUIRED");
            if (target.Attributes.Keys.Any(k => !Allowed.Contains(k)))
            {
                var targetTrace = (ITracingService)provider.GetService(typeof(ITracingService));
                targetTrace?.Trace("qmcp acquisition post target attributes: {0}", string.Join(",", target.Attributes.Keys.OrderBy(k => k, StringComparer.Ordinal)));
                throw new Fault("ACQUISITION_FIELDS_UNSUPPORTED");
            }
            var processingUser = native.GetAttributeValue<EntityReference>("processinguser");
            if (processingUser == null || processingUser.Id != context.InitiatingUserId) throw new Fault("ACQUISITION_HANDOFF_REQUIRED");
            var binding = bindingRows[0];
            var queueKey = binding.GetAttributeValue<string>("qmcp_queuekey");
            if (string.IsNullOrWhiteSpace(queueKey)) throw new Fault("QUEUE_NOT_REGISTERED");
            var key = Json.Hash("acquire|" + context.InitiatingUserId.ToString() + "|" + queueKey);
            var intentRow = Find(service, "qmcp_wqcursor", "qmcp_key", key, "qmcp_document");
            var intent = intentRow.GetAttributeValue<string>("qmcp_document");
            var acquisition = Json.Read<AcquisitionIntent>(intent ?? "");
            if (acquisition.Status != "Prepared" || acquisition.ActorId != context.InitiatingUserId.ToString() || acquisition.Expires <= DateTime.UtcNow)
                throw new Fault("ACQUISITION_INTENT_INVALID");
            var requestId = Guid.TryParse(acquisition.RequestId, out _) ? acquisition.RequestId : "";
            trace?.Trace("qmcp acquisition claim validated; correlation {0}; depth {1}; transaction {2}; requestId {3}", context.CorrelationId, context.Depth, context.IsInTransaction, requestId);
            var request = new OrganizationRequest("qmcp_WQ_AcceptAcquire");
            request["RequestId"] = acquisition.RequestId;
            request["QueueKey"] = queueKey;
            request["ItemId"] = context.PrimaryEntityId.ToString();
            request["DataJson"] = "{}";
            caller.Execute(request);
        }
        catch (Fault e) { throw new InvalidPluginExecutionException(e.Code); }
        catch (InvalidPluginExecutionException) { throw; }
        catch (Exception) { throw new InvalidPluginExecutionException("ACQUISITION_HANDOFF_FAILED"); }
    }

    static bool ClaimTransition(Entity pre, Entity target, Entity observed, Guid user)
    {
        var before = pre.GetAttributeValue<OptionSetValue>("statecode")?.Value;
        var status = pre.GetAttributeValue<OptionSetValue>("statuscode")?.Value;
        var after = target.GetAttributeValue<OptionSetValue>("statecode")?.Value ?? observed.GetAttributeValue<OptionSetValue>("statecode")?.Value;
        var afterStatus = target.GetAttributeValue<OptionSetValue>("statuscode")?.Value ?? observed.GetAttributeValue<OptionSetValue>("statuscode")?.Value;
        if (before != 0 || after != 1 || afterStatus != 1) return false;
        return true;
    }

    static Entity Find(IOrganizationService service, string table, string field, string value, params string[] columns)
    {
        var q = new QueryExpression(table) { ColumnSet = new ColumnSet(columns), TopCount = 2 };
        q.Criteria.AddCondition(field, ConditionOperator.Equal, value);
        var rows = service.RetrieveMultiple(q).Entities;
        if (rows.Count != 1) throw new Fault(rows.Count == 0 ? "NOT_FOUND" : "DUPLICATE_KEY");
        return rows[0];
    }

}
public sealed class LifecycleGuard : IPlugin
{
    public void Execute(IServiceProvider provider)
    {
        var c = (IPluginExecutionContext)provider.GetService(typeof(IPluginExecutionContext));
        var trace = (ITracingService)provider.GetService(typeof(ITracingService));
        if (trace != null)
        {
            trace.Trace("qmcp lifecycle guard current {0}", DescribeContext(c));
            for (var observed = c.ParentContext; observed != null; observed = observed.ParentContext)
                trace.Trace("qmcp lifecycle guard ancestor {0}", DescribeContext(observed));
        }
        IOrganizationService? metadata = null;
        try { metadata = ((IOrganizationServiceFactory)provider.GetService(typeof(IOrganizationServiceFactory))).CreateOrganizationService(null); }
        catch (Exception) { }
        for (var parent = c.ParentContext; parent != null; parent = parent.ParentContext)
            if (metadata != null && IsTrustedFrameworkParent(c, parent, metadata)) return;
        // In the observed native handoff, companion write contexts retain the
        // registered post handler but omit the nested AcceptAcquire API context.
        // This ancestry authorizes only the four acquisition persistence writes.
        var acquisitionWrite =
            (c.MessageName == "Create" && (c.PrimaryEntityName == "qmcp_wqattempt" || c.PrimaryEntityName == "qmcp_wqcommand")) ||
            (c.MessageName == "Update" && (c.PrimaryEntityName == "qmcp_wqitemcontext" || c.PrimaryEntityName == "qmcp_wqcursor"));
        if (acquisitionWrite && metadata != null && LifecyclePlugin.HasAcquisitionPostAncestor(c, metadata)) return;
        // Companion state is only writable through framework actions. Principal/bootstrap configuration is separately privileged.
        if (c.PrimaryEntityName != "workqueueitem") throw new InvalidPluginExecutionException("LIFECYCLE_BYPASS");
        var service = ((IOrganizationServiceFactory)provider.GetService(typeof(IOrganizationServiceFactory))).CreateOrganizationService(null);
        if (c.MessageName == "Update" && ValidateAcquisitionAdmission(c, service)) return;
        // Admission-only privileged reads prevent a caller's hidden registry rows from bypassing the guard.
        // This service performs no writes and is never used by the lifecycle engine.
        Entity? entity = c.InputParameters.Contains("Target") ? c.InputParameters["Target"] as Entity : null;
        var queues=new HashSet<Guid>();var queue=entity?.GetAttributeValue<EntityReference>("workqueueid");if(queue!=null)queues.Add(queue.Id);
        if(c.MessageName!="Create" && c.PrimaryEntityId!=Guid.Empty){var old=service.Retrieve("workqueueitem",c.PrimaryEntityId,new Microsoft.Xrm.Sdk.Query.ColumnSet("workqueueid")).GetAttributeValue<EntityReference>("workqueueid");if(old!=null)queues.Add(old.Id);}
        foreach(var id in queues) {
            var query=new Microsoft.Xrm.Sdk.Query.QueryExpression("qmcp_wqqueuebinding"){ColumnSet=new Microsoft.Xrm.Sdk.Query.ColumnSet("qmcp_key"),TopCount=1};
            query.Criteria.AddCondition("qmcp_key",Microsoft.Xrm.Sdk.Query.ConditionOperator.Equal,id.ToString());
            if(service.RetrieveMultiple(query).Entities.Count!=0)throw new InvalidPluginExecutionException("LIFECYCLE_BYPASS");
        }
    }

    static bool ValidateAcquisitionAdmission(IPluginExecutionContext c, IOrganizationService service)
    {
        var target = c.InputParameters.Contains("Target") ? c.InputParameters["Target"] as Entity : null;
        if (target == null || c.PrimaryEntityId == Guid.Empty) throw new InvalidPluginExecutionException("LIFECYCLE_BYPASS");
        var before = service.Retrieve("workqueueitem", c.PrimaryEntityId, new ColumnSet("statecode", "statuscode", "workqueueid"));
        var queue = before.GetAttributeValue<EntityReference>("workqueueid");
        if (queue == null) throw new InvalidPluginExecutionException("LIFECYCLE_BYPASS");
        var bindingQuery = new QueryExpression("qmcp_wqqueuebinding") { ColumnSet = new ColumnSet("qmcp_queuekey"), TopCount = 2 }; bindingQuery.Criteria.AddCondition("qmcp_key", ConditionOperator.Equal, queue.Id.ToString());
        var bindingRows = service.RetrieveMultiple(bindingQuery).Entities; if (bindingRows.Count == 0) return false; if (bindingRows.Count != 1) throw new InvalidPluginExecutionException("LIFECYCLE_BYPASS");
        var allowed = new HashSet<string>(new[] { "machineuser", "processorid", "processortype", "statecode", "statuscode", "workqueueitemid", "modifiedby", "modifiedon", "modifiedonbehalfby" }, StringComparer.Ordinal);
        if (target.Attributes.Keys.Any(x => !allowed.Contains(x))) throw new InvalidPluginExecutionException("LIFECYCLE_BYPASS");
        var from = before.GetAttributeValue<OptionSetValue>("statecode")?.Value;
        var fromStatus = before.GetAttributeValue<OptionSetValue>("statuscode")?.Value;
        var to = target.GetAttributeValue<OptionSetValue>("statecode")?.Value;
        var toStatus = target.GetAttributeValue<OptionSetValue>("statuscode")?.Value;
        if (from != 0 || to != 1 || toStatus != 1) throw new InvalidPluginExecutionException("LIFECYCLE_BYPASS");
        var binding = bindingRows[0];
        var queueKey = binding.GetAttributeValue<string>("qmcp_queuekey");
        var definition = FindOne(service, "qmcp_wqdefinition", "qmcp_key", queueKey, "qmcp_document");
        var policy = Json.Read<QueuePolicy>(definition.GetAttributeValue<string>("qmcp_document") ?? "{}");
        if (!policy.Enabled) throw new InvalidPluginExecutionException("LIFECYCLE_BYPASS");
        if (!policy.Grants.TryGetValue(c.InitiatingUserId.ToString(), out var grants) || !grants.Contains("worker")) throw new InvalidPluginExecutionException("LIFECYCLE_BYPASS");
        var intentKey = Json.Hash("acquire|" + c.InitiatingUserId.ToString() + "|" + queueKey);
        var intentRow = FindOne(service, "qmcp_wqcursor", "qmcp_key", intentKey, "qmcp_document");
        var intent = Json.Read<AcquisitionIntent>(intentRow.GetAttributeValue<string>("qmcp_document") ?? "{}");
        if (intent.Status != "Prepared" || intent.ActorId != c.InitiatingUserId.ToString() || intent.Expires <= DateTime.UtcNow) throw new InvalidPluginExecutionException("LIFECYCLE_BYPASS");
        return true;
    }

    static Entity FindOne(IOrganizationService service, string table, string field, string value, params string[] columns)
    {
        var q = new QueryExpression(table) { ColumnSet = new ColumnSet(columns), TopCount = 2 }; q.Criteria.AddCondition(field, ConditionOperator.Equal, value);
        var rows = service.RetrieveMultiple(q).Entities; if (rows.Count != 1) throw new InvalidPluginExecutionException("LIFECYCLE_BYPASS"); return rows[0];
    }

    static string DescribeContext(IPluginExecutionContext context)
    {
        var variables = context.SharedVariables;
        var keys = variables == null ? "" : string.Join(",", variables.Keys.Cast<string>().OrderBy(x => x, StringComparer.Ordinal));
        var marker = variables != null && variables.Contains("qmcp.runtime");
        var markerType = marker && variables!["qmcp.runtime"] != null ? variables["qmcp.runtime"]!.GetType().FullName : "";
        var extension = context.OwningExtension;
        var target = context.InputParameters != null && context.InputParameters.Contains("Target") ? context.InputParameters["Target"] as Entity : null;
        var targetAttributes = target == null ? "" : string.Join(",", target.Attributes.Keys.OrderBy(x => x, StringComparer.Ordinal));
        return $"message={context.MessageName}; stage={context.Stage}; depth={context.Depth}; userId={context.UserId}; initiatingUserId={context.InitiatingUserId}; isInTransaction={context.IsInTransaction}; owningExtensionLogicalName={extension?.LogicalName ?? ""}; owningExtensionId={extension?.Id.ToString() ?? ""}; targetAttributeNames={targetAttributes}; sharedVariableKeys={keys}; runtimeMarkerPresent={marker}; runtimeMarkerType={markerType ?? ""}";
    }

    static bool IsTrustedFrameworkParent(IPluginExecutionContext current, IPluginExecutionContext parent, IOrganizationService metadata)
    {
        if (!current.IsInTransaction || !parent.IsInTransaction || current.InitiatingUserId != parent.InitiatingUserId ||
            !parent.MessageName.StartsWith("qmcp_WQ_", StringComparison.Ordinal) || !Engine.Roles.ContainsKey(parent.MessageName.Substring("qmcp_WQ_".Length)) || parent.Stage != 30 || parent.Mode != 0)
            return false;
        var extension = parent.OwningExtension;
        if (extension == null || extension.LogicalName != "sdkmessageprocessingstep" || extension.Id == Guid.Empty) return false;
        try
        {
            var step = metadata.Retrieve("sdkmessageprocessingstep", extension.Id, new ColumnSet("stage", "mode", "eventhandler"));
            if (step.GetAttributeValue<OptionSetValue>("stage")?.Value != 30 || step.GetAttributeValue<OptionSetValue>("mode")?.Value != 0) return false;
            var handler = step.GetAttributeValue<EntityReference>("eventhandler");
            if (handler == null || handler.LogicalName != "plugintype" || handler.Id == Guid.Empty) return false;
            var type = metadata.Retrieve("plugintype", handler.Id, new ColumnSet("typename", "assemblyname"));
            return type.GetAttributeValue<string>("typename") == typeof(LifecyclePlugin).FullName &&
                type.GetAttributeValue<string>("assemblyname") == typeof(LifecyclePlugin).Assembly.GetName().Name;
        }
        catch (Exception) { return false; }
    }
}
