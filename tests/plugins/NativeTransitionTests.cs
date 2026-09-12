using Microsoft.Xrm.Sdk;
using Moq;
using QueueFramework.Plugins;
using Xunit;
namespace QueueFramework.Tests;
public sealed class NativeTransitionTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void OnlyFutureQueueSchedulingSendsRequeuePayload(bool future)
    {
        Entity? sent = null;
        var service = new Mock<IOrganizationService>(MockBehavior.Strict);
        service.Setup(x => x.Update(It.IsAny<Entity>())).Callback<Entity>(e => sent = e);
        var available = DateTime.UtcNow.AddMinutes(future ? 5 : -5);
        new DataverseStore(service.Object, Mock.Of<IPluginExecutionContext>()).NativeSet(new NativeItem
        { Id = Guid.NewGuid().ToString(), Status = "Queued", Available = available });
        Assert.Equal(future, sent!.Contains("delayuntil"));
        if (future) Assert.Equal(available, sent.GetAttributeValue<DateTime>("delayuntil"));
    }
    [Theory]
    [InlineData("Processed", 2)]
    [InlineData("Exception", 4)]
    public void TerminalTransitionDoesNotInvokeRequeueValidation(string outcome, int state)
    {
        Entity? sent = null;
        var service = new Mock<IOrganizationService>(MockBehavior.Strict);
        service.Setup(x => x.Update(It.IsAny<Entity>())).Callback<Entity>(e => sent = e);
        new DataverseStore(service.Object, Mock.Of<IPluginExecutionContext>()).NativeSet(new NativeItem
        { Id = Guid.NewGuid().ToString(), Status = outcome, Available = DateTime.UtcNow.AddHours(-1) });
        Assert.NotNull(sent);
        Assert.Equal(state, sent!.GetAttributeValue<OptionSetValue>("statecode").Value);
        Assert.False(sent.Contains("delayuntil"));
    }
}
