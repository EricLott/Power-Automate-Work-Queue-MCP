"""Explicit synthetic contract snapshot and completion receipt/outbox proof."""
import argparse, copy, hashlib, json, subprocess, uuid
from pathlib import Path
from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding

ERRORS={'CONTRACT_IMMUTABLE','REQUEST_CONFLICT'}
def fault(stdout):
    try: message=json.loads(stdout)['error']['message']
    except (ValueError,TypeError,KeyError): message=''
    return message if message in ERRORS else 'DATAVERSE_CLI_FAILED'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('binding','fixture-ledger','output'): p.add_argument('--'+n,required=True)
    p.add_argument('--execute',action='store_true'); a=p.parse_args()
    binding=json.loads(Path(a.binding).read_text(encoding='utf-8-sig')); origin,expected=_validate_binding(binding)
    fixture=json.loads(Path(a.fixture_ledger).read_text(encoding='utf-8-sig')); queue=fixture['queueKey']
    if queue not in binding['queueKeys'] or not queue.startswith('qmcp-proof-'): raise ValueError('SYNTHETIC_QUEUE_NOT_BOUND')
    for key in ('queue','team','user'): uuid.UUID(fixture[key])
    if not a.execute: print(json.dumps({'ready':True,'writes':False})); return
    out=Path(a.output); proof=str(uuid.uuid4()); record=str(uuid.uuid5(uuid.UUID(proof),'business'))
    evidence={'classification':'live-contract-snapshot-completion-replay','proofId':proof,'organizationId':expected,'queueKey':queue,'completed':False,'businessRecordId':record}
    with out.open('x',encoding='utf-8') as stream: json.dump(evidence,stream,indent=2)
    def note(**values): evidence.update(values); out.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    def runner(*args,**kwargs):
        result=subprocess.run(*args,**kwargs)
        if result.returncode: raise ValueError(fault(result.stdout))
        return result
    cmd=_cli_command()
    def call(method,path,body=None): return _cli_request(cmd,origin,method,path,body,runner=runner)
    def api(op,label,data=None,owned=None,version=None,discard=False):
        request=str(uuid.uuid5(uuid.UUID(proof),label)); body={'QueueKey':queue,'RequestId':request,'DataJson':json.dumps(data or {},separators=(',',':'))}
        if owned: body.update({k:owned[k] for k in ('ItemId','AttemptId','Generation')})
        if version is not None: body['ExpectedVersion']=str(version)
        requests=dict(evidence.get('requests',{})); requests[label]=request; note(requests=requests)
        response=call('POST','qmcp_WQ_'+op,body)
        if discard: return None
        return json.loads(response['ResultJson'])
    def rows(table,key): return call('GET',table+"?$select=qmcp_document,versionnumber&$filter=qmcp_key eq '"+key+"'")['value']
    def single(table,key):
        values=rows(table,key)
        if len(values)!=1: raise ValueError('EXPECTED_SINGLE_ROW')
        return values[0]
    def policy():
        row=single('qmcp_wqdefinitions',queue); return json.loads(row['qmcp_document']),row['versionnumber']
    def expect_error(code,fn):
        try: fn()
        except ValueError as error:
            if str(error)!=code: raise
        else: raise ValueError('EXPECTED_ERROR_MISSING')
    def comparable_policy(value):
        """Ignore monotonic revision and server-added empty optional fields."""
        result=copy.deepcopy(value)
        result.pop('Revision',None)
        result.setdefault('NotificationRules',[])
        result.setdefault('OperationsBaseUrl','')
        return result

    original=None; changed=False
    try:
        who=call('GET','WhoAmI')
        if who['OrganizationId'].lower()!=expected.lower() or who['UserId'].lower()!=fixture['user'].lower(): raise ValueError('ENVIRONMENT_MISMATCH')
        for flow in ('a9c6e175-d6f6-50a7-860c-8fdb91da396e','5391db37-d88c-57c5-839a-d66c26ffd46a','d6228ad8-9758-567d-a1a3-2d5c97ab4c73','6a491be2-4f32-549d-8afb-92d556e5c89b','014c3583-22a5-5146-bf25-94768d689092','656a2463-6fd0-5892-b382-3fc8babdc8ed','a0fed279-6860-5897-912d-ccfabee2de0d'):
            if call('GET','workflows('+flow+')?$select=statecode')['statecode']!=0: raise ValueError('FLOWS_MUST_BE_DRAFT')
        original,version=policy(); note(originalPolicy=original)
        pending=call('GET',"workqueueitems?$select=workqueueitemid,input&$filter=_workqueueid_value eq "+fixture['queue']+" and statecode eq 0&$top=101")['value']
        if not pending or len(pending)>100 or any(json.loads(row['input']).get('source',{}).get('kind')!='synthetic' for row in pending): raise ValueError('SYNTHETIC_BACKLOG_REQUIRED')
        allowed_items={row['workqueueitemid'] for row in pending}
        contract_key=hashlib.sha256((queue+'|mail.v1').encode()).hexdigest()
        contract=json.loads(single('qmcp_wqcontracts',contract_key)['qmcp_document'])
        modified=copy.deepcopy(contract); modified['Schema']['properties']['subject']['maxLength']=17
        expect_error('CONTRACT_IMMUTABLE',lambda:api('RegisterContract','contract-change',modified))
        if json.loads(single('qmcp_wqcontracts',contract_key)['qmcp_document'])!=contract: raise ValueError('CONTRACT_CHANGED')
        note(contractImmutable=True,contractHash=contract['Hash'])
        effective=copy.deepcopy(original); effective.update(Destinations=['qmcp-synthetic-outbox-proof'],LeaseSeconds=900,DeadlineSeconds=1800)
        changed=True
        api('RegisterQueue','policy-effective',effective,version=version)
        effective,_=policy()
        if api('PrepareAcquire','acquire')['Outcome']!='Prepared': raise ValueError('ACQUIRE_NOT_PREPARED')
        claimed=call('POST','workqueues('+fixture['queue']+')/Microsoft.Dynamics.CRM.Dequeue',{}).get('workqueueitemid')
        acquired=api('ResolveAcquire','acquire')
        if acquired.get('Outcome')!='Acquired' or acquired['ItemId']!=claimed or claimed not in allowed_items: raise ValueError('ACQUIRE_NOT_RESOLVED')
        note(itemId=claimed,attemptId=acquired['AttemptId'],generation=acquired['Generation'])
        attempt=json.loads(single('qmcp_wqattempts',acquired['AttemptId'])['qmcp_document'])
        if attempt['ContractHash']!=contract['Hash'] or attempt['Contract']!=contract or attempt['Policy']!=effective: raise ValueError('SNAPSHOT_MISMATCH')
        current,current_version=policy(); current['RetryBaseSeconds']+=1; current['Destinations']=[]
        api('RegisterQueue','policy-later',current,version=current_version)
        after=json.loads(single('qmcp_wqattempts',acquired['AttemptId'])['qmcp_document'])
        if after!=attempt: raise ValueError('ATTEMPT_SNAPSHOT_CHANGED')
        note(contractSnapshot=attempt['Contract'],effectivePolicyRevision=attempt['Policy']['Revision'],snapshotPreserved=True)
        call('POST','qmcp_emailrequests',{'qmcp_emailrequestid':record,'qmcp_name':'Synthetic replay proof','qmcp_key':acquired['BusinessKey'],'qmcp_queuekey':queue,'qmcp_document':json.dumps({'sourceKey':acquired['SourceKey']}),'ownerid@odata.bind':'/teams('+fixture['team']+')'})
        result={'table':'qmcp_emailrequest','recordId':record}
        # Intentionally discard the successful response before receipt replay.
        api('Complete','complete',result,acquired,discard=True)
        replay=api('Complete','complete',result,acquired); repeated=api('Complete','complete',result,acquired)
        if replay!=repeated or replay.get('Outcome')!='Processed': raise ValueError('REPLAY_CHANGED')
        expect_error('REQUEST_CONFLICT',lambda:api('Complete','complete',{**result,'recordId':str(uuid.uuid4())},acquired))
        native=call('GET','workqueueitems('+claimed+')?$select=statecode')['statecode']
        event_key=hashlib.sha256((queue+'|'+claimed+'|'+acquired['AttemptId']+'|Processed|qmcp-synthetic-outbox-proof').encode()).hexdigest()
        event_rows=rows('qmcp_wqevents',event_key)
        queue_events=call('GET',"qmcp_wqevents?$select=qmcp_document&$filter=qmcp_queuekey eq '"+queue+"'&$top=101")['value']
        if len(queue_events)>100 or sum(json.loads(row['qmcp_document']).get('ItemId')==claimed for row in queue_events)!=1: raise ValueError('OUTBOX_COUNT_INVALID')
        receipt_key=hashlib.sha256((fixture['user']+'|Complete|'+evidence['requests']['complete']).encode()).hexdigest()
        receipt_rows=rows('qmcp_wqcommands',receipt_key)
        business=call('GET','qmcp_emailrequests('+record+')?$select=qmcp_emailrequestid')
        if native!=2 or len(event_rows)!=1 or len(receipt_rows)!=1 or business['qmcp_emailrequestid']!=record: raise ValueError('DURABLE_EVIDENCE_MISMATCH')
        if json.loads(json.loads(receipt_rows[0]['qmcp_document'])['Result'])!=replay: raise ValueError('RECEIPT_RESULT_MISMATCH')
        event=json.loads(event_rows[0]['qmcp_document'])
        if event['State']!='Pending': raise ValueError('EVENT_NOT_PENDING')
        note(nativeState=native,completionReplay=replay,changedReplayRejected=True,outboxCount=1,outboxState=event['State'],outboxKey=event_key,completionReceiptCount=1,responseDiscarded=True,completed=True)
    except Exception as error:
        code=str(error) if isinstance(error,ValueError) and str(error).replace('_','').isalpha() and str(error).isupper() else 'PROOF_INCONCLUSIVE'
        note(error=code,completed=False)
    finally:
        if changed and original:
            _,version=policy(); api('RegisterQueue','restore-policy',original,version=version)
            restored,_=policy(); left=comparable_policy(restored); right=comparable_policy(original)
            note(policyRestored=left==right)
            if left!=right: note(completed=False,error='POLICY_RESTORE_FAILED')
        print(json.dumps(evidence,indent=2))
    if not evidence['completed']: raise SystemExit(1)

if __name__=='__main__': main()
