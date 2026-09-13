"""Opt-in installed API proof that direct acquisition acceptance is rejected."""
import argparse, hashlib, json, subprocess, uuid
from pathlib import Path
from bootstrap_tenant import _cli_command, _cli_request
from prove_native_queue_pause import validate, FLOW_IDS


def exact_fault(result):
    if not result.returncode: return False
    try: error=json.loads(result.stdout).get('error', {})
    except (ValueError, TypeError, AttributeError): return False
    return error.get('message') == 'ACQUISITION_HANDOFF_REQUIRED'


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('binding','fixture-ledger','output'): p.add_argument('--'+name,required=True)
    p.add_argument('--execute',action='store_true'); a=p.parse_args(argv)
    binding=json.loads(Path(a.binding).read_text(encoding='utf-8-sig')); f=json.loads(Path(a.fixture_ledger).read_text(encoding='utf-8-sig'))
    origin,org,queue,native_queue,item=validate(binding,f); uuid.UUID(f['user'])
    if not a.execute: print(json.dumps({'ready':True,'tenantCalls':False})); return
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    e={'completed':False,'classification':'installed-direct-acquisition-rejection','organizationId':org,'queueKey':queue,'itemId':item,'requestId':str(uuid.uuid4())}
    with out.open('x',encoding='utf-8') as stream: json.dump(e,stream,indent=2)
    def save(**values): e.update(values); out.write_text(json.dumps(e,indent=2),encoding='utf-8')
    cmd=_cli_command()
    def call(method,path,body=None,runner=subprocess.run): return _cli_request(cmd,origin,method,path,body,runner=runner)
    who=call('GET','WhoAmI')
    if str(who.get('OrganizationId','')).lower()!=org.lower() or str(who.get('UserId','')).lower()!=f['user'].lower(): raise ValueError('IDENTITY_MISMATCH')
    for flow in FLOW_IDS:
        if call('GET','workflows('+flow+')?$select=statecode').get('statecode')!=0: raise ValueError('FLOWS_MUST_BE_DRAFT')
    native_path='workqueueitems('+item+')?$select=workqueueitemid,uniqueidbyqueue,statecode,statuscode,_workqueueid_value'
    before=call('GET',native_path)
    if before.get('_workqueueid_value')!=native_queue or before.get('statecode')!=0 or not before.get('@odata.etag'): raise ValueError('QUEUED_FIXTURE_REQUIRED')
    attempts_path="qmcp_wqattempts?$select=qmcp_wqattemptid&$filter=qmcp_itemid eq '"+item+"'&$top=2"
    def no_attempts():
        rows=call('GET',attempts_path).get('value')
        if not isinstance(rows,list) or rows: raise ValueError('UNEXPECTED_ATTEMPTS')
    no_attempts();save(nativeBefore=before)
    observed={'rejected':False}
    def runner(*args,**kwargs):
        result=subprocess.run(*args,**kwargs);observed['rejected']=exact_fault(result);return result
    try: call('POST','qmcp_WQ_AcceptAcquire',{'QueueKey':queue,'RequestId':e['requestId'],'ItemId':item,'DataJson':'{}'},runner=runner)
    except ValueError:
        if not observed['rejected']: raise ValueError('DIRECT_REJECTION_UNVERIFIED')
    else: raise ValueError('DIRECT_ACCEPTANCE_SUCCEEDED')
    after=call('GET',native_path);no_attempts()
    if before!=after: raise ValueError('NATIVE_ITEM_MUTATED')
    key=hashlib.sha256((f['user']+'|AcceptAcquire|'+e['requestId']).encode()).hexdigest()
    receipts=call('GET',"qmcp_wqcommands?$select=qmcp_wqcommandid&$filter=qmcp_key eq '"+key+"'&$top=2").get('value')
    if not isinstance(receipts,list) or receipts: raise ValueError('UNEXPECTED_ACCEPTANCE_RECEIPT')
    save(nativeAfter=after,attemptCount=0,receiptCount=0,error='ACQUISITION_HANDOFF_REQUIRED',completed=True)
    print(json.dumps(e,indent=2))

if __name__=='__main__':
    try: main()
    except (ValueError,TypeError,KeyError,OSError) as error: raise SystemExit(str(error))
