using Newtonsoft.Json.Linq;
namespace QueueFramework;
public sealed class TestCase
{
    public string Id { get; set; } = "";
    public JObject Input { get; set; } = new JObject();
    public JObject Expected { get; set; } = new JObject();
    public string ExpectedOutcome { get; set; } = "Processed";
    public int Repetitions { get; set; } = 1;
    public string ExpectedErrorCode { get; set; } = "";
    public int? ExpectedAttemptCount { get; set; }
    public string ExpectedNotificationKind { get; set; } = "";
    public string ExpectedNotificationState { get; set; } = "";
}
public sealed class TestRun
{
    public string Id { get; set; } = "";
    public string RequestedBy { get; set; } = "";
    public DateTime Deadline { get; set; }
    public string State { get; set; } = "Running";
    public string ManifestHash { get; set; } = "";
    public List<TestResult> Results { get; set; } = new List<TestResult>();
}
public sealed class TestResult
{
    public string Id { get; set; } = "";
    public string CaseId { get; set; } = "";
    public string ItemId { get; set; } = "";
    public JObject Expected { get; set; } = new JObject();
    public string ExpectedOutcome { get; set; } = "Processed";
    public string State { get; set; } = "Pending";
    public JObject Evidence { get; set; } = new JObject();
    public string Cleanup { get; set; } = "NotRequested";
    public string ExpectedErrorCode { get; set; } = "";
    public int? ExpectedAttemptCount { get; set; }
    public string ExpectedNotificationKind { get; set; } = "";
    public string ExpectedNotificationState { get; set; } = "";
}
public sealed partial class Engine
{
    object StartTest(Command c, Actor actor, JObject d)
    {
        if (actor.Production) throw new Fault("PRODUCTION_TEST_DENIED");
        if (d["cases"] == null) throw new Fault("INPUT_INVALID");
        TestCase[] cases;
        try { cases = Json.ToObject<TestCase[]>(d["cases"]!); }
        catch (Fault) { throw new Fault("INPUT_INVALID"); }
        if (cases.Any(x => x == null || x.Id == null || x.Input == null || x.Expected == null)) throw new Fault("INPUT_INVALID");
        if (cases.Length < 1 || cases.Length > 20 || cases.Any(x => x.Repetitions < 1 || x.Repetitions > 10) || cases.Sum(x => x.Repetitions) > 50 || cases.Select(x => x.Id).Distinct().Count() != cases.Length) throw new Fault("TEST_LIMIT");
        foreach (var test in cases)
        {
            if (test.Id.Length < 1 || test.Id.Length > 100 || !new[] { "Processed", "Exception" }.Contains(test.ExpectedOutcome) ||
               test.Expected.Properties().Any(p => !new[] { "contact", "category", "summary" }.Contains(p.Name))) throw new Fault("ASSERTION_UNSUPPORTED");
        }
        var run = new TestRun { Id = Guid.NewGuid().ToString(), RequestedBy = actor.Id, Deadline = clock().AddMinutes(15), ManifestHash = Json.Fingerprint(cases) };
        var policy = Get<QueuePolicy>("definition", c.QueueKey)!;
        foreach (var test in cases)
        {
            Add("testcase", Json.Hash(run.Id + "|" + test.Id), c.QueueKey, test);
            for (int repetition = 0; repetition < test.Repetitions; repetition++)
            {
                var input = (JObject)test.Input.DeepClone();
                input["deduplicationKey"] = Json.Hash(run.Id + "|" + test.Id + "|" + repetition);
                var result = JObject.FromObject(Enqueue(c, input, policy));
                string itemId = (string)result["ItemId"]!;
                var item = Item(new Command { QueueKey = c.QueueKey, ItemId = itemId });
                item.context.TestRun = run.Id; Save("itemcontext", item.native.UniqueKey, item.context);
                var record = new TestResult { Id = Json.Hash(run.Id + "|" + test.Id + "|" + repetition), CaseId = test.Id, ItemId = itemId, Expected = (JObject)test.Expected.DeepClone(), ExpectedOutcome = test.ExpectedOutcome, ExpectedErrorCode = test.ExpectedErrorCode, ExpectedAttemptCount = test.ExpectedAttemptCount, ExpectedNotificationKind = test.ExpectedNotificationKind, ExpectedNotificationState = test.ExpectedNotificationState };
                run.Results.Add(record); Add("testresult", record.Id, c.QueueKey, record);
            }
        }
        Add("testrun", run.Id, c.QueueKey, run);
        return new { Outcome = "Started", RunId = run.Id, run.ManifestHash };
    }
    TestRun Run(Command c)
    {
        var row = store.Get("testrun", c.ItemId) ?? throw new Fault("NOT_FOUND");
        if (row.Queue != c.QueueKey) throw new Fault("FORBIDDEN");
        return Json.Read<TestRun>(row.Body);
    }
    object GetTest(Command c) => Run(c);
    object AdvanceTest(Command c)
    {
        var run = Run(c); if (run.State != "Running") return run;
        foreach (var result in run.Results.Where(r => r.State == "Pending"))
        {
            var item = Item(new Command { QueueKey = c.QueueKey, ItemId = result.ItemId });
            if (item.native.Status == "Processing" || item.native.Status == "Queued") { if (clock() >= run.Deadline) result.State = "Inconclusive"; else continue; }
            else
            {
                result.Evidence = new JObject { ["nativeOutcome"] = item.native.Status, ["attemptCount"] = item.context.AttemptCount, ["reviewRequired"] = item.context.ReviewRequired };
                if (item.native.Status != result.ExpectedOutcome) result.State = "Failed";
                else if (item.native.Status == "Exception") result.State = "Passed";
                else
                {
                    var output = Json.Object(item.context.OutputJson);
                    string recordId = (string?)output["recordId"] ?? "";
                    var actual = store.Get("business", recordId);
                    if (actual == null) result.State = "Inconclusive";
                    else
                    {
                        var record = Json.Object(actual.Body);
                        if ((string?)record["testRun"] != run.Id || (string?)record["sourceKey"] != item.context.SourceKey) result.State = "Failed";
                        else
                        {
                            var fields = record["fields"] as JObject ?? new JObject();
                            result.Evidence["recordId"] = recordId; result.Evidence["fields"] = fields.DeepClone();
                            result.State = result.Expected.Properties().All(p => JToken.DeepEquals(p.Value, fields[p.Name])) ? "Passed" : "Failed";
                        }
                    }
                }
            }
            if (result.State == "Passed")
            {
                var attempt = Get<Attempt>("attempt", item.context.LastAttempt);
                if (attempt == null) result.State = "Inconclusive";
                else
                {
                    result.Evidence["errorCode"] = attempt.ErrorCode;
                    if (result.ExpectedErrorCode != "" && result.ExpectedErrorCode != attempt.ErrorCode) result.State = "Failed";
                    if (result.ExpectedAttemptCount.HasValue && result.ExpectedAttemptCount.Value != item.context.AttemptCount) result.State = "Failed";
                    if (result.ExpectedNotificationKind != "")
                    {
                        var policy = attempt.Policy; var found = new List<Delivery>();
                        foreach (var destination in policy.Destinations)
                        {
                            var key = Json.Hash(c.QueueKey + "|" + result.ItemId + "|" + attempt.Id + "|" + result.ExpectedNotificationKind + "|" + destination);
                            var delivery = Get<Delivery>("event", key); if (delivery != null) found.Add(delivery);
                        }
                        result.Evidence["notifications"] = JArray.FromObject(found.Select(e => new { e.Id, e.State, e.Kind }));
                        if (found.Count == 0) result.State = "Failed";
                        else if (result.ExpectedNotificationState != "" && found.Any(e => e.State != result.ExpectedNotificationState))
                        {
                            if (found.Any(e => e.State == "Pending" || e.State == "Sending") && clock() < run.Deadline) result.State = "Pending";
                            else result.State = "Failed";
                        }
                    }
                }
            }
            Save("testresult", result.Id, result);
        }
        if (run.Results.All(r => r.State != "Pending")) run.State = run.Results.Any(r => r.State == "Failed") ? "Failed" : run.Results.Any(r => r.State == "Inconclusive") ? "Inconclusive" : "Passed";
        Save("testrun", run.Id, run); return run;
    }
    object CleanupTest(Command c)
    {
        var run = Run(c);
        if (run.State != "Passed") throw new Fault("EVIDENCE_RETENTION_HOLD");
        foreach (var result in run.Results)
        {
            var item = Item(new Command { QueueKey = c.QueueKey, ItemId = result.ItemId });
            if (item.context.ActiveAttempt != "") throw new Fault("ATTEMPT_ACTIVE");
            string recordId = (string?)result.Evidence["recordId"] ?? "";
            if (recordId != "")
            {
                var record = store.Get("business", recordId);
                if (record != null)
                {
                    if ((string?)Json.Object(record.Body)["testRun"] != run.Id) throw new Fault("CLEANUP_FORBIDDEN");
                    store.Delete("business", recordId, record.Version);
                }
            }
            result.Cleanup = "Completed"; Save("testresult", result.Id, result);
        }
        Save("testrun", run.Id, run); return run;
    }
}
