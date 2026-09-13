using Newtonsoft.Json.Linq;
using QueueFramework;
using Xunit;

namespace QueueFramework.Tests;

public class CancellationTests
{
    static JObject Start(Fixture f, string id = "cancel") => f.Run(f.Cmd("StartTestRun", new { cases = new[] { new TestCase { Id = id, Input = f.Envelope(id) } } }));

    [Fact]
    public void CancellationBeforeAcquisitionHoldsQueuedFixtures()
    {
        var f = new Fixture();
        var run = Start(f);
        var cancel = f.Cmd("CancelTestRun", item: (string)run["RunId"]!);
        var result = f.Run(cancel);

        Assert.Equal("Cancelled", (string)result["State"]!);
        Assert.All((JArray)result["Results"]!, r => Assert.Equal("Cancelled", (string)r["State"]!));
        Assert.All(f.Store.NativePage("mail", "", 100), item => Assert.Equal("OnHold", item.Status));
        Assert.Equal("NoWork", (string)f.Acquire()["Outcome"]!);
    }

    [Fact]
    public void RetentionRedactsExpiredCancelledOnHoldInputButPreservesIdentity()
    {
        var f = new Fixture(); var run = Start(f); var item = f.Store.NativePage("mail", "", 100).Single();
        f.Run(f.Cmd("CancelTestRun", item: (string)run["RunId"]!)); f.Now = f.Now.AddDays(31);
        f.Run(f.Cmd("ApplyRetention"));
        Assert.Equal("{}", f.Store.NativeGet(item.Id)!.Input);
        Assert.Equal(item.UniqueKey, f.Store.NativeGet(item.Id)!.UniqueKey);
        var savedRun = Json.Read<TestRun>(f.Store.Get("testrun", (string)run["RunId"]!)!.Body);
        Assert.Equal("Cancelled", savedRun.State);
        Assert.Equal("Cancelled", savedRun.Results.Single().State);
    }

    [Fact]
    public void RetentionPreservesRecentAndReviewHeldCancelledInputs()
    {
        var f = new Fixture(); var run = Start(f); var item = f.Store.NativePage("mail", "", 100).Single();
        f.Run(f.Cmd("CancelTestRun", item: (string)run["RunId"]!)); f.Run(f.Cmd("ApplyRetention"));
        Assert.NotEqual("{}", f.Store.NativeGet(item.Id)!.Input);
        var row = f.Store.Get("itemcontext", item.UniqueKey)!; var context = Json.Read<ItemContext>(row.Body); context.ReviewRequired = true; row.Body = Json.Write(context); f.Store.Put(row, row.Version);
        f.Now = f.Now.AddDays(31); f.Run(f.Cmd("ApplyRetention"));
        Assert.NotEqual("{}", f.Store.NativeGet(item.Id)!.Input);
    }

    [Fact]
    public void RetentionPreservesExpiredCancelledInputWithActiveAttempt()
    {
        var f = new Fixture(); var run = Start(f); var acquired = f.Acquire(); var item = f.Store.NativeGet((string)acquired["ItemId"]!)!;
        f.Run(f.Cmd("CancelTestRun", item: (string)run["RunId"]!)); f.Now = f.Now.AddDays(31);
        f.Run(f.Cmd("ApplyRetention"));
        Assert.NotEqual("{}", f.Store.NativeGet(item.Id)!.Input);
        Assert.Equal("Processing", f.Store.NativeGet(item.Id)!.Status);
    }

    [Fact]
    public void RetentionPreservesOrdinaryExpiredOnHoldInput()
    {
        var f = new Fixture(); var id = f.Enqueue(); var item = f.Store.NativeGet(id)!;
        item.Status = "OnHold"; f.Store.NativeSet(item); f.Now = f.Now.AddDays(31);
        f.Run(f.Cmd("ApplyRetention"));
        Assert.NotEqual("{}", f.Store.NativeGet(id)!.Input);
    }

    [Fact]
    public void CancellationLeavesActiveAttemptForConservativeReconciliation()
    {
        var f = new Fixture();
        var run = Start(f);
        var acquired = f.Acquire();
        var itemId = (string)acquired["ItemId"]!;
        var attemptId = (string)acquired["AttemptId"]!;
        var cancel = f.Cmd("CancelTestRun", item: (string)run["RunId"]!);

        var result = f.Run(cancel);

        Assert.Equal("Cancelled", (string)result["State"]!);
        Assert.Equal("Processing", f.Store.NativeGet(itemId)!.Status);
        Assert.NotNull(f.Store.Get("attempt", attemptId));
        var context = Json.Read<ItemContext>(f.Store.Get("itemcontext", f.Store.NativeGet(itemId)!.UniqueKey)!.Body);
        Assert.Equal(attemptId, context.ActiveAttempt);
    }

    [Fact]
    public void CancellationIsRequestIdempotentAndRetainsEvidence()
    {
        var f = new Fixture();
        var run = Start(f);
        var cancel = f.Cmd("CancelTestRun", item: (string)run["RunId"]!);

        var first = f.Run(cancel);
        var replay = f.Run(cancel);

        Assert.Equal(first.ToString(), replay.ToString());
        Assert.Equal("EVIDENCE_RETENTION_HOLD", Assert.Throws<Fault>(() => f.Run(f.Cmd("CleanupTestRun", item: (string)run["RunId"]!))).Code);
        Assert.NotEmpty(f.Store.Page("testresult", "mail", "", 100));
    }

    [Fact]
    public void CancelledFixtureCannotBeOperatorRetried()
    {
        var f = new Fixture();
        var run = Start(f);
        var cancel = f.Cmd("CancelTestRun", item: (string)run["RunId"]!);
        f.Run(cancel);
        var item = f.Store.NativePage("mail", "", 100).Single();
        var status = f.Status(item.Id);

        var retry = f.Cmd("RequestRetry", new { reason = "reviewed", reconciliation = "VerifiedSafe" }, item.Id, version: (long)status["Version"]!);
        Assert.Equal("RETRY_UNSAFE", Assert.Throws<Fault>(() => f.Run(retry)).Code);
        Assert.Equal("OnHold", f.Store.NativeGet(item.Id)!.Status);
    }

    [Fact]
    public void CancelledActiveFailureCannotAutomaticallyRequeue()
    {
        var f = new Fixture();
        var run = Start(f);
        var acquired = f.Acquire();
        f.Run(f.Cmd("CancelTestRun", item: (string)run["RunId"]!));

        var failed = f.Run(f.Owned("Fail", acquired, new { category = "Technical", code = "TRANSIENT", effect = "None" }));

        Assert.Equal("ReviewRequired", (string)failed["Outcome"]!);
        Assert.Equal("Exception", f.Store.NativeGet((string)acquired["ItemId"]!)!.Status);
    }

    [Fact]
    public void StaleFailureCannotRequeueAfterCancellationMarkerCommits()
    {
        var f = new Fixture();
        var run = Start(f);
        var acquired = f.Acquire();
        var itemId = (string)acquired["ItemId"]!;
        var item = f.Store.NativeGet(itemId)!;
        var contextRow = f.Store.Get("itemcontext", item.UniqueKey)!;
        var injected = false;
        f.Store.BeforeWrite = op =>
        {
            if (op == "native:set" && !injected)
            {
                injected = true;
                var context = Json.Read<ItemContext>(contextRow.Body); context.TestCancelled = true;
                contextRow.Body = Json.Write(context);
                f.Store.Put(contextRow, contextRow.Version);
            }
        };

        Assert.Equal("VERSION_CONFLICT", Assert.Throws<Fault>(() => f.Run(f.Owned("Fail", acquired, new { category = "Technical", code = "TRANSIENT", effect = "None" }))).Code);
        Assert.True(injected);
        Assert.Equal("Processing", f.Store.NativeGet(itemId)!.Status);
    }

    [Fact]
    public void CancelledActiveCompletionPreservesCancellationMarker()
    {
        var f = new Fixture();
        var run = Start(f);
        var acquired = f.Acquire();
        f.Run(f.Cmd("CancelTestRun", item: (string)run["RunId"]!));

        f.Run(f.Owned("Complete", acquired, new { table = "qmcp_emailrequest", recordId = Guid.NewGuid().ToString() }));

        var native = f.Store.NativeGet((string)acquired["ItemId"]!)!;
        var context = Json.Read<ItemContext>(f.Store.Get("itemcontext", native.UniqueKey)!.Body);
        Assert.Equal("Processed", native.Status);
        Assert.True(context.TestCancelled);
    }

    [Fact]
    public void CancellingTerminalRunIsAReceiptBackedNoOp()
    {
        var f = new Fixture();
        var run = Start(f);
        var cancel = f.Cmd("CancelTestRun", item: (string)run["RunId"]!);
        var first = f.Run(cancel);
        var second = f.Cmd("CancelTestRun", item: (string)run["RunId"]!);

        Assert.Equal(first.ToString(), f.Run(second).ToString());
        Assert.Equal("Cancelled", (string)f.Run(f.Cmd("GetTestRun", item: (string)run["RunId"]!))["State"]!);
    }

    [Fact]
    public void CancellationCasRejectsCompetingAcquisitionContextUpdate()
    {
        var f = new Fixture();
        var run = Start(f);
        var native = f.Store.NativePage("mail", "", 100).Single();
        var raced = false;
        f.Store.BeforeWrite = op =>
        {
            if (op == "put:itemcontext" && !raced)
            {
                raced = true;
                var current = f.Store.Get("itemcontext", native.UniqueKey)!;
                var context = Json.Read<ItemContext>(current.Body); context.ActiveAttempt = "concurrent-acquisition";
                current.Body = Json.Write(context); f.Store.Put(current, current.Version);
            }
        };

        Assert.Equal("VERSION_CONFLICT", Assert.Throws<Fault>(() => f.Run(f.Cmd("CancelTestRun", item: (string)run["RunId"]!))).Code);
        Assert.True(raced);
        Assert.Equal("Queued", f.Store.NativeGet(native.Id)!.Status);
        Assert.False(Json.Read<ItemContext>(f.Store.Get("itemcontext", native.UniqueKey)!.Body).TestCancelled);
    }

    [Fact]
    public void AdvanceCasRejectsCompetingCancellationWithoutOverwritingResult()
    {
        var f = new Fixture();
        var run = Start(f);
        var runId = (string)run["RunId"]!;
        var raced = false;
        f.Store.BeforeWrite = op =>
        {
            if (op == "put:testrun" && !raced)
            {
                raced = true;
                var current = f.Store.Get("testrun", runId)!;
                var body = Json.Read<TestRun>(current.Body); body.State = "Cancelled";
                current.Body = Json.Write(body); f.Store.Put(current, current.Version);
            }
        };

        Assert.Equal("VERSION_CONFLICT", Assert.Throws<Fault>(() => f.Run(f.Cmd("AdvanceTestRun", item: runId))).Code);
        Assert.True(raced);
        var persisted = Json.Read<TestRun>(f.Store.Get("testrun", runId)!.Body);
        Assert.Equal("Running", persisted.State);
        Assert.All(persisted.Results, result => Assert.Equal("Pending", result.State));
    }

    [Fact]
    public void CancellationRequiresTesterRoleAndSameQueue()
    {
        var f = new Fixture();
        var run = Start(f);
        var runId = (string)run["RunId"]!;
        var producer = new Actor { Id = "producer", Roles = new() { "producer" } };
        Assert.Equal("FORBIDDEN", Assert.Throws<Fault>(() => f.Run(f.Cmd("CancelTestRun", item: runId), producer)).Code);

        var otherPolicy = f.Policy();
        otherPolicy.NativeQueueId = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
        otherPolicy.Grants["tester"] = new[] { "tester" };
        var register = f.Cmd("RegisterQueue", otherPolicy); register.QueueKey = "other";
        f.Run(register);
        var wrongQueue = f.Cmd("CancelTestRun", item: runId); wrongQueue.QueueKey = "other";
        var tester = new Actor { Id = "tester", Roles = new() { "tester" } };
        Assert.Equal("FORBIDDEN", Assert.Throws<Fault>(() => f.Run(wrongQueue, tester)).Code);
    }
}
