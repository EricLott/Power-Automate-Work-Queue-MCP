"""Opt-in status redaction proof using a queued synthetic framework item."""
import argparse, json, subprocess, uuid
from pathlib import Path
from bootstrap_tenant import _cli_command, _cli_request
from prove_native_queue_pause import validate, FLOW_IDS

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('binding','fixture','output'): p.add_argument('--'+n,required=True)
    p.add_argument('--execute',action='store_true'); a=p.parse_args(argv)
    bd=json.loads(Path(a.binding).read_text(encoding='utf-8-sig')); f=json.loads(Path(a.fixture).read_text(encoding='utf-8-sig'))
    origin,org,queue,native_queue,item=validate(bd,f); uuid.UUID(f['team'])
    if not a.execute: print(json.dumps({'ready':True,'tenantCalls':False})); return
    e={'completed':False,'classification':'installed-status-redaction','organizationId':org,'queueKey':queue,'itemId':item,'recordId':str(uuid.uuid4()),'requests':{k:str(uuid.uuid4()) for k in ('acquire','complete','status')}}
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8') as h: json.dump(e,h,indent=2)
    def save(**v): e.update(v); out.write_text(json.dumps(e,indent=2),encoding='utf-8')
    cmd=_cli_command()
    def call(method,path,body=None): return _cli_request(cmd,origin,method,path,body,runner=subprocess.run)
    def api(op,label,data=None,owned=None):
        body={'QueueKey':queue,'RequestId':e['requests'][label],'DataJson':json.dumps(data or {})}
        if owned: body.update({k:owned[k] for k in ('ItemId','AttemptId','Generation')})
        if op=='GetItemStatus': body['ItemId']=item
        return json.loads(call('POST','qmcp_WQ_'+op,body)['ResultJson'])
    who=call('GET','WhoAmI')
    if str(who.get('OrganizationId','')).lower()!=org.lower(): raise ValueError('ENVIRONMENT_MISMATCH')
    for flow in FLOW_IDS:
        if call('GET','workflows('+flow+')?$select=statecode').get('statecode')!=0: raise ValueError('FLOWS_MUST_BE_DRAFT')
    pending=call('GET','workqueueitems?$select=workqueueitemid&$filter=_workqueueid_value eq '+native_queue+' and statecode eq 0&$top=2').get('value')
    if not isinstance(pending,list) or len(pending)!=1 or pending[0]['workqueueitemid']!=item: raise ValueError('SOLE_SYNTHETIC_ITEM_REQUIRED')
    native=call('GET','workqueueitems('+item+')?$select=input')
    if json.loads(native['input']).get('source',{}).get('kind')!='synthetic': raise ValueError('SYNTHETIC_INPUT_REQUIRED')
    prepared=api('PrepareAcquire','acquire')
    if prepared.get('Outcome')!='Prepared' or prepared.get('NativeQueueId')!=native_queue: raise ValueError('PREPARE_FAILED')
    claimed=call('POST','workqueues('+native_queue+')/Microsoft.Dynamics.CRM.Dequeue',{})
    owned=api('ResolveAcquire','acquire'); save(acquisition=owned)
    if claimed.get('workqueueitemid')!=item or owned.get('ItemId')!=item or owned.get('Outcome')!='Acquired': raise ValueError('ACQUISITION_FAILED')
    call('POST','qmcp_emailrequests',{'qmcp_emailrequestid':e['recordId'],'qmcp_name':'Synthetic status redaction proof','qmcp_key':owned['BusinessKey'],'qmcp_queuekey':queue,'qmcp_document':json.dumps({'sourceKey':owned['SourceKey'],'contentHash':owned['ContentHash']}),'ownerid@odata.bind':'/teams('+f['team']+')'})
    completion={'table':'qmcp_emailrequest','recordId':e['recordId'],'privateNote':'SYNTHETIC_PRIVATE_SENTINEL','nested':{'value':'SYNTHETIC_NESTED_SENTINEL'}}
    save(completionInput=completion)
    if api('Complete','complete',completion,owned).get('Outcome')!='Processed': raise ValueError('COMPLETE_FAILED')
    status=api('GetItemStatus','status'); save(status=status)
    if status.get('Output')!={'table':'qmcp_emailrequest','recordId':e['recordId']} or status.get('LastAttempt')!=owned['AttemptId'] or status.get('ActiveAttempt')!='' or status.get('Outcome')!='Processed': raise ValueError('STATUS_REDACTION_FAILED')
    rows=call('GET',"qmcp_wqitemcontexts?$select=qmcp_document&$filter=qmcp_key eq '"+owned['BusinessKey']+"'&$top=2").get('value')
    if not isinstance(rows,list) or len(rows)!=1: raise ValueError('CONTEXT_NOT_UNIQUE')
    preserved=json.loads(json.loads(rows[0]['qmcp_document'])['OutputJson'])
    if preserved!=completion: raise ValueError('INTERNAL_EVIDENCE_LOST')
    result=call('GET','qmcp_emailrequests('+e['recordId']+')?$select=qmcp_key')
    if result['qmcp_key']!=owned['BusinessKey']: raise ValueError('OUTPUT_NOT_VERIFIED')
    save(internalEvidencePreserved=True,outputVerified=True,completed=True); print(json.dumps(e,indent=2))

if __name__=='__main__':
    try: main()
    except (ValueError,TypeError,KeyError,OSError) as err: raise SystemExit(str(err))
