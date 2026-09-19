using QueueFramework;
using Xunit;

namespace QueueFramework.Tests;

public class RetentionPolicyTests
{
    [Fact]
    public void RetentionUsesIndependentPayloadAndReceiptWindows()
    {
        var f = new Fixture();
        var request = f.Cmd("Enqueue", f.Envelope());
        var itemId = (string)f.Run(request)["ItemId"]!;
        f.Worker().Process("mail");

        var policy = f.Policy();
        policy.Retention.PayloadDays = 7;
        policy.Retention.ReceiptDays = 14;
        f.Run(f.Cmd("RegisterQueue", policy, version: 1));

        f.Now = f.Now.AddDays(8);
        var first = f.Run(f.Cmd("ApplyRetention"));
        Assert.Equal(7, (int)first["Retention"]!["PayloadDays"]!);
        Assert.Equal("{}", f.Store.NativeGet(itemId)!.Input);
        Assert.Equal("Enqueued", (string)f.Run(request)["Outcome"]!);

        f.Now = f.Now.AddDays(7);
        f.Run(f.Cmd("ApplyRetention"));
        Assert.Equal("ReplayExpired", (string)f.Run(request)["Outcome"]!);
    }

    [Fact]
    public void InvalidRetentionWindowFailsClosed()
    {
        var f = new Fixture();
        var policy = f.Policy();
        policy.Retention.PayloadDays = 0;
        Assert.Equal("POLICY_INVALID", Assert.Throws<Fault>(() => f.Run(f.Cmd("RegisterQueue", policy, version: 1))).Code);
    }
}
