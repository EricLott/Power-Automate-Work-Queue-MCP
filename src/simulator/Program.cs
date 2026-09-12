using Newtonsoft.Json.Linq;
using QueueFramework;
using QueueFramework.Simulator;
var statePath = Path.GetFullPath(Environment.GetEnvironmentVariable("QMCP_SIM_STATE") ?? "artifacts/local/state.json");
var store = new SimulatedStore(statePath);
var engine = new Engine(store);
var admin = new Actor { Id = "local-developer", Roles = new HashSet<string> { "administrator" }, Production = false };
if (args.Contains("--worker"))
{
    var worker = new ReferenceWorker(store, engine, admin, p => new JObject { ["contact"] = (string?)p["senderAddress"], ["category"] = "service", ["summary"] = (string?)p["subject"] });
    Console.Error.WriteLine("LOCAL SIMULATION ONLY: fixture extraction; no mailbox, AI, or Dataverse connection.");
    using var stop = new CancellationTokenSource(); Console.CancelKeyPress += (_, e) => { e.Cancel = true; stop.Cancel(); };
    while (!stop.IsCancellationRequested)
    {
        foreach (var queue in args.SkipWhile(a => a != "--worker").Skip(1))
        {
            try
            {
                worker.Process(queue);
                engine.Execute(new Command { Operation = "RunMaintenance", QueueKey = queue, RequestId = Guid.NewGuid().ToString() }, admin);
                var runs = store.Atomic(() => store.Page("testrun", queue, "", 100));
                foreach (var run in runs) engine.Execute(new Command { Operation = "AdvanceTestRun", QueueKey = queue, ItemId = run.Key, RequestId = Guid.NewGuid().ToString() }, admin);
            }
            catch (Fault f) { Console.Error.WriteLine(f.Code); }
        }
        await Task.Delay(200);
    }
}
else
{
    string? line;
    while ((line = Console.ReadLine()) != null)
    {
        try { var command = Json.Read<Command>(line); Console.WriteLine(engine.Execute(command, admin)); }
        catch (Fault f) { Console.WriteLine(Json.Write(new { Error = f.Code })); }
        catch (Newtonsoft.Json.JsonException) { Console.WriteLine(Json.Write(new { Error = "INPUT_INVALID" })); }
    }
}
