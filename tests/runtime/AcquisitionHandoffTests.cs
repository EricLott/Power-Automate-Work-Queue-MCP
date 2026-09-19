using Newtonsoft.Json.Linq;
using QueueFramework;
using Xunit;
namespace QueueFramework.Tests;
public sealed class AcquisitionHandoffTests
{
    [Fact]
    public void AcceptRejectsIntentVersionChangedAfterValidation()
    {
        var f = new Fixture(); var id = f.Enqueue();
        var native = f.Store.NativeGet(id)!; native.Status = "Processing"; f.Store.NativeSet(native);
        var prepare = f.Cmd("PrepareAcquire"); f.Run(prepare);
        var accept = f.Cmd("AcceptAcquire", new { }, id); accept.RequestId = prepare.RequestId;
        f.Store.BeforeWrite = operation =>
        {
            if (operation != "add:attempt") return;
            f.Store.BeforeWrite = null;
            var row = f.Store.Get("cursor", Json.Hash("acquire|admin|mail"))!;
            f.Store.Put(row, row.Version);
        };
        Assert.Equal("VERSION_CONFLICT", Assert.Throws<Fault>(() => f.Run(accept)).Code);
        Assert.Empty(f.Store.Page("attempt", "mail", "", 100));
        Assert.Equal("Prepared", Json.Read<AcquisitionIntent>(f.Store.Get("cursor", Json.Hash("acquire|admin|mail"))!.Body).Status);
    }
    [Fact] public void PrepareIsIdempotentAndBusyForAnotherRequest(){var f=new Fixture();var c=f.Cmd("PrepareAcquire");var first=f.Run(c);Assert.Equal((string)first["RequestId"]!, (string)f.Run(c)["RequestId"]!);var other=f.Cmd("PrepareAcquire");Assert.Equal("ACQUIRE_BUSY",Assert.Throws<Fault>(()=>f.Run(other)).Code);}
    [Fact] public void AcceptConsumesIntentAndCannotRepeat(){var f=new Fixture();var id=f.Enqueue();var native=f.Store.NativeGet(id)!;native.Status="Processing";f.Store.NativeSet(native);var prepare=f.Cmd("PrepareAcquire");var request=(string)f.Run(prepare)["RequestId"]!;var accept=f.Cmd("AcceptAcquire",new{},id);accept.RequestId=request;var result=f.Run(accept);Assert.Equal("Acquired",(string)result["Outcome"]!);Assert.Equal(result.ToString(),f.Run(accept).ToString());}
    [Fact] public void AcceptRejectsInvalidNativeStateWithoutConsumingIntent(){var f=new Fixture();var id=f.Enqueue();var prepare=f.Cmd("PrepareAcquire");var request=(string)f.Run(prepare)["RequestId"]!;var accept=f.Cmd("AcceptAcquire",new{},id);accept.RequestId=request;Assert.Equal("NATIVE_ITEM_INVALID",Assert.Throws<Fault>(()=>f.Run(accept)).Code);Assert.Equal("Prepared",Json.Read<AcquisitionIntent>(f.Store.Get("cursor",Json.Hash("acquire|admin|mail"))!.Body).Status);}
    [Fact] public void ResolveOldRequestSurvivesIntentOverwrite(){var f=new Fixture();var id=f.Enqueue();var native=f.Store.NativeGet(id)!;native.Status="Processing";f.Store.NativeSet(native);var prepare=f.Cmd("PrepareAcquire");var request=(string)f.Run(prepare)["RequestId"]!;var accept=f.Cmd("AcceptAcquire",new{},id);accept.RequestId=request;var accepted=f.Run(accept);f.Run(f.Cmd("PrepareAcquire"));var resolve=f.Cmd("ResolveAcquire");resolve.RequestId=request;Assert.Equal(accepted.ToString(),f.Run(resolve).ToString());}
    [Fact] public void AcceptRejectsPausedAndUnavailableOrExpiredItems(){var f=new Fixture();var id=f.Enqueue();var native=f.Store.NativeGet(id)!;native.Status="Processing";native.Available=f.Now.AddSeconds(1);f.Store.NativeSet(native);var prepare=f.Cmd("PrepareAcquire");var request=(string)f.Run(prepare)["RequestId"]!;var accept=f.Cmd("AcceptAcquire",new{},id);accept.RequestId=request;Assert.Equal("ITEM_NOT_AVAILABLE",Assert.Throws<Fault>(()=>f.Run(accept)).Code);f.Now=f.Now.AddSeconds(2);Assert.Equal("Acquired",(string)f.Run(accept)["Outcome"]!);var p=f.Policy();p.Enabled=false;f.Run(f.Cmd("RegisterQueue",p,version:1));var paused=f.Cmd("AcceptAcquire",new{},id);Assert.Equal("QUEUE_PAUSED",Assert.Throws<Fault>(()=>f.Run(paused)).Code);}
    [Fact] public void FailedAcceptRollsBackIntentAndContext(){var f=new Fixture();var id=f.Enqueue();var native=f.Store.NativeGet(id)!;native.Status="Processing";f.Store.NativeSet(native);var prepare=f.Cmd("PrepareAcquire");var request=(string)f.Run(prepare)["RequestId"]!;var accept=f.Cmd("AcceptAcquire",new{},id);accept.RequestId=request;f.Store.BeforeWrite=op=>{if(op=="add:attempt")throw new Fault("INJECTED");};Assert.Throws<Fault>(()=>f.Run(accept));f.Store.BeforeWrite=null;var intent=Json.Read<AcquisitionIntent>(f.Store.Get("cursor",Json.Hash("acquire|admin|mail"))!.Body);Assert.Equal("Prepared",intent.Status);Assert.Equal("",f.Status(id)["ActiveAttempt"]!.ToString());}
    [Fact] public void ResolveCannotDiscloseReceiptAcrossQueues(){var f=new Fixture();var id=f.Enqueue();var native=f.Store.NativeGet(id)!;native.Status="Processing";f.Store.NativeSet(native);var prepare=f.Cmd("PrepareAcquire");var request=(string)f.Run(prepare)["RequestId"]!;var accept=f.Cmd("AcceptAcquire",new{},id);accept.RequestId=request;f.Run(accept);var p=f.Policy();p.NativeQueueId="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";var register=f.Cmd("RegisterQueue",p);register.QueueKey="other";f.Run(register);var resolve=f.Cmd("ResolveAcquire");resolve.QueueKey="other";resolve.RequestId=request;Assert.Equal("NoAcquisition",(string)f.Run(resolve)["Outcome"]!);}
}
