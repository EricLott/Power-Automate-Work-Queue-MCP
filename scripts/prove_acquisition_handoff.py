"""Opt-in synthetic tenant proof: receipt rollback, concurrent claim, delayed retry."""
import argparse, concurrent.futures, datetime, hashlib, json, subprocess, sys, time, uuid
from pathlib import Path

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 for name in ['binding','fixture-ledger','output-dir','run-id']: parser.add_argument('--'+name,required=True)
 parser.add_argument('--execute',action='store_true')
 args=parser.parse_args()
 binding=json.loads(Path(args.binding).read_text(encoding='utf-8-sig'))
 ids=json.loads(Path(args.fixture_ledger).read_text(encoding='utf-8-sig'))
 run=args.run_id; output=Path(args.output_dir)
 if not run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in run): raise ValueError('RUN_ID_INVALID')
 if output.exists(): raise ValueError('EVIDENCE_RUN_EXISTS')
 if binding.get('environmentClass')!='development' or not binding.get('environmentUrl','').startswith('https://'): raise ValueError('DEVELOPMENT_BINDING_REQUIRED')
 if not ids.get('queueKey','').startswith('qmcp-proof-'): raise ValueError('SYNTHETIC_QUEUE_REQUIRED')
 for key in ['queue','team','principal','user']: uuid.UUID(ids[key])
 uuid.UUID(binding['organizationId'])
 if not args.execute:
  print(json.dumps({'ready':True,'runId':run,'liveCalls':False})); return
 output.mkdir(parents=True,exist_ok=False)
 sys.path.insert(0,str(Path(__file__).resolve().parent))
 import bootstrap_tenant as b
 cmd=b._cli_command(); events=[]
 def req(method,path,body=None):
  def runner(*args,**kwargs):
   r=subprocess.run(*args,**kwargs)
   if r.returncode:(output / ('error-'+str(uuid.uuid4())+'.json')).write_text(r.stdout)
   return r
  return b._cli_request(cmd,binding['environmentUrl'],method,path,body,runner=runner)
 def note(kind,**values):
  events.append({'step':kind,**values});(output / 'evidence.json').write_text(json.dumps(events,indent=2));print(kind,json.dumps(values),flush=True)
 def rid(suffix):return str(uuid.uuid5(uuid.UUID(ids['queue']),run+'|'+suffix))
 def api(op,suffix,data=None,owned=None):
  body={'QueueKey':ids['queueKey'],'RequestId':rid(suffix),'DataJson':json.dumps(data or {})}
  if owned:body.update({k:owned[k] for k in ['ItemId','AttemptId','Generation']})
  return json.loads(req('POST','qmcp_WQ_'+op,body)['ResultJson'])
 def dequeue():
  try:return {'ok':True,'item':req('POST','workqueues('+ids['queue']+')/Microsoft.Dynamics.CRM.Dequeue',{}).get('workqueueitemid')}
  except ValueError:return {'ok':False,'item':None}
 def native(item):return req('GET','workqueueitems('+item+')?$select=statecode,statuscode,delayuntil')
 def attempts(item):return req('GET',"qmcp_wqattempts?$select=qmcp_wqattemptid,qmcp_document&$filter=qmcp_itemid eq '"+item+"'")['value']
 def receipts(suffix):
  key=hashlib.sha256((ids['user']+'|AcceptAcquire|'+rid(suffix)).encode()).hexdigest()
  return req('GET',"qmcp_wqcommands?$select=qmcp_wqcommandid&$filter=qmcp_key eq '"+key+"'")['value']
 def finish(owned,suffix):
  record=str(uuid.uuid5(uuid.UUID(ids['queue']),'stress-output|'+owned['BusinessKey']))
  rows=req('GET',"qmcp_emailrequests?$select=qmcp_emailrequestid&$filter=qmcp_key eq '"+owned['BusinessKey']+"'")['value']
  if not rows:req('POST','qmcp_emailrequests',{'qmcp_emailrequestid':record,'qmcp_name':'Synthetic transaction proof output','qmcp_key':owned['BusinessKey'],'qmcp_queuekey':ids['queueKey'],'qmcp_document':json.dumps({'sourceKey':owned['SourceKey']}),'ownerid@odata.bind':'/teams('+ids['team']+')'})
  out=api('Complete',suffix,{'table':'qmcp_emailrequest','recordId':record},owned)
  assert out['Outcome']=='Processed' and api('Complete',suffix,{'table':'qmcp_emailrequest','recordId':record},owned)==out
  note('completed',item=owned['ItemId'],nativeState=native(owned['ItemId'])['statecode'])
 assert binding['environmentClass']=='development' and ids['queueKey'].startswith('qmcp-proof-')
 identity=req('GET','WhoAmI')
 assert identity['OrganizationId']==binding['organizationId'] and identity['UserId']==ids['user']
 for suffix in ['a','b']:
  key=hashlib.sha256((ids['user']+'|Enqueue|'+rid('enqueue-'+suffix)).encode()).hexdigest()
  assert not req('GET',"qmcp_wqcommands?$select=qmcp_wqcommandid&$filter=qmcp_key eq '"+key+"'")['value'], 'RUN_ALREADY_USED'
 assert not req('GET',"workqueueitems?$select=workqueueitemid&$filter=_workqueueid_value eq "+ids['queue']+" and statecode ne 2")['value'], 'SYNTHETIC_QUEUE_NOT_IDLE'
 items=[]
 for suffix in ['a','b']:
  payload={'envelopeVersion':'1.0','contract':'mail.v1','correlationId':run+'-'+suffix,'deduplicationKey':run+'-'+suffix,'source':{'kind':'synthetic'},'payload':{'subject':'Synthetic transaction proof','senderAddress':'synthetic@example.invalid','bodyText':'Synthetic framework proof only.'}}
  items.append(api('Enqueue','enqueue-'+suffix,payload)['ItemId'])
 assert api('PrepareAcquire','claim-a')['Outcome']=='Prepared'
 profile=req('GET','qmcp_wqprincipals('+ids['principal']+')?$select=qmcp_document')['qmcp_document']
 (output / 'original-principal.json').write_text(profile)
 modified=json.loads(profile);modified['proofFault']='before-receipt'
 try:
  req('PATCH','qmcp_wqprincipals('+ids['principal']+')',{'qmcp_document':json.dumps(modified)})
  failed=dequeue();assert not failed['ok']
 finally:req('PATCH','qmcp_wqprincipals('+ids['principal']+')',{'qmcp_document':profile})
 assert all(native(item)['statecode']==0 and len(attempts(item))==0 for item in items)
 assert receipts('claim-a')==[] and api('ResolveAcquire','claim-a')['Outcome']=='Pending'
 note('receipt-failure-rollback',queuedItems=2,attempts=0,acceptReceipts=0,profileRestored=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  results=list(pool.map(lambda _:dequeue(),range(2)))
 resolved=api('ResolveAcquire','claim-a');assert resolved['Outcome']=='Acquired'
 assert api('ResolveAcquire','claim-a')==resolved
 states=[native(item)['statecode'] for item in items]
 assert sorted(states)==[0,1] and sum(len(attempts(item)) for item in items)==1 and len(receipts('claim-a'))==1
 note('concurrent-native-claims',responses=results,nativeStates=states,attempts=1,acceptReceipts=1,repeatedResolveIdentical=True)
 finish(resolved,'complete-a')
 assert api('PrepareAcquire','claim-b')['Outcome']=='Prepared'
 assert dequeue()['ok']
 second=api('ResolveAcquire','claim-b');assert second['Outcome']=='Acquired' and second['ItemId']!=resolved['ItemId']
 assert api('Fail','fail-b',{'category':'Technical','code':'SYNTHETIC_TRANSIENT','effect':'None'},second)['Outcome']=='RetryScheduled'
 queued=native(second['ItemId']);assert queued['statecode']==0
 closed=json.loads(attempts(second['ItemId'])[0]['qmcp_document']);assert closed['Outcome']=='Exception'
 note('safe-delayed-retry',nativeState=0,attemptOutcome=closed['Outcome'],delayUntil=queued['delayuntil'])
 assert api('PrepareAcquire','claim-c')['Outcome']=='Prepared'
 early=dequeue();assert early['ok'] and early['item'] is None
 assert api('ResolveAcquire','claim-c')['Outcome']=='Pending'
 note('delayed-item-not-claimed-early',nativeItemReturned=False)
 due=datetime.datetime.fromisoformat(queued['delayuntil'].replace('Z','+00:00'))
 wait=max(0,(due-datetime.datetime.now(datetime.timezone.utc)).total_seconds()+1)
 assert wait<=55
 if wait:time.sleep(wait)
 assert dequeue()['ok']
 third=api('ResolveAcquire','claim-c');assert third['Outcome']=='Acquired' and third['ItemId']==second['ItemId']
 assert third['Generation']>second['Generation']
 finish(third,'complete-b')
 assert all(native(item)['statecode']==2 for item in items)
 assert sorted(len(attempts(item)) for item in items)==[1,2]
 note('proof-completed',processedItems=2,attemptCounts=[len(attempts(item)) for item in items],allLiveGatesRemainOpen=True)

if __name__ == '__main__':
 main()
