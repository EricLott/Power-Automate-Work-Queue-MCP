"""Opt-in reversible native expiry experiment on an isolated synthetic probe."""
import argparse, datetime, json, subprocess, uuid
from pathlib import Path
from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('binding','fixture','output'): p.add_argument('--'+n,required=True)
    p.add_argument('--execute',action='store_true'); a=p.parse_args(argv)
    origin,org=_validate_binding(json.loads(Path(a.binding).read_text(encoding='utf-8-sig')))
    f=json.loads(Path(a.fixture).read_text(encoding='utf-8-sig')); item=str(uuid.UUID(f['itemId'])); queue=str(uuid.UUID(f['queueId']))
    if not a.execute: print(json.dumps({'ready':True,'tenantCalls':False})); return
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    e={'classification':'isolated-native-expiry','organizationId':org,'itemId':item,'queueId':queue,'completed':False}
    with out.open('x',encoding='utf-8') as h: json.dump(e,h,indent=2)
    def save(**v): e.update(v); out.write_text(json.dumps(e,indent=2),encoding='utf-8')
    cmd=_cli_command(); etag=None
    def runner(args,**kw):
        if '--method' in args and args[args.index('--method')+1]=='PATCH':
            if not etag: raise ValueError('ETAG_REQUIRED')
            args=list(args)+['--header','If-Match: '+etag]
        return subprocess.run(args,**kw)
    def call(method,path,body=None): return _cli_request(cmd,origin,method,path,body,runner=runner)
    who=call('GET','WhoAmI')
    if str(who.get('OrganizationId','')).lower()!=org.lower(): raise ValueError('ENVIRONMENT_MISMATCH')
    q=call('GET','workqueues('+queue+')?$select=name,statecode,statuscode')
    if q.get('name')!='qmcp empty native dequeue probe' or q.get('statecode')!=0: raise ValueError('ISOLATED_PROBE_REQUIRED')
    bindings=call('GET',"qmcp_wqqueuebindings?$select=qmcp_key&$filter=qmcp_key eq '"+queue+"'&$top=2").get('value')
    if not isinstance(bindings,list) or bindings: raise ValueError('REGISTERED_QUEUE_NOT_ALLOWED')
    rows=call('GET','workqueueitems?$select=workqueueitemid&$filter=_workqueueid_value eq '+queue+'&$top=2').get('value')
    if not isinstance(rows,list) or len(rows)!=1 or rows[0]['workqueueitemid']!=item: raise ValueError('SOLE_PROBE_REQUIRED')
    path='workqueueitems('+item+')?$select=workqueueitemid,name,statecode,statuscode,expirydate,delayuntil,input,_workqueueid_value'
    original=call('GET',path)
    if original.get('name')!='qmcp synthetic native probe' or original.get('input')!='{}' or original.get('statecode')!=0 or original.get('_workqueueid_value')!=queue: raise ValueError('SYNTHETIC_ITEM_REQUIRED')
    etag=original.get('@odata.etag'); save(original=original)
    expiry=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'); save(testExpiry=expiry)
    changed=False
    try:
        changed=True; call('PATCH','workqueueitems('+item+')',{'expirydate':expiry})
        expired=call('GET',path); save(expired=expired)
        if expired.get('expirydate')!=expiry: raise ValueError('EXPIRY_NOT_APPLIED')
        result=call('POST','workqueues('+queue+')/Microsoft.Dynamics.CRM.Dequeue',{})
        after=call('GET',path); save(dequeue=result,after=after)
        if result.get('workqueueitemid') or after!=expired: raise ValueError('EXPIRED_ITEM_CHANGED_OR_CLAIMED')
        save(expiredItemNotClaimed=True)
    finally:
        if changed:
            current=call('GET',path); etag=current.get('@odata.etag')
            if current.get('expirydate') not in (expiry,original.get('expirydate')) or any(current.get(k)!=original.get(k) for k in ('statecode','statuscode','input','delayuntil')): raise ValueError('PROBE_CHANGED_RESTORE_REFUSED')
            call('PATCH','workqueueitems('+item+')',{'expirydate':original.get('expirydate')})
            restored=call('GET',path)
            if {k:v for k,v in restored.items() if k!='@odata.etag'}!={k:v for k,v in original.items() if k!='@odata.etag'}: raise ValueError('RESTORATION_NOT_VERIFIED')
            save(restored=restored,restorationVerified=True)
    if not e.get('expiredItemNotClaimed') or not e.get('restorationVerified'): raise ValueError('INCOMPLETE_PROOF')
    save(completed=True); print(json.dumps(e,indent=2))

if __name__=='__main__':
    try: main()
    except (ValueError,TypeError,KeyError,OSError) as err: raise SystemExit(str(err))
