namespace QueueFramework.Simulator;
/// <summary>A serialized local model, not a Dataverse emulator or platform transaction proof.</summary>
public sealed class SimulatedStore : IStore
{
    public sealed class State
    {
        public Dictionary<string, Row> Rows { get; set; } = new();
        public Dictionary<string, NativeItem> Native { get; set; } = new();
    }
    readonly object mutex = new();
    readonly string? path;
    int depth;
    State state = new();
    public Action<string>? BeforeWrite { get; set; }
    public SimulatedStore(string? path = null) { this.path = path; }
    public T Atomic<T>(Func<T> operation)
    {
        lock (mutex)
        {
            if (depth > 0) return operation();
            FileStream? lease = null;
            try
            {
                if (path != null)
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
                    // Cross-process serialization makes detached local worker and MCP clients share one durable model.
                    for (int i = 0; ; i++) { try { lease = new FileStream(path + ".lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None); break; } catch (IOException) when (i < 100) { Thread.Sleep(25); } }
                    if (File.Exists(path)) state = Json.Read<State>(File.ReadAllText(path));
                }
                var snapshot = Json.Write(state); depth++;
                try
                {
                    var result = operation();
                    if (path != null) { var tmp = path + "." + Guid.NewGuid().ToString("N") + ".tmp"; File.WriteAllText(tmp, Json.Write(state)); File.Move(tmp, path, true); }
                    return result;
                }
                catch { state = Json.Read<State>(snapshot); throw; }
                finally { depth--; }
            }
            finally { lease?.Dispose(); }
        }
    }
    static T Copy<T>(T value) => Json.Read<T>(Json.Write(value!));
    static string Id(string kind, string key) => kind + ":" + key;
    public Row? Get(string kind, string key) => state.Rows.TryGetValue(Id(kind, key), out var value) ? Copy(value) : null;
    public IReadOnlyList<Row> Page(string kind, string queue, string after, int limit) => state.Rows.Values.Where(r => r.Kind == kind && r.Queue == queue && string.CompareOrdinal(r.Key, after) > 0).OrderBy(r => r.Key, StringComparer.Ordinal).Take(Math.Min(100, limit)).Select(Copy).ToList();
    public Row Add(Row row) { BeforeWrite?.Invoke("add:" + row.Kind); var id = Id(row.Kind, row.Key); if (state.Rows.ContainsKey(id)) throw new Fault("DUPLICATE_KEY"); row.Version = 1; state.Rows.Add(id, Copy(row)); return Copy(row); }
    public Row Put(Row row, long version) { BeforeWrite?.Invoke("put:" + row.Kind); var current = Get(row.Kind, row.Key) ?? throw new Fault("NOT_FOUND"); if (current.Version != version) throw new Fault("VERSION_CONFLICT"); row.Version = version + 1; state.Rows[Id(row.Kind, row.Key)] = Copy(row); return Copy(row); }
    public void Delete(string kind, string key, long version) { BeforeWrite?.Invoke("delete:" + kind); if (Get(kind, key)?.Version != version) throw new Fault("VERSION_CONFLICT"); state.Rows.Remove(Id(kind, key)); }
    public NativeItem? NativeGet(string id) => state.Native.TryGetValue(id, out var value) ? Copy(value) : null;
    public NativeItem NativeCreate(NativeItem item) { BeforeWrite?.Invoke("native:create"); if (state.Native.Values.Any(n => n.Queue == item.Queue && n.UniqueKey == item.UniqueKey)) throw new Fault("DUPLICATE_KEY"); state.Native.Add(item.Id, Copy(item)); return Copy(item); }
    public NativeItem? NativeDequeue(string queue, DateTime now) { BeforeWrite?.Invoke("native:dequeue"); var item = state.Native.Values.Where(n => n.Queue == queue && n.Status == "Queued" && n.Available <= now && n.Expires > now).OrderBy(n => n.Created).ThenBy(n => n.Id, StringComparer.Ordinal).FirstOrDefault(); if (item == null) return null; item.Status = "Processing"; return Copy(item); }
    public void NativeSet(NativeItem item) { BeforeWrite?.Invoke("native:set"); if (!state.Native.ContainsKey(item.Id)) throw new Fault("ITEM_NOT_FOUND"); state.Native[item.Id] = Copy(item); }
    public void NativeRedactInput(string id) { var item = NativeGet(id) ?? throw new Fault("ITEM_NOT_FOUND"); item.Input = "{}"; NativeSet(item); }
    public IReadOnlyList<NativeItem> NativePage(string queue, string after, int limit) => state.Native.Values.Where(n => n.Queue == queue && string.CompareOrdinal(n.Id, after) > 0).OrderBy(n => n.Id, StringComparer.Ordinal).Take(Math.Min(100, limit)).Select(Copy).ToList();
}
