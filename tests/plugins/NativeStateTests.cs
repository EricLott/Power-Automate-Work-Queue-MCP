using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Query;
using Moq;
using QueueFramework.Plugins;
using Xunit;

namespace QueueFramework.Tests;

public class NativeStateTests
{
    [Fact]
    public void NativeOnHoldMapsToDataversePausedState()
    {
        var id = Guid.NewGuid();
        var service = new Mock<IOrganizationService>(MockBehavior.Strict);
        service.Setup(s => s.Update(It.Is<Entity>(e => e.LogicalName == "workqueueitem" && e.Id == id &&
            e.GetAttributeValue<OptionSetValue>("statecode").Value == 3 &&
            e.GetAttributeValue<OptionSetValue>("statuscode").Value == 3)));

        new DataverseStore(service.Object, new Mock<IPluginExecutionContext>().Object).NativeSet(new NativeItem { Id = id.ToString(), Status = "OnHold" });

        service.Verify(s => s.Update(It.Is<Entity>(e => e.LogicalName == "workqueueitem" && e.Id == id &&
            e.GetAttributeValue<OptionSetValue>("statecode").Value == 3 &&
            e.GetAttributeValue<OptionSetValue>("statuscode").Value == 3)), Times.Once);
    }
}
