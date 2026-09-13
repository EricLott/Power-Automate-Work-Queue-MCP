using Newtonsoft.Json.Linq;
using QueueFramework;
using Xunit;

namespace QueueFramework.Tests;

public class StatusReadTests
{
    [Fact]
    public void ReaderStatusRedactsNestedAndSensitiveOutput()
    {
        var f = new Fixture(); var id = f.Enqueue(); var acquired = f.Acquire();
        var record = Guid.NewGuid().ToString();
        f.Run(f.Owned("Complete", acquired, new { table = "qmcp_emailrequest", recordId = record, secret = "sentinel", nested = new { token = "hidden" } }));
        var actor = new Actor { Id = "reader", Roles = new() { "reader" } };
        var status = f.Run(f.Cmd("GetItemStatus", item: id), actor);
        Assert.Equal(record, (string?)status["Output"]?["recordId"]);
        Assert.Null(status["Output"]?["secret"]);
        Assert.Null(status["Output"]?["nested"]);
        var native = f.Store.NativeGet(id)!;
        var persisted = Json.Read<ItemContext>(f.Store.Get("itemcontext", native.UniqueKey)!.Body);
        Assert.Equal("sentinel", (string?)Json.Object(persisted.OutputJson)["secret"]);
        Assert.Equal("hidden", (string?)Json.Object(persisted.OutputJson)["nested"]?["token"]);
        Assert.Equal((string)acquired["AttemptId"]!, (string)status["LastAttempt"]!);
        Assert.Equal("", (string)status["ActiveAttempt"]!);
    }

    [Fact]
    public void StatusReadIsQueueScopedAndNativeRunIsNotRequired()
    {
        var f = new Fixture(); var id = f.Enqueue();
        var actor = new Actor { Id = "reader", Roles = new() { "reader" } };
        var status = f.Run(f.Cmd("GetItemStatus", item: id), actor);
        Assert.Equal("Queued", (string)status["Outcome"]!);
        var otherPolicy = f.Policy(); otherPolicy.NativeQueueId = Guid.NewGuid().ToString();
        otherPolicy.Grants.Remove("reader");
        var register = f.Cmd("RegisterQueue", otherPolicy); register.QueueKey = "other"; f.Run(register);
        var wrongQueue = f.Cmd("GetItemStatus", item: id); wrongQueue.QueueKey = "other";
        Assert.Equal("FORBIDDEN", Assert.Throws<Fault>(() => f.Run(wrongQueue, actor)).Code);

    }
}
