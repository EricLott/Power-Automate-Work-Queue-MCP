using Newtonsoft.Json.Linq;

namespace QueueFramework;

public sealed partial class Engine
{
    // WQTesting-only fixture creation. Production actors, customer queues, and
    // direct companion-table writes remain ineligible for this operation.
    object SeedRetentionFixture(Command c, Actor actor, JObject data, QueuePolicy policy)
    {
        if (actor.Production) throw new Fault("PRODUCTION_TEST_DENIED");
        if (!c.QueueKey.StartsWith("qmcp-proof-", StringComparison.Ordinal)) throw new Fault("SYNTHETIC_QUEUE_REQUIRED");
        var fixtureId = Required(data, "fixtureId", 80);
        var phase = (string?)data["phase"] ?? "seed";
        if (phase != "seed" || data["ageDays"]?.Type != JTokenType.Integer || (int)data["ageDays"]! < 1 || (int)data["ageDays"]! > 3650) throw new Fault("INPUT_INVALID");
        var created = clock().AddDays(-(int)data["ageDays"]!);
        NativeItem redaction;
        NativeItem protectedItem;
        try
        {
            redaction = SeedRetentionItem(c, policy, fixtureId, created, "Processed", false);
            protectedItem = SeedRetentionItem(c, policy, fixtureId + "-protected", created, "Exception", true);
        }
        catch (Fault) { throw; }
        catch (Exception) { throw new Fault("FIXTURE_NATIVE_OR_CONTEXT_WRITE"); }

        var receiptKey = Json.Hash(c.QueueKey + "|retention-receipt|" + fixtureId);
        try
        {
            AddAt("command", receiptKey, c.QueueKey, new Receipt
            {
                ActorId = actor.Id, Operation = "Enqueue", Created = created,
                Fingerprint = Json.Hash("retention-fixture|" + fixtureId),
                Result = Json.Write(new { Outcome = "Processed", ItemId = redaction.Id })
            }, created);
        }
        catch (Fault) { throw; }
        catch (Exception) { throw new Fault("FIXTURE_RECEIPT_WRITE"); }

        var runId = Json.Hash("retention-fixture|run|" + fixtureId);
        var caseId = "retention-fixture";
        var testCase = new TestCase { Id = caseId, Input = JObject.Parse(redaction.Input), ExpectedOutcome = "Processed" };
        var testResult = new TestResult { Id = Json.Hash(runId + "|result"), CaseId = caseId, ItemId = redaction.Id, State = "Passed" };
        var testRun = new TestRun { Id = runId, RequestedBy = actor.Id, Deadline = created.AddMinutes(15), State = "Passed", ManifestHash = Json.Hash(fixtureId), Results = new List<TestResult> { testResult } };
        try
        {
            AddAt("testcase", Json.Hash(runId + "|" + caseId), c.QueueKey, testCase, created);
            AddAt("testresult", testResult.Id, c.QueueKey, testResult, created);
            AddAt("testrun", runId, c.QueueKey, testRun, created);
        }
        catch (Fault) { throw; }
        catch (Exception) { throw new Fault("FIXTURE_EVIDENCE_WRITE"); }

        return new { Outcome = "RetentionFixtureSeeded", FixtureId = fixtureId, CreatedOn = created, RedactionItemId = redaction.Id, ProtectedItemId = protectedItem.Id, ReceiptKey = receiptKey, TestRunId = runId };
    }

    NativeItem SeedRetentionItem(Command c, QueuePolicy policy, string fixtureId, DateTime created, string status, bool reviewRequired)
    {
        var source = "retention-source|" + fixtureId;
        var envelope = new JObject
        {
            ["envelopeVersion"] = "1.0", ["contract"] = "mail.v1",
            ["correlationId"] = Json.Hash("retention-correlation|" + fixtureId), ["deduplicationKey"] = source,
            ["source"] = new JObject { ["kind"] = "synthetic" },
            ["payload"] = new JObject { ["subject"] = "Synthetic retention fixture", ["senderAddress"] = "synthetic@example.invalid", ["bodyText"] = "Synthetic retention fixture only." }
        };
        ValidateEnvelope(c.QueueKey, envelope, policy);
        var key = Json.Hash(c.QueueKey + "|" + source);
        NativeItem native;
        try { native = store.NativeCreate(new NativeItem { Id = Guid.NewGuid().ToString(), Queue = c.QueueKey, UniqueKey = key, Input = envelope.ToString(Newtonsoft.Json.Formatting.None), Created = created, Available = clock(), Expires = clock().AddDays(7) }); }
        catch (Fault) { throw; }
        catch (Exception) { throw new Fault("FIXTURE_NATIVE_CREATE"); }
        try
        {
            AddAt("itemcontext", key, c.QueueKey, new ItemContext { ItemId = native.Id, SourceKey = Json.Hash(source), ContentHash = Json.Fingerprint(new { contract = envelope["contract"], source = envelope["source"], payload = envelope["payload"] }), CorrelationId = (string)envelope["correlationId"]!, ReviewRequired = false }, created);
        }
        catch (Fault) { throw; }
        catch (Exception) { throw new Fault("FIXTURE_CONTEXT_WRITE"); }
        return native;
    }
}
