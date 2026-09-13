"""Opt-in native stale ownership proof with simultaneous old-worker calls."""
import argparse,hashlib,json,subprocess,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from bootstrap_tenant import _cli_command,_cli_request
from probe_tenant_metadata import _validate_binding

def request_ids(proof):
    labels=('prepare-old','resolve-old','fail-old','status-old','retry','prepare-new','resolve-new','stale-complete','stale-fail','stale-checkpoint','complete-new')
    ids={label:str(uuid.uuid5(uuid.UUID(proof),label)) for label in labels}
    for label in ('old','new'): ids['resolve-'+label]=ids['prepare-'+label]
    return ids

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('binding','fixture-ledger','output'): p.add_argument('--'+n,required=True)
    p.add_argument('--execute',action='store_true'); p.add_argument('--resume',action='store_true'); a=p.parse_args()
    binding=json.loads(Path(a.binding).read_text(encoding='utf-8-sig')); origin,expected=_validate_binding(binding)
    fixture=json.loads(Path(a.fixture_ledger).read_text(encoding='utf-8-sig')); queue=fixture['queueKey']
    if queue not in binding['queueKeys'] or not queue.startswith('qmcp-proof-'): raise ValueError('SYNTHETIC_QUEUE_NOT_BOUND')
    for key in ('queue','team','user'): uuid.UUID(fixture[key])
    if not a.execute: print(json.dumps({'ready':True,'writes':False})); return
    prior=json.loads(Path(a.output).read_text()) if a.resume else None
    if prior and (prior.get('error')!='ACQUIRE_NOT_RESOLVED' or prior.get('oldAttemptId') or prior.get('organizationId')!=expected or prior.get('queueKey')!=queue): raise ValueError('RESUME_NOT_SUPPORTED')
    proof=prior['proofId'] if prior else str(uuid.uuid4()); record=str(uuid.uuid5(uuid.UUID(proof),'business'))
    ids=request_ids(proof)
    evidence={'classification':'live-stale-worker-ownership','proofId':proof,'organizationId':expected,'queueKey':queue,'requests':ids,'businessRecordId':record,'completed':False}
    out=Path(a.output)
    if prior:
        evidence['previousError']=prior['error']; evidence['resumedAcquisition']=True
        out.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    else:
        with out.open('x',encoding='utf-8') as stream: json.dump(evidence,stream,indent=2)
    def note(**values): evidence.update(values); out.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    def runner(*args,**kwargs):
        result=subprocess.run(*args,**kwargs)
        if result.returncode:
            try: code=json.loads(result.stdout)['error']['message']
            except (ValueError,TypeError,KeyError): code=''
            raise ValueError('STALE_ATTEMPT' if code=='STALE_ATTEMPT' else 'DATAVERSE_CLI_FAILED')
        return result
    cmd=_cli_command()
    def call(method,path,body=None): return _cli_request(cmd,origin,method,path,body,runner=runner)
    def api(op,label,data=None,owned=None,item=None,version=None):
        body={'QueueKey':queue,'RequestId':ids[label],'DataJson':json.dumps(data or {},separators=(',',':'))}
        if owned: body.update({k:owned[k] for k in ('ItemId','AttemptId','Generation')})
        if item: body['ItemId']=item
        if version is not None: body['ExpectedVersion']=str(version)
        return json.loads(call('POST','qmcp_WQ_'+op,body)['ResultJson'])
    def acquire(label):
        if api('PrepareAcquire','prepare-'+label)['Outcome']!='Prepared': raise ValueError('ACQUIRE_NOT_PREPARED')
        item=call('POST','workqueues('+fixture['queue']+')/Microsoft.Dynamics.CRM.Dequeue',{}).get('workqueueitemid')
        result=api('ResolveAcquire','resolve-'+label)
        if result.get('Outcome')!='Acquired' or result['ItemId']!=item: raise ValueError('ACQUIRE_NOT_RESOLVED')
        return result
    def stored(table,key):
        rows=call('GET',table+"?$select=qmcp_document,versionnumber&$filter=qmcp_key eq '"+key+"'")['value']
        if len(rows)!=1: raise ValueError('EXPECTED_SINGLE_ROW')
        return rows[0]
    try:
        who=call('GET','WhoAmI')
        if who['OrganizationId'].lower()!=expected.lower() or who['UserId'].lower()!=fixture['user'].lower(): raise ValueError('ENVIRONMENT_MISMATCH')
        for flow in ('a9c6e175-d6f6-50a7-860c-8fdb91da396e','5391db37-d88c-57c5-839a-d66c26ffd46a','d6228ad8-9758-567d-a1a3-2d5c97ab4c73','6a491be2-4f32-549d-8afb-92d556e5c89b','014c3583-22a5-5146-bf25-94768d689092','656a2463-6fd0-5892-b382-3fc8babdc8ed','a0fed279-6860-5897-912d-ccfabee2de0d'):
            if call('GET','workflows('+flow+')?$select=statecode')['statecode']!=0: raise ValueError('FLOWS_MUST_BE_DRAFT')
        state=1 if prior else 0
        pending=call('GET',"workqueueitems?$select=workqueueitemid,input&$filter=_workqueueid_value eq "+fixture['queue']+" and statecode eq "+str(state)+"&$top=2")['value']
        if len(pending)!=1 or json.loads(pending[0]['input']).get('source',{}).get('kind')!='synthetic': raise ValueError('ONE_SYNTHETIC_PENDING_ITEM_REQUIRED')
        item=pending[0]['workqueueitemid']; old=api('ResolveAcquire','resolve-old') if prior else acquire('old')
        if old['ItemId']!=item: raise ValueError('UNEXPECTED_ITEM')
        note(itemId=item,oldAttemptId=old['AttemptId'],oldGeneration=old['Generation'])
        failed=api('Fail','fail-old',{'category':'Unknown','code':'SYNTHETIC_STALE_PROOF','effect':'Unknown'},old)
        if failed['Outcome']!='ReviewRequired': raise ValueError('UNKNOWN_NOT_HELD')
        status=api('GetItemStatus','status-old',item=item)
        if not status['ReviewRequired'] or status['ActiveAttempt']: raise ValueError('REVIEW_STATE_INVALID')
        retry=api('RequestRetry','retry',{'reason':'Synthetic proof made no external business effect','reconciliation':'VerifiedSafe'},item=item,version=status['Version'])
        if retry['Outcome']!='RetryScheduled': raise ValueError('RETRY_FAILED')
        newer=acquire('new')
        if newer['ItemId']!=item or newer['Generation']<=old['Generation'] or newer['AttemptId']==old['AttemptId']: raise ValueError('OWNERSHIP_NOT_REPLACED')
        note(newAttemptId=newer['AttemptId'],newGeneration=newer['Generation'])
        context_key=hashlib.sha256((queue+'|'+json.loads(pending[0]['input'])['deduplicationKey']).encode()).hexdigest()
        before_attempt=stored('qmcp_wqattempts',newer['AttemptId']); before_context=stored('qmcp_wqitemcontexts',context_key)
        operations=[('Complete','stale-complete',{'table':'qmcp_emailrequest','recordId':record}),('Fail','stale-fail',{'category':'Unknown','code':'STALE','effect':'Unknown'}),('Checkpoint','stale-checkpoint',{'progress':'Stale worker must not extend lease'})]
        def stale(case):
            op,label,data=case
            try: api(op,label,data,old)
            except ValueError as error: return {'operation':op,'error':str(error)}
            return {'operation':op,'error':'UNEXPECTED_SUCCESS'}
        with ThreadPoolExecutor(max_workers=3) as pool: rejected=list(pool.map(stale,operations))
        note(staleCalls=rejected)
        if any(row['error']!='STALE_ATTEMPT' for row in rejected): raise ValueError('STALE_FENCE_FAILED')
        if stored('qmcp_wqattempts',newer['AttemptId'])!=before_attempt or stored('qmcp_wqitemcontexts',context_key)!=before_context: raise ValueError('CURRENT_OWNERSHIP_MUTATED')
        if call('GET','workqueueitems('+item+')?$select=statecode')['statecode']!=1: raise ValueError('CURRENT_NATIVE_STATE_MUTATED')
        note(currentAttemptAndContextUnchanged=True)
        call('POST','qmcp_emailrequests',{'qmcp_emailrequestid':record,'qmcp_name':'Synthetic stale ownership proof','qmcp_key':newer['BusinessKey'],'qmcp_queuekey':queue,'qmcp_document':json.dumps({'sourceKey':newer['SourceKey']}),'ownerid@odata.bind':'/teams('+fixture['team']+')'})
        if api('Complete','complete-new',{'table':'qmcp_emailrequest','recordId':record},newer)['Outcome']!='Processed': raise ValueError('CURRENT_WORKER_CANNOT_COMPLETE')
        native=call('GET','workqueueitems('+item+')?$select=statecode')['statecode']
        business=call('GET','qmcp_emailrequests('+record+')?$select=qmcp_emailrequestid')
        if native!=2 or business['qmcp_emailrequestid']!=record: raise ValueError('OUTPUT_NOT_VERIFIED')
        note(nativeState=native,currentWorkerCompleted=True,completed=True)
    except Exception as error:
        code=str(error) if isinstance(error,ValueError) and str(error).replace('_','').isalpha() and str(error).isupper() else 'PROOF_INCONCLUSIVE'
        note(error=code,completed=False)
    finally: print(json.dumps(evidence,indent=2))
    if not evidence['completed']: raise SystemExit(1)

if __name__=='__main__': main()
