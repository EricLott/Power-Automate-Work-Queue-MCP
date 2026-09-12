using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Query;
using Moq;
using QueueFramework.Plugins;
using Xunit;

namespace QueueFramework.Tests;

public sealed class PostGuardOriginTests
{
    static IServiceProvider Provider(string table, string message, Guid user, IPluginExecutionContext? parent, bool transaction = true, string handler = null!)
    {
        var stepId = Guid.NewGuid(); var typeId = Guid.NewGuid();
        var step = new Entity("sdkmessageprocessingstep", stepId) { ["stage"] = new OptionSetValue(40), ["mode"] = new OptionSetValue(0), ["eventhandler"] = new EntityReference("plugintype", typeId) };
        var type = new Entity("plugintype", typeId) { ["typename"] = handler ?? typeof(AcquisitionPostPlugin).FullName, ["assemblyname"] = typeof(AcquisitionPostPlugin).Assembly.GetName().Name };
        var service = new Mock<IOrganizationService>(MockBehavior.Strict);
        service.Setup(s => s.Retrieve("sdkmessageprocessingstep", It.IsAny<Guid>(), It.IsAny<ColumnSet>())).Returns(step);
        service.Setup(s => s.Retrieve("plugintype", It.IsAny<Guid>(), It.IsAny<ColumnSet>())).Returns(type);
        var context = new Mock<IPluginExecutionContext>(); context.SetupGet(c => c.PrimaryEntityName).Returns(table); context.SetupGet(c => c.MessageName).Returns(message); context.SetupGet(c => c.InitiatingUserId).Returns(user); context.SetupGet(c => c.IsInTransaction).Returns(transaction); context.SetupGet(c => c.ParentContext).Returns(parent!);
        var factory = new Mock<IOrganizationServiceFactory>(); factory.Setup(f => f.CreateOrganizationService(null)).Returns(service.Object);
        var provider = new Mock<IServiceProvider>(); provider.Setup(p => p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object); provider.Setup(p => p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object); provider.Setup(p => p.GetService(typeof(ITracingService))).Returns(Mock.Of<ITracingService>());
        return provider.Object;
    }

    static IPluginExecutionContext PostParent(Guid user, bool transaction = true)
    {
        var parent = new Mock<IPluginExecutionContext>(); parent.SetupGet(c => c.PrimaryEntityName).Returns("workqueueitem"); parent.SetupGet(c => c.MessageName).Returns("Update"); parent.SetupGet(c => c.Stage).Returns(40); parent.SetupGet(c => c.Mode).Returns(0); parent.SetupGet(c => c.IsInTransaction).Returns(transaction); parent.SetupGet(c => c.InitiatingUserId).Returns(user); parent.SetupGet(c => c.OwningExtension).Returns(new EntityReference("sdkmessageprocessingstep", Guid.NewGuid()));
        return parent.Object;
    }

    [Theory]
    [InlineData("qmcp_wqattempt", "Create")]
    [InlineData("qmcp_wqcommand", "Create")]
    [InlineData("qmcp_wqitemcontext", "Update")]
    [InlineData("qmcp_wqcursor", "Update")]
    public void RegisteredPostAllowsAcquisitionWrite(string table, string message)
    {
        var user = Guid.NewGuid(); var parent = PostParent(user); var provider = Provider(table, message, user, parent);
        new LifecycleGuard().Execute(provider);
    }

    [Fact] public void ForgedPostMarkerOrWrongPluginIsDenied()
    {
        var user = Guid.NewGuid(); var parent = PostParent(user); var provider = Provider("qmcp_wqattempt", "Create", user, parent, handler: "Other.Plugin");
        Assert.Equal("LIFECYCLE_BYPASS", Assert.Throws<InvalidPluginExecutionException>(() => new LifecycleGuard().Execute(provider)).Message);
    }

    [Fact] public void PostOriginCannotAuthorizeDefinitionWrite()
    {
        var user = Guid.NewGuid(); var parent = PostParent(user); var provider = Provider("qmcp_wqdefinition", "Update", user, parent);
        Assert.Equal("LIFECYCLE_BYPASS", Assert.Throws<InvalidPluginExecutionException>(() => new LifecycleGuard().Execute(provider)).Message);
    }

    [Fact] public void PostOriginWithWrongActorIsDenied()
    {
        var user = Guid.NewGuid(); var parent = PostParent(Guid.NewGuid()); var provider = Provider("qmcp_wqitemcontext", "Update", user, parent);
        Assert.Equal("LIFECYCLE_BYPASS", Assert.Throws<InvalidPluginExecutionException>(() => new LifecycleGuard().Execute(provider)).Message);
    }

    [Fact] public void PostOriginOutsideTransactionIsDenied()
    {
        var user = Guid.NewGuid(); var parent = PostParent(user); var provider = Provider("qmcp_wqcursor", "Update", user, parent, transaction: false);
        Assert.Equal("LIFECYCLE_BYPASS", Assert.Throws<InvalidPluginExecutionException>(() => new LifecycleGuard().Execute(provider)).Message);
    }
}
