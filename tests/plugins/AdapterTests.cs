using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Query;
using Microsoft.Xrm.Sdk.Messages;
using Moq;
using QueueFramework.Plugins;
using Xunit;
namespace QueueFramework.Tests;
public class AdapterTests {
    [Fact] public void MovingManagedItemToAnotherQueueCannotBypassGuard(){
        var oldQueue=Guid.NewGuid();var newQueue=Guid.NewGuid();var item=Guid.NewGuid();
        var context=new Mock<IPluginExecutionContext>();context.SetupGet(c=>c.PrimaryEntityName).Returns("workqueueitem");context.SetupGet(c=>c.PrimaryEntityId).Returns(item);context.SetupGet(c=>c.MessageName).Returns("Update");var target=new Entity("workqueueitem",item);target["workqueueid"]=new EntityReference("workqueue",newQueue);context.SetupGet(c=>c.InputParameters).Returns(new ParameterCollection{{"Target",target}});
        var service=new Mock<IOrganizationService>(MockBehavior.Strict);var previous=new Entity("workqueueitem",item);previous["workqueueid"]=new EntityReference("workqueue",oldQueue);
        service.Setup(s=>s.Retrieve("workqueueitem",item,It.IsAny<ColumnSet>())).Returns(previous);
        service.Setup(s=>s.RetrieveMultiple(It.IsAny<QueryBase>())).Returns<QueryBase>(q=>new EntityCollection(((QueryExpression)q).Criteria.Conditions[0].Values[0].ToString()==oldQueue.ToString()?new List<Entity>{new Entity("qmcp_wqqueuebinding")}:new List<Entity>()));
        var factory=new Mock<IOrganizationServiceFactory>();factory.Setup(f=>f.CreateOrganizationService(null)).Returns(service.Object);var provider=new Mock<IServiceProvider>();provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object);provider.Setup(p=>p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object);
        Assert.Equal("LIFECYCLE_BYPASS",Assert.Throws<InvalidPluginExecutionException>(()=>new LifecycleGuard().Execute(provider.Object)).Message);factory.Verify(f=>f.CreateOrganizationService(null),Times.Once);service.Verify(s=>s.Update(It.IsAny<Entity>()),Times.Never);
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
    [Fact] public void CompanionRawMutationDenied(){
        var context=new Mock<IPluginExecutionContext>();context.SetupGet(c=>c.PrimaryEntityName).Returns("qmcp_wqattempt");var provider=new Mock<IServiceProvider>();provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object);
        Assert.Equal("LIFECYCLE_BYPASS",Assert.Throws<InvalidPluginExecutionException>(()=>new LifecycleGuard().Execute(provider.Object)).Message);
    }
    [Fact] public void TrustedParentAllowsFrameworkMutation(){
        var parent=new Mock<IPluginExecutionContext>();parent.SetupGet(c=>c.MessageName).Returns("qmcp_WQ_Complete");parent.SetupGet(c=>c.SharedVariables).Returns(new ParameterCollection{{"qmcp.runtime",true}});
        var context=new Mock<IPluginExecutionContext>();context.SetupGet(c=>c.ParentContext).Returns(parent.Object);var provider=new Mock<IServiceProvider>();provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object);
        new LifecycleGuard().Execute(provider.Object);
    }
    [Fact] public void PluginUsesInitiatingIdentityAndDoesNotElevate(){
        var user=Guid.NewGuid();var context=new Mock<IPluginExecutionContext>();context.SetupGet(c=>c.InitiatingUserId).Returns(user);context.SetupGet(c=>c.MessageName).Returns("qmcp_WQ_GetQueueHealth");
        var service=new Mock<IOrganizationService>();service.Setup(s=>s.RetrieveMultiple(It.IsAny<QueryBase>())).Returns(new EntityCollection());
        var factory=new Mock<IOrganizationServiceFactory>();factory.Setup(f=>f.CreateOrganizationService(user)).Returns(service.Object);
        var provider=new Mock<IServiceProvider>();provider.Setup(p=>p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object);provider.Setup(p=>p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object);provider.Setup(p=>p.GetService(typeof(ITracingService))).Returns(Mock.Of<ITracingService>());
        Assert.Throws<InvalidPluginExecutionException>(()=>new LifecyclePlugin().Execute(provider.Object));factory.Verify(f=>f.CreateOrganizationService(user),Times.Once);factory.Verify(f=>f.CreateOrganizationService(null),Times.Never);
    }
}
