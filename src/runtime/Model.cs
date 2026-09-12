using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using System.Security.Cryptography;
using System.Text;
namespace QueueFramework;

public sealed class Fault : Exception
{
    public string Code { get; }
    public Fault(string code) : base(code) { Code = code; }
}
public static class Json
{
    public static string Write(object value) => JsonConvert.SerializeObject(value, Formatting.None);
    public static T Read<T>(string value) => JsonConvert.DeserializeObject<T>(value) ?? throw new Fault("INPUT_INVALID");
    public static T ToObject<T>(JToken value)
    {
        try { return value.ToObject<T>() ?? throw new Fault("INPUT_INVALID"); }
        catch (JsonException) { throw new Fault("INPUT_INVALID"); }
    }
    public static string Hash(string value) { using var sha = SHA256.Create(); return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(value))).Replace("-", "").ToLowerInvariant(); }
    public static JToken Canonical(JToken value) => value is JObject o ? new JObject(o.Properties().OrderBy(p => p.Name, StringComparer.Ordinal).Select(p => new JProperty(p.Name, Canonical(p.Value)))) : value is JArray a ? new JArray(a.Select(Canonical)) : value.DeepClone();
    public static string Fingerprint(object value) => Hash(Canonical(JToken.FromObject(value)).ToString(Formatting.None));
    public static JObject Object(string text, int limit = 131072)
    {
        if (Encoding.UTF8.GetByteCount(text) > limit) throw new Fault("INPUT_TOO_LARGE");
        try
        {
            using var reader = new JsonTextReader(new StringReader(text)) { MaxDepth = 32, DateParseHandling = DateParseHandling.None };
            var token = JObject.Load(reader, new JsonLoadSettings { DuplicatePropertyNameHandling = DuplicatePropertyNameHandling.Error });
            if (reader.Read()) throw new Fault("INPUT_INVALID");
            if (token.Descendants().Count() > 8192) throw new Fault("INPUT_TOO_COMPLEX");
            return token;
        }
        catch (JsonException) { throw new Fault("INPUT_INVALID"); }
    }
}
public sealed class Command
{
    public string Operation { get; set; } = "";
    public string RequestId { get; set; } = "";
    public string QueueKey { get; set; } = "";
    public string ItemId { get; set; } = "";
    public string AttemptId { get; set; } = "";
    public int Generation { get; set; }
    public long ExpectedVersion { get; set; }
    public string DataJson { get; set; } = "{}";
}
public sealed class Actor
{
    public string Id { get; set; } = "";
    public HashSet<string> Roles { get; set; } = new HashSet<string>(StringComparer.Ordinal);
    public bool Production { get; set; }
    public bool Has(string role) => Roles.Contains("administrator") || Roles.Contains(role);
}
public sealed class Row
{
    public string Kind { get; set; } = "";
    public string Key { get; set; } = "";
    public string Queue { get; set; } = "";
    public string Body { get; set; } = "{}";
    public long Version { get; set; }
    public DateTime Updated { get; set; }
}
public sealed class NativeItem
{
    public string Id { get; set; } = "";
    public string Queue { get; set; } = "";
    public string UniqueKey { get; set; } = "";
    public string Input { get; set; } = "";
    public string Status { get; set; } = "Queued";
    public DateTime Created { get; set; }
    public DateTime Available { get; set; }
    public DateTime Expires { get; set; }
}
public interface IStore
{
    T Atomic<T>(Func<T> operation);
    Row? Get(string kind, string key);
    IReadOnlyList<Row> Page(string kind, string queue, string after, int limit);
    Row Add(Row row);
    Row Put(Row row, long expectedVersion);
    void Delete(string kind, string key, long expectedVersion);
    NativeItem? NativeGet(string id);
    NativeItem NativeCreate(NativeItem item);
    NativeItem? NativeDequeue(string queue, DateTime now);
    void NativeSet(NativeItem item);
    void NativeRedactInput(string id);
    IReadOnlyList<NativeItem> NativePage(string queue, string after, int limit);
}
public sealed class QueuePolicy
{
    public string OwnerTeamId { get; set; } = "";
    public string NativeQueueId { get; set; } = "";
    public bool Enabled { get; set; } = true;
    public int Revision { get; set; } = 1;
    public int MaxAttempts { get; set; } = 3;
    public int LeaseSeconds { get; set; } = 120;
    public int DeadlineSeconds { get; set; } = 1800;
    public int RetryBaseSeconds { get; set; } = 30;
    public int RetryMaxSeconds { get; set; } = 600;
    public bool SafeEffects { get; set; }
    public string[] Contracts { get; set; } = Array.Empty<string>();
    public Dictionary<string, string[]> Grants { get; set; } = new Dictionary<string, string[]>();
    public string[] Destinations { get; set; } = Array.Empty<string>();
}
public sealed class Contract
{
    public string Id { get; set; } = "";
    public string Dialect { get; set; } = "http://json-schema.org/draft-07/schema#";
    public JObject Schema { get; set; } = new JObject();
    public string Hash { get; set; } = "";
}
public sealed class ItemContext
{
    public string LastAttempt { get; set; } = "";
    public string ItemId { get; set; } = "";
    public string ContentHash { get; set; } = "";
    public string SourceKey { get; set; } = "";
    public string CorrelationId { get; set; } = "";
    public string ActiveAttempt { get; set; } = "";
    public int Generation { get; set; }
    public int AttemptCount { get; set; }
    public bool ReviewRequired { get; set; }
    public string OutputJson { get; set; } = "{}";
    public string TestRun { get; set; } = "";
}
public sealed class Attempt
{
    public string Id { get; set; } = "";
    public string ItemId { get; set; } = "";
    public string Worker { get; set; } = "";
    public int Generation { get; set; }
    public DateTime Started { get; set; }
    public DateTime LeaseExpires { get; set; }
    public DateTime Deadline { get; set; }
    public string Outcome { get; set; } = "Processing";
    public string ErrorCode { get; set; } = "";
    public string Checkpoint { get; set; } = "";
    public QueuePolicy Policy { get; set; } = new QueuePolicy();
    public string ContractHash { get; set; } = "";
    public JObject Caller { get; set; } = new JObject();
}
public sealed class Receipt
{
    public string ActorId { get; set; } = "";
    public string Operation { get; set; } = "";
    public string Reason { get; set; } = "";
    public DateTime Created { get; set; }
    public string Fingerprint { get; set; } = "";
    public string Result { get; set; } = "";
}
public sealed class Delivery
{
    public string Id { get; set; } = "";
    public string ItemId { get; set; } = "";
    public string AttemptId { get; set; } = "";
    public string Kind { get; set; } = "";
    public string Destination { get; set; } = "";
    public string State { get; set; } = "Pending";
    public string Owner { get; set; } = "";
    public string LeaseToken { get; set; } = "";
    public DateTime LeaseExpires { get; set; }
    public DateTime NextAttempt { get; set; }
    public int Tries { get; set; }
    public string ErrorCode { get; set; } = "";
}
public sealed class AcquisitionIntent
{
    public string RequestId { get; set; } = "";
    public string ActorId { get; set; } = "";
    public DateTime Expires { get; set; }
    public string Status { get; set; } = "Prepared";
    public string Result { get; set; } = "";
}
