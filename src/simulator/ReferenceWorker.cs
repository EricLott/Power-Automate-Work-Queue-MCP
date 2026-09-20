using Newtonsoft.Json.Linq;
namespace QueueFramework.Simulator;
public sealed class ReferenceWorker
{
    readonly IStore store; readonly Engine engine; readonly Actor actor; readonly Func<JObject, JObject> extract;
    public ReferenceWorker(IStore store, Engine engine, Actor actor, Func<JObject, JObject> extract) { this.store = store; this.engine = engine; this.actor = actor; this.extract = extract; }
    public JObject Process(string queue, Action<string>? inject = null)
    {
        var acquired = JObject.Parse(engine.Execute(new Command { Operation = "AcquireNext", QueueKey = queue, RequestId = Guid.NewGuid().ToString() }, actor));
        if ((string?)acquired["Outcome"] != "Acquired") return acquired;
        string itemId = (string)acquired["ItemId"]!, source = (string)acquired["SourceKey"]!, hash = (string)acquired["ContentHash"]!;
        string recordId = StableGuid(queue + "|" + source);
        JObject result;
        try
        {
            var existing = store.Atomic(() => store.Get("business", recordId));
            if (existing != null) { result = Json.Object(existing.Body); if ((string?)result["contentHash"] != hash) throw new Fault("KEY_CONTENT_CONFLICT"); }
            else
            {
                var fields = extract((JObject)acquired["Envelope"]!["payload"]!);
                if (fields.Properties().Any(p => !new[] { "contact", "category", "summary" }.Contains(p.Name)) || fields["contact"]?.Type != JTokenType.String || string.IsNullOrWhiteSpace((string?)fields["contact"]) ||
                   !new[] { "service", "question" }.Contains((string?)fields["category"]) || fields["summary"]?.Type != JTokenType.String) throw new Fault("BUSINESS_VALIDATION_FAILED");
                inject?.Invoke("before-write");
                result = store.Atomic(() =>
                {
                    var duplicate = store.Get("business", recordId);
                    if (duplicate != null) { var old = Json.Object(duplicate.Body); if ((string?)old["contentHash"] != hash) throw new Fault("KEY_CONTENT_CONFLICT"); return old; }
                    var native = store.NativeGet(itemId)!; var context = Json.Read<ItemContext>(store.Get("itemcontext", native.UniqueKey)!.Body);
                    var record = new JObject { ["sourceKey"] = source, ["contentHash"] = hash, ["testRun"] = context.TestRun, ["fields"] = fields, ["promptVersion"] = "fixture-v1" };
                    store.Add(new Row { Kind = "business", Key = recordId, Queue = queue, Body = Json.Write(record), Updated = DateTime.UtcNow }); return record;
                });
            }
        }
        catch (Fault f)
        {
            var failure = new Command { Operation = "Fail", QueueKey = queue, RequestId = Guid.NewGuid().ToString(), ItemId = itemId, AttemptId = (string)acquired["AttemptId"]!, Generation = (int)acquired["Generation"]!, DataJson = Json.Write(new { category = "Business", code = f.Code, effect = "None" }) };
            return JObject.Parse(engine.Execute(failure, actor));
        }
        // Intentional failure point: external business write has committed, framework completion has not.
        inject?.Invoke("after-write");
        var complete = new Command { Operation = "Complete", QueueKey = queue, RequestId = Guid.NewGuid().ToString(), ItemId = itemId, AttemptId = (string)acquired["AttemptId"]!, Generation = (int)acquired["Generation"]!, DataJson = Json.Write(new { table = "qmcp_emailrequest", recordId, promptVersion = (string?)result["promptVersion"] }) };
        var completed = JObject.Parse(engine.Execute(complete, actor));
        // The completion write is durable before a caller can lose its response.
        // This hook lets the local harness model that boundary without replaying
        // the business action or pretending it is an installed-flow outage.
        inject?.Invoke("after-complete");
        return completed;
    }
    public static string StableGuid(string value) => new Guid(Json.Hash(value).Substring(0, 32)).ToString();
}
