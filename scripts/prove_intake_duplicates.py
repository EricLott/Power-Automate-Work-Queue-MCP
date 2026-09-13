"""Opt-in synthetic tenant intake proof; no customer business actions."""
import argparse, datetime, hashlib, json, subprocess, uuid
from pathlib import Path
from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding


def safe_error(stdout, returncode):
    if returncode == 0: return ''
    try:
        error = json.loads(stdout).get('error')
        message = error.get('message') if isinstance(error, dict) else error
    except (ValueError, TypeError, AttributeError): message = None
    return 'KEY_CONTENT_CONFLICT' if message == 'KEY_CONTENT_CONFLICT' else 'DATAVERSE_CLI_FAILED'


def prove(call, queue, proof, note):
    ids = {k: str(uuid.uuid5(uuid.UUID(proof), k)) for k in ('first','duplicate','conflict')}
    source = 'intake-proof-' + proof
    key = hashlib.sha256((queue + '|' + source).encode()).hexdigest()
    envelope = {'envelopeVersion':'1.0','contract':'mail.v1','correlationId':proof,'deduplicationKey':source,
        'source':{'kind':'synthetic'},'payload':{'subject':'Synthetic duplicate proof',
        'senderAddress':'synthetic@example.invalid','bodyText':'Synthetic validation only.'}}
    note(requestIds=ids, nativeUniqueKey=key)
    def api(label, payload):
        response = call('POST','qmcp_WQ_Enqueue',{'QueueKey':queue,'RequestId':ids[label],
            'DataJson':json.dumps(payload,separators=(',',':'))})
        return json.loads(response['ResultJson'])
    def native():
        return call('GET',"workqueueitems?$select=workqueueitemid,input,statecode&$filter=uniqueidbyqueue eq '"+key+"'")['value']
    if native(): raise ValueError('PROOF_KEY_ALREADY_EXISTS')
    first = api('first',envelope); note(first=first)
    if first.get('Outcome') != 'Enqueued' or not first.get('ItemId'): raise ValueError('ENQUEUE_NOT_CONFIRMED')
    before = native()
    if len(before) != 1 or before[0]['workqueueitemid'] != first['ItemId']: raise ValueError('NATIVE_ITEM_COUNT_INVALID')
    before_hash = hashlib.sha256(before[0]['input'].encode()).hexdigest()
    duplicate = api('duplicate',envelope); note(duplicate=duplicate)
    if duplicate.get('Outcome') != 'Existing' or duplicate.get('ItemId') != first['ItemId']: raise ValueError('DUPLICATE_NOT_CONFIRMED')
    changed = {**envelope,'payload':{**envelope['payload'],'subject':'Synthetic changed content'}}
    try: api('conflict',changed)
    except ValueError as error:
        if str(error) != 'KEY_CONTENT_CONFLICT': raise
        note(conflictCode='KEY_CONTENT_CONFLICT')
    else: raise ValueError('CONFLICT_NOT_REJECTED')
    after = native()
    if len(after) != 1 or after[0]['workqueueitemid'] != first['ItemId'] or after[0]['statecode'] != 0: raise ValueError('NATIVE_ITEM_CHANGED')
    after_hash = hashlib.sha256(after[0]['input'].encode()).hexdigest()
    if before_hash != after_hash: raise ValueError('NATIVE_INPUT_CHANGED')
    note(nativeCountBefore=len(before),nativeCountAfter=len(after),nativeState=after[0]['statecode'],
        inputSha256Before=before_hash,inputSha256After=after_hash,completed=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binding','queue-key','output'): parser.add_argument('--'+name,required=True)
    parser.add_argument('--execute',action='store_true'); args=parser.parse_args()
    binding=json.loads(Path(args.binding).read_text(encoding='utf-8-sig')); origin,expected=_validate_binding(binding)
    if args.queue_key not in binding.get('queueKeys',[]) or not args.queue_key.startswith('qmcp-proof-'): raise ValueError('SYNTHETIC_QUEUE_NOT_BOUND')
    if not args.execute: print(json.dumps({'ready':True,'liveCalls':False})); return
    out=Path(args.output)
    evidence={'classification':'live-native-intake-duplicate-conflict','proofId':str(uuid.uuid4()),
        'organizationId':expected,'queueKey':args.queue_key,'completed':False,
        'startedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'cleanup':'Synthetic queued item retained; no business action or deletion.'}
    with out.open('x',encoding='utf-8') as stream: json.dump(evidence,stream,indent=2)
    def note(**values):
        evidence.update(values); out.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    def runner(*values,**options):
        result=subprocess.run(*values,**options)
        if result.returncode: raise ValueError(safe_error(result.stdout,result.returncode))
        return result
    command=_cli_command()
    def call(method,relative,body=None): return _cli_request(command,origin,method,relative,body,runner=runner)
    try:
        identity=call('GET','WhoAmI')
        if str(identity.get('OrganizationId','')).lower()!=expected.lower(): raise ValueError('ENVIRONMENT_MISMATCH')
        note(verifiedOrganizationId=identity['OrganizationId']); prove(call,args.queue_key,evidence['proofId'],note)
    except Exception as error:
        code=str(error) if isinstance(error,ValueError) and str(error).replace('_','').isalpha() and str(error).isupper() else 'PROOF_INCONCLUSIVE'
        note(error=code,completed=False); raise SystemExit(1)
    finally: print(json.dumps(evidence,indent=2))

if __name__=='__main__': main()
