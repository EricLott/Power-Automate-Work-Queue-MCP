using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Query;
using Microsoft.Xrm.Sdk.Messages;
using Moq;
using QueueFramework.Plugins;
using Xunit;
namespace QueueFramework.Tests;
public class AdapterTests {
    sealed class ErrorCodeException : Exception { public int ErrorCode { get; } public ErrorCodeException(int code) : base("secret customer payload") { ErrorCode = code; } }
    [Fact] public void MovingManagedItemToAnotherQueueCannotBypassGuard(){
        var oldQueue=Guid.NewGuid();var newQueue=Guid.NewGuid();var item=Guid.NewGuid();
        var context=new Mock<IPluginExecutionContext>();context.SetupGet(c=>c.PrimaryEntityName).Returns("workqueueitem");context.SetupGet(c=>c.PrimaryEntityId).Returns(item);context.SetupGet(c=>c.MessageName).Returns("Update");var target=new Entity("workqueueitem",item);target["workqueueid"]=new EntityReference("workqueue",newQueue);context.SetupGet(c=>c.InputParameters).Returns(new ParameterCollection{{"Target",target}});
        var service=new Mock<IOrganizationService>(MockBehavior.Strict);var previous=new Entity("workqueueitem",item);previous["workqueueid"]=new EntityReference("workqueue",oldQueue);
        service.Setup(s=>s.Retrieve("workqueueitem",item,It.IsAny<ColumnSet>())).Returns(previous);
        service.Setup(s=>s.RetrieveMultiple(It.IsAny<QueryBase>())).Returns<QueryBase>(q=>new EntityCollection(((QueryExpression)q).Criteria.Conditions[0].Values[0].ToString()==oldQueue.ToString()?new List<Entity>{new Entity("qmcp_wqqueuebinding")}:new List<Entity>()));
        var factory=new Mock<IOrganizationServiceFactory>();factory.Setup(f=>f.CreateOrganizationService(null)).Returns(service.Object);var provider=new Mock<IServiceProvider>();provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object);provider.Setup(p=>p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object);
        Assert.Equal("LIFECYCLE_BYPASS",Assert.Throws<InvalidPluginExecutionException>(()=>new LifecycleGuard().Execute(provider.Object)).Message);factory.Verify(f=>f.CreateOrganizationService(null),Times.Exactly(2));service.Verify(s=>s.Update(It.IsAny<Entity>()),Times.Never);
    }
    [Fact] public void TransactionRequiredBeforeAnyWrite(){var service=new Mock<IOrganizationService>(MockBehavior.Strict);var context=new Mock<IPluginExecutionContext>();var store=new DataverseStore(service.Object,context.Object);Assert.Equal("TRANSACTION_REQUIRED",Assert.Throws<Fault>(()=>store.Atomic(()=>1)).Code);service.VerifyNoOtherCalls();}
    [Fact] public void NativeAcquisitionUsesDequeueInsteadOfListingWork(){
        var service=new Mock<IOrganizationService>(MockBehavior.Strict);var context=new Mock<IPluginExecutionContext>();
        var policy=new Entity("qmcp_wqdefinition"){RowVersion="1"};policy["qmcp_key"]="mail";policy["qmcp_queuekey"]="mail";policy["qmcp_document"]=Json.Write(new QueuePolicy{NativeQueueId="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"});
        service.Setup(s=>s.RetrieveMultiple(It.Is<QueryBase>(q=>((QueryExpression)q).EntityName=="qmcp_wqdefinition"))).Returns(new EntityCollection(new List<Entity>{policy}));
        service.Setup(s=>s.Execute(It.Is<OrganizationRequest>(r=>r.RequestName=="Dequeue"&&((EntityReference)r["Target"]).LogicalName=="workqueue"))).Returns(new OrganizationResponse());
        Assert.Null(new DataverseStore(service.Object,context.Object).NativeDequeue("mail",DateTime.UtcNow));
        service.Verify(s=>s.RetrieveMultiple(It.Is<QueryBase>(q=>((QueryExpression)q).EntityName=="workqueueitem")),Times.Never);
        service.Verify(s=>s.Update(It.IsAny<Entity>()),Times.Never);
    }
    [Fact] public void UnknownDequeueResponseFailsClosed(){
        var service=new Mock<IOrganizationService>();var context=new Mock<IPluginExecutionContext>();
        var row=new Entity("qmcp_wqdefinition"){RowVersion="1"};row["qmcp_key"]="mail";row["qmcp_queuekey"]="mail";row["qmcp_document"]=Json.Write(new QueuePolicy{NativeQueueId=Guid.NewGuid().ToString()});
        service.Setup(s=>s.RetrieveMultiple(It.IsAny<QueryBase>())).Returns(new EntityCollection(new List<Entity>{row}));
        var response=new OrganizationResponse();response.Results["unknown"]="opaque";service.Setup(s=>s.Execute(It.IsAny<OrganizationRequest>())).Returns(response);
        Assert.Equal("DEQUEUE_RESPONSE_UNVALIDATED",Assert.Throws<Fault>(()=>new DataverseStore(service.Object,context.Object).NativeDequeue("mail",DateTime.UtcNow)).Code);
    }
    [Fact] public void UpdatesUseOptimisticConcurrency(){
        var service=new Mock<IOrganizationService>();var context=new Mock<IPluginExecutionContext>();var entity=new Entity("qmcp_wqattempt",Guid.NewGuid()){RowVersion="8"};entity["qmcp_key"]="attempt";entity["qmcp_queuekey"]="mail";entity["qmcp_document"]="{}";
        service.Setup(s=>s.RetrieveMultiple(It.IsAny<QueryBase>())).Returns(new EntityCollection(new List<Entity>{entity}));
        new DataverseStore(service.Object,context.Object).Put(new Row{Kind="attempt",Key="attempt",Queue="mail",Body="{}"},7);
        service.Verify(s=>s.Execute(It.Is<UpdateRequest>(r=>r.ConcurrencyBehavior==ConcurrencyBehavior.IfRowVersionMatches&&r.Target.RowVersion=="7")),Times.Once);
    }
    [Fact] public void ReadsSelectOnlyAdapterColumns(){
        var service=new Mock<IOrganizationService>();var context=new Mock<IPluginExecutionContext>();QueryExpression? observed=null;
        var entity=new Entity("qmcp_wqattempt",Guid.NewGuid()){RowVersion="8"};entity["qmcp_key"]="attempt";entity["qmcp_queuekey"]="mail";entity["qmcp_document"]="{}";
        service.Setup(s=>s.RetrieveMultiple(It.IsAny<QueryBase>())).Callback<QueryBase>(q=>observed=(QueryExpression)q).Returns(new EntityCollection(new List<Entity>{entity}));
        new DataverseStore(service.Object,context.Object).Get("attempt","attempt");
        Assert.NotNull(observed);Assert.False(observed!.ColumnSet.AllColumns);Assert.Equal(new[]{"modifiedon","qmcp_document","qmcp_key","qmcp_queuekey","versionnumber"},observed.ColumnSet.Columns.OrderBy(x=>x).ToArray());
    }
    [Theory]
    [InlineData("attempt", "after-attempt", "Create")]
    [InlineData("itemcontext", "after-context", "Update")]
    [InlineData("cursor", "after-intent", "Update")]
    [InlineData("command", "after-receipt", "Create")]
    public void AcquisitionProofFaultsAfterEachDurableWrite(string kind, string fault, string operation)
    {
        var context = new Mock<IPluginExecutionContext>();
        context.SetupGet(c => c.MessageName).Returns("qmcp_WQ_AcceptAcquire");
        var service = new Mock<IOrganizationService>(MockBehavior.Strict);
        var queue = new Entity("qmcp_wqdefinition") { RowVersion = "1" };
        queue["qmcp_key"] = "mail"; queue["qmcp_document"] = Json.Write(new QueuePolicy { OwnerTeamId = Guid.NewGuid().ToString() });
        service.Setup(s => s.RetrieveMultiple(It.Is<QueryBase>(q => ((QueryExpression)q).EntityName == "qmcp_wqdefinition"))).Returns(new EntityCollection(new List<Entity> { queue }));
        var store = new DataverseStore(service.Object, context.Object) { ProofFault = fault };
        if (operation == "Create")
        {
            service.Setup(s => s.Create(It.IsAny<Entity>())).Returns(Guid.NewGuid());
            Assert.Equal("INJECTED_PROOF_FAILURE", Assert.Throws<Fault>(() => store.Add(new Row { Kind = kind, Key = "k", Queue = "mail", Body = "{}" })).Code);
            service.Verify(s => s.Create(It.IsAny<Entity>()), Times.Once);
        }
        else
        {
            var existing = new Entity(DataverseStore.Tables[kind], Guid.NewGuid()) { RowVersion = "1" };
            existing["qmcp_key"] = "k"; existing["qmcp_queuekey"] = "mail"; existing["qmcp_document"] = "{}";
            service.Setup(s => s.RetrieveMultiple(It.Is<QueryBase>(q => ((QueryExpression)q).EntityName == DataverseStore.Tables[kind]))).Returns(new EntityCollection(new List<Entity> { existing }));
            service.Setup(s => s.Execute(It.IsAny<UpdateRequest>())).Returns(new OrganizationResponse());
            Assert.Equal("INJECTED_PROOF_FAILURE", Assert.Throws<Fault>(() => store.Put(new Row { Kind = kind, Key = "k", Queue = "mail", Body = "{}" }, 1)).Code);
            service.Verify(s => s.Execute(It.IsAny<UpdateRequest>()), Times.Once);
        }
    }
    [Theory]
    [InlineData(true, "deployment")]
    [InlineData(false, "worker")]
    public void ProofFaultRequiresNonProductionDeploymentPrincipal(bool production, string role)
    {
        var user = Guid.NewGuid();
        var context = new Mock<IPluginExecutionContext>();
        context.SetupGet(c => c.MessageName).Returns("qmcp_WQ_GetQueueHealth");
        context.SetupGet(c => c.InitiatingUserId).Returns(user);
        context.SetupGet(c => c.InputParameters).Returns(new ParameterCollection { { "QueueKey", "mail" } });
        var principal = new Entity("qmcp_wqprincipal") { RowVersion = "1" };
        principal["qmcp_key"] = user.ToString();
        principal["qmcp_document"] = Json.Write(new { production, roles = new[] { role }, proofFault = "after-context" });
        var service = new Mock<IOrganizationService>(MockBehavior.Strict);
        service.Setup(s => s.RetrieveMultiple(It.Is<QueryBase>(q => ((QueryExpression)q).EntityName == "qmcp_wqprincipal"))).Returns(new EntityCollection(new List<Entity> { principal }));
        var factory = new Mock<IOrganizationServiceFactory>();
        factory.Setup(f => f.CreateOrganizationService(user)).Returns(service.Object);
        var provider = new Mock<IServiceProvider>();
        provider.Setup(p => p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object);
        provider.Setup(p => p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object);
        provider.Setup(p => p.GetService(typeof(ITracingService))).Returns(Mock.Of<ITracingService>());
        Assert.Equal("PROOF_FAULT_DENIED", Assert.Throws<InvalidPluginExecutionException>(() => new LifecyclePlugin().Execute(provider.Object)).Message);
    }
    [Fact]
    public void AcquisitionProofHooksIgnoreNonAcceptAcquireWrites()
    {
        var context = new Mock<IPluginExecutionContext>();
        context.SetupGet(c => c.MessageName).Returns("qmcp_WQ_Complete");
        var service = new Mock<IOrganizationService>(MockBehavior.Strict);
        var existing = new Entity(DataverseStore.Tables["itemcontext"], Guid.NewGuid()) { RowVersion = "1" };
        existing["qmcp_key"] = "k"; existing["qmcp_queuekey"] = "mail"; existing["qmcp_document"] = "{}";
        service.Setup(s => s.RetrieveMultiple(It.Is<QueryBase>(q => ((QueryExpression)q).EntityName == DataverseStore.Tables["itemcontext"]))).Returns(new EntityCollection(new List<Entity> { existing }));
        service.Setup(s => s.Execute(It.IsAny<UpdateRequest>())).Returns(new OrganizationResponse());
        var store = new DataverseStore(service.Object, context.Object) { ProofFault = "after-context" };
        store.Put(new Row { Kind = "itemcontext", Key = "k", Queue = "mail", Body = "{}" }, 1);
        service.Verify(s => s.Execute(It.IsAny<UpdateRequest>()), Times.Once);
    }
    [Fact] public void CompanionRawMutationDenied(){
        var context=new Mock<IPluginExecutionContext>();context.SetupGet(c=>c.PrimaryEntityName).Returns("qmcp_wqattempt");var provider=new Mock<IServiceProvider>();provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object);
        Assert.Equal("LIFECYCLE_BYPASS",Assert.Throws<InvalidPluginExecutionException>(()=>new LifecycleGuard().Execute(provider.Object)).Message);
    }
    [Fact] public void RegisteredFrameworkParentAllowsFrameworkMutation(){
        var user=Guid.NewGuid(); var stepId=Guid.NewGuid(); var typeId=Guid.NewGuid();
        var parent=new Mock<IPluginExecutionContext>(); parent.SetupGet(c=>c.MessageName).Returns("qmcp_WQ_Complete"); parent.SetupGet(c=>c.Stage).Returns(30); parent.SetupGet(c=>c.Mode).Returns(0); parent.SetupGet(c=>c.IsInTransaction).Returns(true); parent.SetupGet(c=>c.InitiatingUserId).Returns(user); parent.SetupGet(c=>c.OwningExtension).Returns(new EntityReference("sdkmessageprocessingstep",stepId));
        var context=new Mock<IPluginExecutionContext>(); context.SetupGet(c=>c.ParentContext).Returns(parent.Object); context.SetupGet(c=>c.InitiatingUserId).Returns(user); context.SetupGet(c=>c.IsInTransaction).Returns(true); context.SetupGet(c=>c.PrimaryEntityName).Returns("workqueueitem");
        var step=new Entity("sdkmessageprocessingstep",stepId); step["stage"]=new OptionSetValue(30); step["mode"]=new OptionSetValue(0); step["eventhandler"]=new EntityReference("plugintype",typeId);
        var type=new Entity("plugintype",typeId); type["typename"]=typeof(LifecyclePlugin).FullName; type["assemblyname"]=typeof(LifecyclePlugin).Assembly.GetName().Name;
        var service=new Mock<IOrganizationService>(MockBehavior.Strict); service.Setup(s=>s.Retrieve("sdkmessageprocessingstep",stepId,It.IsAny<ColumnSet>())).Returns(step); service.Setup(s=>s.Retrieve("plugintype",typeId,It.IsAny<ColumnSet>())).Returns(type);
        var factory=new Mock<IOrganizationServiceFactory>(); factory.Setup(f=>f.CreateOrganizationService(null)).Returns(service.Object); var provider=new Mock<IServiceProvider>(); provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object); provider.Setup(p=>p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object); provider.Setup(p=>p.GetService(typeof(ITracingService))).Returns(Mock.Of<ITracingService>());
        new LifecycleGuard().Execute(provider.Object);
    }
    [Fact] public void MarkerOrPrefixWithoutRegisteredPluginIsDenied(){
        var user=Guid.NewGuid(); var stepId=Guid.NewGuid(); var typeId=Guid.NewGuid(); var parent=new Mock<IPluginExecutionContext>(); parent.SetupGet(c=>c.MessageName).Returns("qmcp_WQ_Complete"); parent.SetupGet(c=>c.Stage).Returns(30); parent.SetupGet(c=>c.Mode).Returns(0); parent.SetupGet(c=>c.IsInTransaction).Returns(true); parent.SetupGet(c=>c.InitiatingUserId).Returns(user); parent.SetupGet(c=>c.OwningExtension).Returns(new EntityReference("sdkmessageprocessingstep",stepId)); parent.SetupGet(c=>c.SharedVariables).Returns(new ParameterCollection{{"qmcp.runtime",true}});
        var context=new Mock<IPluginExecutionContext>(); context.SetupGet(c=>c.ParentContext).Returns(parent.Object); context.SetupGet(c=>c.InitiatingUserId).Returns(user); context.SetupGet(c=>c.IsInTransaction).Returns(true); context.SetupGet(c=>c.PrimaryEntityName).Returns("qmcp_wqattempt");
        var step=new Entity("sdkmessageprocessingstep",stepId); step["stage"]=new OptionSetValue(30); step["mode"]=new OptionSetValue(0); step["eventhandler"]=new EntityReference("plugintype",typeId); var type=new Entity("plugintype",typeId); type["typename"]="Other.Plugin"; type["assemblyname"]="Other";
        var service=new Mock<IOrganizationService>(MockBehavior.Strict); service.Setup(s=>s.Retrieve("sdkmessageprocessingstep",stepId,It.IsAny<ColumnSet>())).Returns(step); service.Setup(s=>s.Retrieve("plugintype",typeId,It.IsAny<ColumnSet>())).Returns(type); var factory=new Mock<IOrganizationServiceFactory>(); factory.Setup(f=>f.CreateOrganizationService(null)).Returns(service.Object); var provider=new Mock<IServiceProvider>(); provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object); provider.Setup(p=>p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object); provider.Setup(p=>p.GetService(typeof(ITracingService))).Returns(Mock.Of<ITracingService>());
        Assert.Equal("LIFECYCLE_BYPASS",Assert.Throws<InvalidPluginExecutionException>(()=>new LifecycleGuard().Execute(provider.Object)).Message);
    }
    [Fact] public void PluginUsesInitiatingIdentityAndDoesNotElevate(){
        var user=Guid.NewGuid();var context=new Mock<IPluginExecutionContext>();context.SetupGet(c=>c.InitiatingUserId).Returns(user);context.SetupGet(c=>c.MessageName).Returns("qmcp_WQ_GetQueueHealth");
        var service=new Mock<IOrganizationService>();service.Setup(s=>s.RetrieveMultiple(It.IsAny<QueryBase>())).Returns(new EntityCollection());
        var factory=new Mock<IOrganizationServiceFactory>();factory.Setup(f=>f.CreateOrganizationService(user)).Returns(service.Object);
        var provider=new Mock<IServiceProvider>();provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object);provider.Setup(p=>p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object);provider.Setup(p=>p.GetService(typeof(ITracingService))).Returns(Mock.Of<ITracingService>());
        Assert.Throws<InvalidPluginExecutionException>(()=>new LifecyclePlugin().Execute(provider.Object));factory.Verify(f=>f.CreateOrganizationService(user),Times.Once);factory.Verify(f=>f.CreateOrganizationService(null),Times.Never);
    }
    [Fact] public void AcceptAcquireCannotBeInvokedDirectly(){
        var user=Guid.NewGuid(); var context=new Mock<IPluginExecutionContext>(); context.SetupGet(c=>c.InitiatingUserId).Returns(user); context.SetupGet(c=>c.MessageName).Returns("qmcp_WQ_AcceptAcquire"); context.SetupGet(c=>c.ParentContext).Returns((IPluginExecutionContext)null!); context.SetupGet(c=>c.InputParameters).Returns(new ParameterCollection());
        var service=new Mock<IOrganizationService>(MockBehavior.Strict); var factory=new Mock<IOrganizationServiceFactory>(); factory.Setup(f=>f.CreateOrganizationService(user)).Returns(service.Object);
        var provider=new Mock<IServiceProvider>(); provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object); provider.Setup(p=>p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object); provider.Setup(p=>p.GetService(typeof(ITracingService))).Returns(Mock.Of<ITracingService>());
        Assert.Equal("ACQUISITION_HANDOFF_REQUIRED",Assert.Throws<InvalidPluginExecutionException>(()=>new LifecyclePlugin().Execute(provider.Object)).Message); service.VerifyNoOtherCalls();
    }
    [Theory] [InlineData("input")] [InlineData("processinguser")] [InlineData("processingstarttime")] public void NativeGuardRejectsImmutableUpdate(string field){
        var user=Guid.NewGuid(); var item=Guid.NewGuid(); var target=new Entity("workqueueitem",item); target[field]="forbidden"; var context=new Mock<IPluginExecutionContext>(); context.SetupGet(c=>c.PrimaryEntityName).Returns("workqueueitem"); context.SetupGet(c=>c.PrimaryEntityId).Returns(item); context.SetupGet(c=>c.MessageName).Returns("Update"); context.SetupGet(c=>c.InitiatingUserId).Returns(user); context.SetupGet(c=>c.InputParameters).Returns(new ParameterCollection{{"Target",target}});
        var service=new Mock<IOrganizationService>(MockBehavior.Strict); var before=new Entity("workqueueitem",item); before["workqueueid"]=new EntityReference("workqueue",Guid.NewGuid()); before["statecode"]=new OptionSetValue(0); service.Setup(s=>s.Retrieve("workqueueitem",item,It.IsAny<ColumnSet>())).Returns(before); service.Setup(s=>s.RetrieveMultiple(It.Is<QueryBase>(q=>((QueryExpression)q).EntityName=="qmcp_wqqueuebinding"))).Returns(new EntityCollection(new List<Entity>{new Entity("qmcp_wqqueuebinding")})); var factory=new Mock<IOrganizationServiceFactory>(); factory.Setup(f=>f.CreateOrganizationService(null)).Returns(service.Object); var provider=new Mock<IServiceProvider>(); provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object); provider.Setup(p=>p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object);
        Assert.Equal("LIFECYCLE_BYPASS",Assert.Throws<InvalidPluginExecutionException>(()=>new LifecycleGuard().Execute(provider.Object)).Message); service.Verify(s=>s.Retrieve("workqueueitem",item,It.IsAny<ColumnSet>()),Times.Once); service.Verify(s=>s.RetrieveMultiple(It.IsAny<QueryBase>()),Times.Once);
    }
    [Fact] public void NativeGuardAdmitsPreparedQueuedToProcessingClaim(){
        var user=Guid.NewGuid();var queue=Guid.NewGuid();var item=Guid.NewGuid();var request=Guid.NewGuid();
        var context=new Mock<IPluginExecutionContext>();context.SetupGet(c=>c.PrimaryEntityName).Returns("workqueueitem");context.SetupGet(c=>c.PrimaryEntityId).Returns(item);context.SetupGet(c=>c.MessageName).Returns("Update");context.SetupGet(c=>c.InitiatingUserId).Returns(user);
        var target=new Entity("workqueueitem",item);target["statecode"]=new OptionSetValue(1);target["statuscode"]=new OptionSetValue(1);context.SetupGet(c=>c.InputParameters).Returns(new ParameterCollection{{"Target",target}});
        var before=new Entity("workqueueitem",item);before["statecode"]=new OptionSetValue(0);before["statuscode"]=new OptionSetValue(0);before["workqueueid"]=new EntityReference("workqueue",queue);
        var binding=new Entity("qmcp_wqqueuebinding");binding["qmcp_queuekey"]="mail";
        var definition=new Entity("qmcp_wqdefinition");definition["qmcp_document"]=Json.Write(new QueuePolicy{NativeQueueId=queue.ToString(),Grants=new Dictionary<string,string[]>{{user.ToString(),new[]{"worker"}}}});
        var intent=new Entity("qmcp_wqcursor");intent["qmcp_document"]=Json.Write(new AcquisitionIntent{RequestId=request.ToString(),ActorId=user.ToString(),Expires=DateTime.UtcNow.AddMinutes(1)});
        var service=new Mock<IOrganizationService>(MockBehavior.Strict);service.Setup(s=>s.Retrieve("workqueueitem",item,It.IsAny<ColumnSet>())).Returns(before);
        service.Setup(s=>s.RetrieveMultiple(It.Is<QueryBase>(q=>((QueryExpression)q).EntityName=="qmcp_wqqueuebinding"))).Returns(new EntityCollection(new List<Entity>{binding}));
        service.Setup(s=>s.RetrieveMultiple(It.Is<QueryBase>(q=>((QueryExpression)q).EntityName=="qmcp_wqdefinition"))).Returns(new EntityCollection(new List<Entity>{definition}));
        service.Setup(s=>s.RetrieveMultiple(It.Is<QueryBase>(q=>((QueryExpression)q).EntityName=="qmcp_wqcursor"))).Returns(new EntityCollection(new List<Entity>{intent}));
        var factory=new Mock<IOrganizationServiceFactory>();factory.Setup(f=>f.CreateOrganizationService(null)).Returns(service.Object);var provider=new Mock<IServiceProvider>();provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object);provider.Setup(p=>p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object);provider.Setup(p=>p.GetService(typeof(ITracingService))).Returns(Mock.Of<ITracingService>());
        new LifecycleGuard().Execute(provider.Object);
    }
    [Fact] public void NativeGuardIgnoresUnregisteredQueueUpdate(){
        var item=Guid.NewGuid();var target=new Entity("workqueueitem",item);target["statecode"]=new OptionSetValue(1);target["statuscode"]=new OptionSetValue(1);var context=new Mock<IPluginExecutionContext>();context.SetupGet(c=>c.PrimaryEntityName).Returns("workqueueitem");context.SetupGet(c=>c.PrimaryEntityId).Returns(item);context.SetupGet(c=>c.MessageName).Returns("Update");context.SetupGet(c=>c.InputParameters).Returns(new ParameterCollection{{"Target",target}});
        var before=new Entity("workqueueitem",item);before["workqueueid"]=new EntityReference("workqueue",Guid.NewGuid());var service=new Mock<IOrganizationService>();service.Setup(s=>s.Retrieve("workqueueitem",item,It.IsAny<ColumnSet>())).Returns(before);service.Setup(s=>s.RetrieveMultiple(It.IsAny<QueryBase>())).Returns(new EntityCollection());var factory=new Mock<IOrganizationServiceFactory>();factory.Setup(f=>f.CreateOrganizationService(null)).Returns(service.Object);var provider=new Mock<IServiceProvider>();provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object);provider.Setup(p=>p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object);new LifecycleGuard().Execute(provider.Object);
    }
    [Theory] [InlineData(false, true)] [InlineData(true, false)] public void NativeGuardRejectsExpiredOrWrongActorIntent(bool expired,bool wrongActor){
        var user=Guid.NewGuid();var actor=wrongActor?Guid.NewGuid():user;var queue=Guid.NewGuid();var item=Guid.NewGuid();var target=new Entity("workqueueitem",item);target["statecode"]=new OptionSetValue(1);target["statuscode"]=new OptionSetValue(1);var context=new Mock<IPluginExecutionContext>();context.SetupGet(c=>c.PrimaryEntityName).Returns("workqueueitem");context.SetupGet(c=>c.PrimaryEntityId).Returns(item);context.SetupGet(c=>c.MessageName).Returns("Update");context.SetupGet(c=>c.InitiatingUserId).Returns(user);context.SetupGet(c=>c.InputParameters).Returns(new ParameterCollection{{"Target",target}});var before=new Entity("workqueueitem",item);before["statecode"]=new OptionSetValue(0);before["statuscode"]=new OptionSetValue(0);before["workqueueid"]=new EntityReference("workqueue",queue);var binding=new Entity("qmcp_wqqueuebinding");binding["qmcp_queuekey"]="mail";var def=new Entity("qmcp_wqdefinition");def["qmcp_document"]=Json.Write(new QueuePolicy{NativeQueueId=queue.ToString(),Grants=new Dictionary<string,string[]>{{user.ToString(),new[]{"worker"}}}});var cursor=new Entity("qmcp_wqcursor");cursor["qmcp_document"]=Json.Write(new AcquisitionIntent{ActorId=actor.ToString(),Expires=expired?DateTime.UtcNow.AddMinutes(-1):DateTime.UtcNow.AddMinutes(1)});var service=new Mock<IOrganizationService>();service.Setup(s=>s.Retrieve("workqueueitem",item,It.IsAny<ColumnSet>())).Returns(before);service.Setup(s=>s.RetrieveMultiple(It.Is<QueryBase>(q=>((QueryExpression)q).EntityName=="qmcp_wqqueuebinding"))).Returns(new EntityCollection(new List<Entity>{binding}));service.Setup(s=>s.RetrieveMultiple(It.Is<QueryBase>(q=>((QueryExpression)q).EntityName=="qmcp_wqdefinition"))).Returns(new EntityCollection(new List<Entity>{def}));service.Setup(s=>s.RetrieveMultiple(It.Is<QueryBase>(q=>((QueryExpression)q).EntityName=="qmcp_wqcursor"))).Returns(new EntityCollection(new List<Entity>{cursor}));var factory=new Mock<IOrganizationServiceFactory>();factory.Setup(f=>f.CreateOrganizationService(null)).Returns(service.Object);var provider=new Mock<IServiceProvider>();provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object);provider.Setup(p=>p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object);Assert.Equal("LIFECYCLE_BYPASS",Assert.Throws<InvalidPluginExecutionException>(()=>new LifecycleGuard().Execute(provider.Object)).Message);
    }
    [Fact] public void AcquisitionPostExecutesAcceptForValidNativeClaim(){
        var user=Guid.NewGuid();var queue=Guid.NewGuid();var item=Guid.NewGuid();var request=Guid.NewGuid();var target=new Entity("workqueueitem",item);target["statecode"]=new OptionSetValue(1);target["statuscode"]=new OptionSetValue(1);target["processinguser"]=new EntityReference("systemuser",user);target["processingstarttime"]=DateTime.UtcNow;var pre=new Entity("workqueueitem",item);pre["statecode"]=new OptionSetValue(0);pre["statuscode"]=new OptionSetValue(0);
        var context=new Mock<IPluginExecutionContext>();context.SetupGet(c=>c.IsInTransaction).Returns(true);context.SetupGet(c=>c.Stage).Returns(40);context.SetupGet(c=>c.Mode).Returns(0);context.SetupGet(c=>c.MessageName).Returns("Update");context.SetupGet(c=>c.PrimaryEntityName).Returns("workqueueitem");context.SetupGet(c=>c.PrimaryEntityId).Returns(item);context.SetupGet(c=>c.InitiatingUserId).Returns(user);context.SetupGet(c=>c.UserId).Returns(user);context.SetupGet(c=>c.InputParameters).Returns(new ParameterCollection{{"Target",target}});context.SetupGet(c=>c.PreEntityImages).Returns(new EntityImageCollection{{"Before",pre}});
        var native=new Entity("workqueueitem",item);native["workqueueid"]=new EntityReference("workqueue",queue);native["processinguser"]=new EntityReference("systemuser",user);native["statecode"]=new OptionSetValue(1);native["statuscode"]=new OptionSetValue(1);var binding=new Entity("qmcp_wqqueuebinding");binding["qmcp_queuekey"]="mail";var intent=new Entity("qmcp_wqcursor");intent["qmcp_document"]=Json.Write(new AcquisitionIntent{RequestId=request.ToString(),ActorId=user.ToString(),Expires=DateTime.UtcNow.AddMinutes(1)});
        var system=new Mock<IOrganizationService>(MockBehavior.Strict);system.Setup(s=>s.Retrieve("workqueueitem",item,It.IsAny<ColumnSet>())).Returns(native);system.Setup(s=>s.RetrieveMultiple(It.Is<QueryBase>(q=>((QueryExpression)q).EntityName=="qmcp_wqqueuebinding"))).Returns(new EntityCollection(new List<Entity>{binding}));system.Setup(s=>s.RetrieveMultiple(It.Is<QueryBase>(q=>((QueryExpression)q).EntityName=="qmcp_wqcursor"))).Returns(new EntityCollection(new List<Entity>{intent}));var caller=new Mock<IOrganizationService>(MockBehavior.Strict);caller.Setup(s=>s.Execute(It.Is<OrganizationRequest>(r=>r.RequestName=="qmcp_WQ_AcceptAcquire"&&r["RequestId"].ToString()==request.ToString()&&r["ItemId"].ToString()==item.ToString()))).Returns(new OrganizationResponse());var factory=new Mock<IOrganizationServiceFactory>();factory.Setup(f=>f.CreateOrganizationService(null)).Returns(system.Object);factory.Setup(f=>f.CreateOrganizationService(user)).Returns(caller.Object);var provider=new Mock<IServiceProvider>();provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object);provider.Setup(p=>p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object);
        new AcquisitionPostPlugin().Execute(provider.Object);caller.VerifyAll();
    }
    [Fact] public void AcquisitionPostSkipsUnregisteredQueueAndCompletedUpdate(){
        var user=Guid.NewGuid();var queue=Guid.NewGuid();var item=Guid.NewGuid();var target=new Entity("workqueueitem",item);target["statecode"]=new OptionSetValue(2);target["statuscode"]=new OptionSetValue(2);var pre=new Entity("workqueueitem",item);pre["statecode"]=new OptionSetValue(2);pre["statuscode"]=new OptionSetValue(2);var context=new Mock<IPluginExecutionContext>();context.SetupGet(c=>c.IsInTransaction).Returns(true);context.SetupGet(c=>c.Stage).Returns(40);context.SetupGet(c=>c.Mode).Returns(0);context.SetupGet(c=>c.MessageName).Returns("Update");context.SetupGet(c=>c.PrimaryEntityName).Returns("workqueueitem");context.SetupGet(c=>c.PrimaryEntityId).Returns(item);context.SetupGet(c=>c.InitiatingUserId).Returns(user);context.SetupGet(c=>c.UserId).Returns(user);context.SetupGet(c=>c.InputParameters).Returns(new ParameterCollection{{"Target",target}});context.SetupGet(c=>c.PreEntityImages).Returns(new EntityImageCollection{{"Before",pre}});var native=new Entity("workqueueitem",item);native["workqueueid"]=new EntityReference("workqueue",queue);var system=new Mock<IOrganizationService>();system.Setup(s=>s.Retrieve("workqueueitem",item,It.IsAny<ColumnSet>())).Returns(native);system.Setup(s=>s.RetrieveMultiple(It.IsAny<QueryBase>())).Returns(new EntityCollection());var caller=new Mock<IOrganizationService>(MockBehavior.Strict);var factory=new Mock<IOrganizationServiceFactory>();factory.Setup(f=>f.CreateOrganizationService(null)).Returns(system.Object);factory.Setup(f=>f.CreateOrganizationService(user)).Returns(caller.Object);var provider=new Mock<IServiceProvider>();provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object);provider.Setup(p=>p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object);new AcquisitionPostPlugin().Execute(provider.Object);caller.VerifyNoOtherCalls();
    }
    [Fact] public void UnexpectedPluginFailureIsGenericButTracedWithoutExceptionMessage(){
        var user=Guid.NewGuid(); var context=new Mock<IPluginExecutionContext>();
        context.SetupGet(c=>c.InitiatingUserId).Returns(user); context.SetupGet(c=>c.MessageName).Returns("qmcp_WQ_GetQueueHealth");
        context.SetupGet(c=>c.InputParameters).Returns(new ParameterCollection{{"QueueKey","mail"}});
        var principal=new Entity("qmcp_wqprincipal"){RowVersion="1"}; principal["qmcp_key"]=user.ToString(); principal["qmcp_queuekey"]=""; principal["qmcp_document"]="{\"roles\":[\"administrator\"],\"production\":false}";
        var service=new Mock<IOrganizationService>(MockBehavior.Strict);
        service.Setup(s=>s.RetrieveMultiple(It.Is<QueryBase>(q=>((QueryExpression)q).EntityName=="qmcp_wqprincipal"))).Returns(new EntityCollection(new List<Entity>{principal}));
        service.Setup(s=>s.RetrieveMultiple(It.Is<QueryBase>(q=>((QueryExpression)q).EntityName=="qmcp_wqdefinition"))).Throws(new InvalidOperationException("secret customer payload"));
        var factory=new Mock<IOrganizationServiceFactory>(); factory.Setup(f=>f.CreateOrganizationService(user)).Returns(service.Object);
        var traces=new List<string>(); var trace=new Mock<ITracingService>();
        trace.Setup(t=>t.Trace(It.IsAny<string>(),It.IsAny<object[]>())).Callback<string,object[]>((format,args)=>traces.Add(string.Format(format,args)));
        var provider=new Mock<IServiceProvider>(); provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object); provider.Setup(p=>p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object); provider.Setup(p=>p.GetService(typeof(ITracingService))).Returns(trace.Object);
        var error=Assert.Throws<InvalidPluginExecutionException>(()=>new LifecyclePlugin().Execute(provider.Object));
        Assert.Equal("RUNTIME_FAILURE",error.Message); var diagnostic=Assert.Single(traces,t=>t.Contains("unexpected failure")); Assert.Contains("exceptionType",diagnostic); Assert.Contains("stackTrace",diagnostic); Assert.Contains("innerTypes",diagnostic); Assert.Contains("organizationServiceErrorCode",diagnostic); Assert.DoesNotContain("secret customer payload",diagnostic);
    }
    [Fact] public void DataverseConcurrencyFaultIsSanitizedToFrameworkConflict(){
        var user=Guid.NewGuid(); var context=new Mock<IPluginExecutionContext>();
        context.SetupGet(c=>c.InitiatingUserId).Returns(user); context.SetupGet(c=>c.MessageName).Returns("qmcp_WQ_GetQueueHealth");
        context.SetupGet(c=>c.InputParameters).Returns(new ParameterCollection{{"QueueKey","mail"}});
        context.SetupGet(c=>c.SharedVariables).Returns(new ParameterCollection());
        context.SetupGet(c=>c.IsInTransaction).Returns(true);
        var principal=new Entity("qmcp_wqprincipal"){RowVersion="1"}; principal["qmcp_key"]=user.ToString(); principal["qmcp_document"]="{\"roles\":[\"administrator\"],\"production\":false}";
        var service=new Mock<IOrganizationService>(MockBehavior.Strict);
        service.Setup(s=>s.RetrieveMultiple(It.Is<QueryBase>(q=>((QueryExpression)q).EntityName=="qmcp_wqprincipal"))).Returns(new EntityCollection(new List<Entity>{principal}));
        service.Setup(s=>s.RetrieveMultiple(It.Is<QueryBase>(q=>((QueryExpression)q).EntityName=="qmcp_wqdefinition"))).Throws(new ErrorCodeException(-2147088254));
        var factory=new Mock<IOrganizationServiceFactory>(); factory.Setup(f=>f.CreateOrganizationService(user)).Returns(service.Object);
        var traces=new List<string>(); var trace=new Mock<ITracingService>(); trace.Setup(t=>t.Trace(It.IsAny<string>(),It.IsAny<object[]>())).Callback<string,object[]>((format,args)=>traces.Add(string.Format(format,args)));
        var provider=new Mock<IServiceProvider>(); provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object); provider.Setup(p=>p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object); provider.Setup(p=>p.GetService(typeof(ITracingService))).Returns(trace.Object);
        var error=Assert.Throws<InvalidPluginExecutionException>(()=>new LifecyclePlugin().Execute(provider.Object));
        Assert.Equal("VERSION_CONFLICT",error.Message); var diagnostic=Assert.Single(traces,t=>t.Contains("concurrency conflict")); Assert.DoesNotContain("secret customer payload",diagnostic);
    }
}
