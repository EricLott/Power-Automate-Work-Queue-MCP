using Microsoft.Xrm.Sdk;
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
            var store = new DataverseStore(service, context);
            var principal = store.Get("principal", context.InitiatingUserId.ToString()) ?? throw new Fault("PRINCIPAL_NOT_REGISTERED");
            var profile = Json.Object(principal.Body);
            var actor = new Actor { Id = context.InitiatingUserId.ToString(), Production = (bool?)profile["production"] ?? true, Roles = new HashSet<string>((profile["roles"] as JArray ?? new JArray()).Values<string>().Where(x => x != null).Select(x => x!)) };
            var proofFault = (string?)profile["proofFault"] ?? "";
            if (proofFault != "")
            {
                if (actor.Production || !actor.Has("deployment") || !new[] { "before-receipt", "after-dequeue" }.Contains(proofFault)) throw new Fault("PROOF_FAULT_DENIED");
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
            context.OutputParameters["ResultJson"] = new Engine(store).Execute(c, actor);
        }
        catch (Fault e) { trace.Trace("qmcp failure {0}; correlation {1}", e.Code, context.CorrelationId); throw new InvalidPluginExecutionException(e.Code); }
        catch (Exception) { trace.Trace("qmcp unexpected failure; correlation {0}", context.CorrelationId); throw new InvalidPluginExecutionException("RUNTIME_FAILURE"); }
    }
}
public sealed class LifecycleGuard : IPlugin
{
    public void Execute(IServiceProvider provider)
    {
        var c = (IPluginExecutionContext)provider.GetService(typeof(IPluginExecutionContext));
        for (var parent = c.ParentContext; parent != null; parent = parent.ParentContext)
            if (parent.MessageName.StartsWith("qmcp_WQ_", StringComparison.Ordinal) && parent.SharedVariables.Contains("qmcp.runtime") && parent.SharedVariables["qmcp.runtime"] is bool trusted && trusted) return;
        // Companion state is only writable through framework actions. Principal/bootstrap configuration is separately privileged.
        if (c.PrimaryEntityName != "workqueueitem") throw new InvalidPluginExecutionException("LIFECYCLE_BYPASS");
        // Admission-only privileged reads prevent a caller's hidden registry rows from bypassing the guard.
        // This service performs no writes and is never used by the lifecycle engine.
        var service = ((IOrganizationServiceFactory)provider.GetService(typeof(IOrganizationServiceFactory))).CreateOrganizationService(null);
        Entity? entity = c.InputParameters.Contains("Target") ? c.InputParameters["Target"] as Entity : null;
        var queues=new HashSet<Guid>();var queue=entity?.GetAttributeValue<EntityReference>("workqueueid");if(queue!=null)queues.Add(queue.Id);
        if(c.MessageName!="Create" && c.PrimaryEntityId!=Guid.Empty){var old=service.Retrieve("workqueueitem",c.PrimaryEntityId,new Microsoft.Xrm.Sdk.Query.ColumnSet("workqueueid")).GetAttributeValue<EntityReference>("workqueueid");if(old!=null)queues.Add(old.Id);}
        foreach(var id in queues) {
            var query=new Microsoft.Xrm.Sdk.Query.QueryExpression("qmcp_wqqueuebinding"){ColumnSet=new Microsoft.Xrm.Sdk.Query.ColumnSet("qmcp_key"),TopCount=1};
            query.Criteria.AddCondition("qmcp_key",Microsoft.Xrm.Sdk.Query.ConditionOperator.Equal,id.ToString());
            if(service.RetrieveMultiple(query).Entities.Count!=0)throw new InvalidPluginExecutionException("LIFECYCLE_BYPASS");
        }
    }
}
