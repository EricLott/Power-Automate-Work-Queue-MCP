using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Query;
using Moq;
using QueueFramework.Plugins;
using Xunit;
namespace QueueFramework.PluginTests;
public sealed class AcquisitionOriginTests
{
    [Theory]
    [InlineData(true, true, "PRINCIPAL_NOT_REGISTERED")]
    [InlineData(false, true, "ACQUISITION_HANDOFF_REQUIRED")]
    [InlineData(true, false, "ACQUISITION_HANDOFF_REQUIRED")]
    public void AcceptRequiresRegisteredPostHandlerAndCurrentTransaction(bool correctHandler, bool transaction, string expected)
    {
        var user = Guid.NewGuid(); var stepId = Guid.NewGuid(); var typeId = Guid.NewGuid();
        var parent = new Mock<IPluginExecutionContext>();
        parent.SetupGet(x => x.IsInTransaction).Returns(true);
        parent.SetupGet(x => x.Stage).Returns(40);
        parent.SetupGet(x => x.Mode).Returns(0);
        parent.SetupGet(x => x.MessageName).Returns("Update");
        parent.SetupGet(x => x.PrimaryEntityName).Returns("workqueueitem");
        parent.SetupGet(x => x.InitiatingUserId).Returns(user);
        parent.SetupGet(x => x.OwningExtension).Returns(new EntityReference("sdkmessageprocessingstep", stepId));
        var current = new Mock<IPluginExecutionContext>();
        current.SetupGet(x => x.IsInTransaction).Returns(transaction);
        current.SetupGet(x => x.MessageName).Returns("qmcp_WQ_AcceptAcquire");
        current.SetupGet(x => x.InitiatingUserId).Returns(user);
        current.SetupGet(x => x.ParentContext).Returns(parent.Object);
        var step = new Entity("sdkmessageprocessingstep", stepId);
        step["stage"] = new OptionSetValue(40); step["mode"] = new OptionSetValue(0);
        step["eventhandler"] = new EntityReference("plugintype", typeId);
        var type = new Entity("plugintype", typeId);
        type["typename"] = correctHandler ? typeof(AcquisitionPostPlugin).FullName : "Untrusted.Plugin";
        type["assemblyname"] = typeof(AcquisitionPostPlugin).Assembly.GetName().Name;
        var service = new Mock<IOrganizationService>(MockBehavior.Strict);
        service.Setup(x => x.Retrieve("sdkmessageprocessingstep", stepId, It.IsAny<ColumnSet>())).Returns(step);
        service.Setup(x => x.Retrieve("plugintype", typeId, It.IsAny<ColumnSet>())).Returns(type);
        service.Setup(x => x.RetrieveMultiple(It.IsAny<QueryBase>())).Returns(new EntityCollection());
        var factory = new Mock<IOrganizationServiceFactory>();
        factory.Setup(x => x.CreateOrganizationService(user)).Returns(service.Object);
        var provider = new Mock<IServiceProvider>();
        provider.Setup(x => x.GetService(typeof(IPluginExecutionContext))).Returns(current.Object);
        provider.Setup(x => x.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object);
        provider.Setup(x => x.GetService(typeof(ITracingService))).Returns(Mock.Of<ITracingService>());
        Assert.Equal(expected, Assert.Throws<InvalidPluginExecutionException>(() => new LifecyclePlugin().Execute(provider.Object)).Message);
    }
}
