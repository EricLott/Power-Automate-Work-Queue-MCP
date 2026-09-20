using Newtonsoft.Json.Linq;
using QueueFramework;
using Xunit;

namespace QueueFramework.Tests;

public sealed class TestingBoundaryTests
{
    [Fact]
    public void TestEvidenceRequiresTesterRoleAndStaysQueueScoped()
    {
        var f = new Fixture();
        var started = f.Run(f.Cmd("StartTestRun", new { cases = new[] { new TestCase { Id = "scope", Input = f.Envelope() } } }));
        var runId = (string)started["RunId"]!;
        var reader = new Actor { Id = "reader", Roles = new() { "reader" } };
        Assert.Equal("FORBIDDEN", Assert.Throws<Fault>(() => f.Run(f.Cmd("GetTestRun", item: runId), reader)).Code);

        var other = f.Policy();
        other.NativeQueueId = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
        var register = f.Cmd("RegisterQueue", other); register.QueueKey = "other";
        f.Run(register);
        var wrongQueue = f.Cmd("GetTestRun", item: runId); wrongQueue.QueueKey = "other";
        Assert.Equal("FORBIDDEN", Assert.Throws<Fault>(() => f.Run(wrongQueue)).Code);
    }

    [Theory]
    [InlineData("url")]
    [InlineData("fetchXml")]
    [InlineData("query")]
    public void TestAssertionsRejectUnboundedQueryShapes(string property)
    {
        var f = new Fixture();
        var expected = new JObject { [property] = "https://example.invalid/unsafe" };
        var command = f.Cmd("StartTestRun", new { cases = new[] { new TestCase { Id = property, Input = f.Envelope(), Expected = expected } } });
        Assert.Equal("ASSERTION_UNSUPPORTED", Assert.Throws<Fault>(() => f.Run(command)).Code);
        Assert.Empty(f.Store.Page("testrun", "mail", "", 100));
        Assert.Empty(f.Store.NativePage("mail", "", 100));
    }
}
