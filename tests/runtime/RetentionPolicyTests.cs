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

    [Fact]
    public void RetentionPurgesOldNonCurrentAttemptsAndErrors()
    {
        var f = new Fixture();
        var policy = f.Policy();
        policy.Destinations = Array.Empty<string>();
        policy.Retention.AttemptDays = 90;
        policy.Retention.ErrorDays = 30;
        f.Run(f.Cmd("RegisterQueue", policy, version: 1));

        var itemId = f.Enqueue();
        var first = f.Acquire();
        f.Run(f.Owned("Fail", first, new { category = "Technical", code = "TRANSIENT", effect = "None" }));
        f.Now = f.Now.AddSeconds(10);
        var second = f.Acquire();
        f.Run(f.Owned("Complete", second, new { table = "qmcp_emailrequest", recordId = Guid.NewGuid().ToString() }));

        var oldAttempt = f.Store.Get("attempt", (string)first["AttemptId"]!)!;
        oldAttempt.Updated = f.Now.AddDays(-91);
        f.Store.Put(oldAttempt, oldAttempt.Version);
        f.Run(f.Cmd("ReportIntakeFailure", new { source = "synthetic", correlationId = "old", code = "INVALID" }));
        var oldError = f.Store.Page("intakefailure", "mail", "", 50).Single();
        oldError.Updated = f.Now.AddDays(-31);
        f.Store.Put(oldError, oldError.Version);

        var result = f.Run(f.Cmd("ApplyRetention"));
        Assert.Equal(1, (int)result["AttemptsPurged"]!);
        Assert.Equal(1, (int)result["ErrorsPurged"]!);
        Assert.Null(f.Store.Get("attempt", oldAttempt.Key));
        Assert.Null(f.Store.Get("intakefailure", oldError.Key));
        Assert.NotNull(f.Store.Get("attempt", (string)second["AttemptId"]!));
        Assert.Equal("Processed", (string)f.Status(itemId)["Outcome"]!);
    }

    [Fact]
    public void RetentionPreservesAttemptsWithActiveDelivery()
    {
        var f = new Fixture();
        var itemId = f.Enqueue();
        var first = f.Acquire();
        f.Run(f.Owned("Fail", first, new { category = "Technical", code = "TRANSIENT", effect = "None" }));
        f.Now = f.Now.AddSeconds(10);
        var second = f.Acquire();
        f.Run(f.Owned("Complete", second, new { table = "qmcp_emailrequest", recordId = Guid.NewGuid().ToString() }));
        var oldAttempt = f.Store.Get("attempt", (string)first["AttemptId"]!)!;
        oldAttempt.Updated = f.Now.AddDays(-91);
        f.Store.Put(oldAttempt, oldAttempt.Version);

        var result = f.Run(f.Cmd("ApplyRetention"));
        Assert.Equal(0, (int)result["AttemptsPurged"]!);
        Assert.True((int)result["ProtectedRows"]! > 0);
        Assert.NotNull(f.Store.Get("attempt", oldAttempt.Key));
        Assert.Equal("Processed", (string)f.Status(itemId)["Outcome"]!);
    }

    [Fact]
    public void RetentionUsesHistoricalAttemptDestinationsAfterPolicyChange()
    {
        var f = new Fixture();
        var itemId = f.Enqueue();
        var first = f.Acquire();
        f.Run(f.Owned("Fail", first, new { category = "Technical", code = "TRANSIENT", effect = "None" }));
        f.Now = f.Now.AddSeconds(10);
        var second = f.Acquire();
        f.Run(f.Owned("Complete", second, new { table = "qmcp_emailrequest", recordId = Guid.NewGuid().ToString() }));

        var rotated = f.Policy();
        rotated.Destinations = new[] { "new-ops" };
        f.Run(f.Cmd("RegisterQueue", rotated, version: 1));

        var oldAttempt = f.Store.Get("attempt", (string)first["AttemptId"]!)!;
        oldAttempt.Updated = f.Now.AddDays(-91);
        f.Store.Put(oldAttempt, oldAttempt.Version);

        var result = f.Run(f.Cmd("ApplyRetention"));
        Assert.Equal(0, (int)result["AttemptsPurged"]!);
        Assert.NotNull(f.Store.Get("attempt", oldAttempt.Key));
        Assert.Equal("Processed", (string)f.Status(itemId)["Outcome"]!);
    }

    [Fact]
    public void RetentionPreservesLegacyErrorsWithoutDestinationSnapshot()
    {
        var f = new Fixture();
        var policy = f.Policy();
        policy.Destinations = Array.Empty<string>();
        policy.Retention.ErrorDays = 30;
        f.Run(f.Cmd("RegisterQueue", policy, version: 1));
        f.Run(f.Cmd("ReportIntakeFailure", new { source = "synthetic", correlationId = "legacy", code = "INVALID" }));
        var row = f.Store.Page("intakefailure", "mail", "", 50).Single();
        var body = Json.Object(row.Body);
        body.Remove("Destinations");
        row.Body = body.ToString(Newtonsoft.Json.Formatting.None);
        row.Updated = f.Now.AddDays(-31);
        f.Store.Put(row, row.Version);

        var result = f.Run(f.Cmd("ApplyRetention"));
        Assert.Equal(0, (int)result["ErrorsPurged"]!);
        Assert.True((int)result["ProtectedRows"]! > 0);
        Assert.NotNull(f.Store.Get("intakefailure", row.Key));
    }

    [Fact]
    public void RetentionPurgesTerminalEvidenceButPreservesRunningEvidence()
    {
        var f = new Fixture();
        var policy = f.Policy();
        policy.Destinations = Array.Empty<string>();
        policy.Retention.EvidenceDays = 30;
        f.Run(f.Cmd("RegisterQueue", policy, version: 1));

        var completedRun = (string)f.Run(f.Cmd("StartTestRun", new { cases = new[] { new TestCase { Id = "old", Input = f.Envelope() } } }))["RunId"]!;
        f.Worker().Process("mail");
        Assert.Equal("Passed", (string)f.Run(f.Cmd("AdvanceTestRun", item: completedRun))["State"]!);
        var completedRow = f.Store.Get("testrun", completedRun)!;
        completedRow.Updated = f.Now.AddDays(-31);
        f.Store.Put(completedRow, completedRow.Version);

        var runningRun = (string)f.Run(f.Cmd("StartTestRun", new { cases = new[] { new TestCase { Id = "current", Input = f.Envelope("current") } } }))["RunId"]!;
        var runningRow = f.Store.Get("testrun", runningRun)!;
        runningRow.Updated = f.Now.AddDays(-31);
        f.Store.Put(runningRow, runningRow.Version);

        var result = f.Run(f.Cmd("ApplyRetention"));
        Assert.Equal(3, (int)result["EvidenceRowsPurged"]!);
        Assert.Null(f.Store.Get("testrun", completedRun));
        Assert.NotNull(f.Store.Get("testrun", runningRun));
        Assert.Single(f.Store.Page("testresult", "mail", "", 100));
        Assert.Single(f.Store.Page("testcase", "mail", "", 100));
    }

    [Fact]
    public void RetentionPurgesCancelledQueuedEvidenceWithoutAnAttempt()
    {
        var f = new Fixture();
        var policy = f.Policy();
        policy.Destinations = Array.Empty<string>();
        policy.Retention.EvidenceDays = 30;
        f.Run(f.Cmd("RegisterQueue", policy, version: 1));

        var run = (string)f.Run(f.Cmd("StartTestRun", new { cases = new[] { new TestCase { Id = "cancelled", Input = f.Envelope("cancelled") } } }))!["RunId"]!;
        f.Run(f.Cmd("CancelTestRun", item: run));
        var row = f.Store.Get("testrun", run)!;
        row.Updated = f.Now.AddDays(-31);
        f.Store.Put(row, row.Version);

        var result = f.Run(f.Cmd("ApplyRetention"));
        Assert.Equal(3, (int)result["EvidenceRowsPurged"]!);
        Assert.Null(f.Store.Get("testrun", run));
        Assert.Empty(f.Store.Page("testresult", "mail", "", 100));
        Assert.Empty(f.Store.Page("testcase", "mail", "", 100));
    }
}
