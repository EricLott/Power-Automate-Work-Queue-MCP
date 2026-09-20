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

    [Fact]
    public void TestEvidenceSupportsBoundedRecordCountAndNoExtraBusinessRecord()
    {
        var f = new Fixture();
        var started = f.Run(f.Cmd("StartTestRun", new
        {
            cases = new[] { new TestCase
            {
                Id = "bounded-output",
                Input = f.Envelope(),
                ExpectedRecordCount = 1,
                ExpectedUnwantedEffectCount = 0
            } }
        }));
        var runId = (string)started["RunId"]!;
        f.Worker().Process("mail");

        var passed = f.Run(f.Cmd("AdvanceTestRun", item: runId));
        Assert.Equal("Passed", (string)passed["State"]!);
        var result = (JObject)passed["Results"]!.Single()!;
        Assert.Equal(1, (int)result["Evidence"]!["recordCount"]!);
        Assert.Equal(0, (int)result["Evidence"]!["unwantedEffectCount"]!);
        Assert.True((bool)result["Evidence"]!["recordCountBounded"]!);

        var extra = f.Store.Page("business", "mail", "", 100).Single();
        var extraBody = Json.Object(extra.Body);
        f.Store.Add(new QueueFramework.Row
        {
            Kind = "business",
            Key = Guid.NewGuid().ToString(),
            Queue = "mail",
            Body = Json.Write(extraBody)
        });

        // The run is terminal after the first advance, so use a fresh run to
        // prove the same fixed evidence query fails closed on an extra record.
        var second = f.Run(f.Cmd("StartTestRun", new
        {
            cases = new[] { new TestCase
            {
                Id = "bounded-output-with-extra",
                Input = f.Envelope("second"),
                ExpectedRecordCount = 1,
                ExpectedUnwantedEffectCount = 0
            } }
        }));
        var secondRunId = (string)second["RunId"]!;
        var secondItem = f.Store.Page("itemcontext", "mail", "", 100).Select(row => Json.Read<ItemContext>(row.Body)).Single(context => context.TestRun == secondRunId);
        var secondBusiness = new JObject
        {
            ["sourceKey"] = secondItem.SourceKey,
            ["contentHash"] = "synthetic-extra",
            ["testRun"] = secondRunId,
            ["fields"] = new JObject { ["contact"] = "extra@example.com", ["category"] = "service", ["summary"] = "extra" }
        };
        f.Store.Add(new QueueFramework.Row { Kind = "business", Key = Guid.NewGuid().ToString(), Queue = "mail", Body = Json.Write(secondBusiness) });
        f.Worker().Process("mail");

        // The worker's real output plus the injected same-case record must be
        // visible as two records, with one unwanted effect.
        var failed = f.Run(f.Cmd("AdvanceTestRun", item: secondRunId));
        Assert.Equal("Failed", (string)failed["State"]!);
        var failedResult = (JObject)failed["Results"]!.Single()!;
        Assert.Equal(2, (int)failedResult["Evidence"]!["recordCount"]!);
        Assert.Equal(1, (int)failedResult["Evidence"]!["unwantedEffectCount"]!);
    }

    [Fact]
    public void TestEvidenceRecordAssertionsHaveAClosedBound()
    {
        var f = new Fixture();
        var command = f.Cmd("StartTestRun", new
        {
            cases = new[] { new TestCase { Id = "too-wide", Input = f.Envelope(), ExpectedRecordCount = 51 } }
        });
        Assert.Equal("ASSERTION_UNSUPPORTED", Assert.Throws<Fault>(() => f.Run(command)).Code);
        Assert.Empty(f.Store.Page("testrun", "mail", "", 100));
    }
}
