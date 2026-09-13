"""Read-only live installation preflight via the authenticated Dataverse CLI."""
import argparse
import hashlib
import json
import sys
import re
import urllib.parse
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap_tenant as bootstrap
from generate_sources import ROOT, uid

FLOW_NAMES = ['ProcessOne', 'OnQueueChanged', 'SweepQueue', 'Intake', 'Watchdog', 'TestCoordinator', 'EmailSender']
TABLES = ['wqdefinition','wqqueuebinding','wqcontract','wqitemcontext','wqattempt','wqcommand','wqevent','wqcursor','wqintakefailure','wqprincipal','wqtestcase','wqtestrun','wqtestresult','emailrequest']

def _binding(binding):
    try: origin = binding['environmentUrl'].rstrip('/'); expected = str(uuid.UUID(binding['organizationId'])).lower()
    except (KeyError, ValueError): raise ValueError('BINDING_INVALID')
    parsed = urllib.parse.urlparse(origin)
    if parsed.scheme != 'https' or parsed.path or parsed.query or parsed.fragment or parsed.username or not parsed.hostname: raise ValueError('ENVIRONMENT_URL_INVALID')
    if binding.get('environmentClass') != 'development': raise ValueError('DEVELOPMENT_ENVIRONMENT_REQUIRED')
    if not isinstance(binding.get('queueKeys'), list) or not binding['queueKeys']: raise ValueError('QUEUE_ALLOWLIST_REQUIRED')
    return origin, expected

def _connection_expectations():
    result = {}
    for package in ['WQCore','WQTesting','WQNotificationsEmail','WQReferenceSharedMailbox']:
        path = ROOT/'solutions'/package/'src/Other/Customizations.xml'
        root = ET.parse(path).getroot()
        result[package] = {x.get('connectionreferencelogicalname'): x.findtext('connectorid') for x in root.findall('./connectionreferences/connectionreference')}
    return result

def preflight(binding, runner=None):
    origin, expected = _binding(binding)
    command = bootstrap._cli_command()
    def get(relative, solution='WQCore'):
        return bootstrap._cli_request(command, origin, 'GET', relative, solution=solution, runner=runner) if runner else bootstrap._cli_request(command, origin, 'GET', relative, solution=solution)
    who = get('WhoAmI')
    try: actual = str(uuid.UUID(who['OrganizationId'])).lower()
    except (KeyError, ValueError): raise ValueError('ENVIRONMENT_MISMATCH')
    if actual != expected: raise ValueError('ENVIRONMENT_MISMATCH')
    unknown = []
    def query(entity, select, filter_text, top=2, solution='WQCore', expand=None):
        params={'$select':select} if entity.startswith('EntityDefinitions(') else {'$select':select, '$filter':filter_text, '$top':top}
        if expand: params['$expand']=expand
        qs = urllib.parse.urlencode(params)
        try:
            response=get(entity+'?'+qs, solution)
            if 'value' in response: return response.get('value') or []
            return [response] if entity.startswith('EntityDefinitions(') else []
        except ValueError as error:
            unknown.append({'resource':entity, 'reason':str(error) if str(error).isupper() else 'READ_FAILED'}); return []
    release = json.loads((ROOT/'config/release.json').read_text())
    manifest = json.loads((ROOT/'artifacts/packages/manifest.json').read_text())
    packages=[]
    expected_files={f'{p["name"]}{suffix}.zip' for p in release['packages'] for suffix in ('','_managed')}
    entries=manifest.get('files',[])
    if (manifest.get('version') != release.get('version') or not isinstance(entries,list) or len(entries) != len(expected_files)
            or len({e.get('file') for e in entries if isinstance(e,dict)}) != len(entries)
            or any(not isinstance(e,dict) or e.get('file') not in expected_files or '/' in e.get('file','') or '\\' in e.get('file','')
                   or not isinstance(e.get('sha256'),str) or not re.fullmatch(r'[0-9a-fA-F]{64}',e['sha256']) for e in entries)):
        raise ValueError('INSTALL_MANIFEST_INVALID')
    for entry in entries:
        file=entry.get('file',''); path=ROOT/'artifacts/packages'/file
        actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        packages.append({'file':file,'expectedSha256':entry.get('sha256'),'actualSha256':actual,'status':'verified-local' if actual and actual.lower()==str(entry.get('sha256','')).lower() else 'missing' if actual is None else 'tampered'})
    expected_solutions = {p['name']: release['version'] for p in release['packages']}
    solutions=[]
    for name in expected_solutions:
        rows=query('solutions','uniquename,version,ismanaged',"uniquename eq '"+name+"'")
        solutions += [{'uniqueName':r.get('uniquename'),'version':r.get('version'),'isManaged':r.get('ismanaged')} for r in rows]
    api_names=['qmcp_WQ_'+x for x in json.loads((ROOT/'config/api-catalog.json').read_text())['operations']]
    apis=[]
    for name in api_names:
        rows=query('customapis','uniquename,_plugintypeid_value',"uniquename eq '"+name+"'")
        apis += [{'uniqueName':r.get('uniquename'),'bound':bool(r.get('_plugintypeid_value')),'pluginTypeId':r.get('_plugintypeid_value')} for r in rows]
    steps=[]
    registration=json.loads((ROOT/'config/registration.json').read_text())
    registration_plan=bootstrap.plan(); runtime_type=registration_plan['apiType']; guard_type=registration_plan['guardType']; acquisition_type=registration_plan['acquisitionPostType']
    runtime_rows=query('plugintypes','plugintypeid,typename',"typename eq '"+runtime_type+"'",top=1)
    guard_rows=query('plugintypes','plugintypeid,typename',"typename eq '"+guard_type+"'",top=1)
    acquisition_rows=query('plugintypes','plugintypeid,typename',"typename eq '"+acquisition_type+"'",top=1)
    runtime_id=runtime_rows[0].get('plugintypeid') if runtime_rows else None; guard_id=guard_rows[0].get('plugintypeid') if guard_rows else None; acquisition_id=acquisition_rows[0].get('plugintypeid') if acquisition_rows else None
    for spec in registration['guardSteps']:
        for message in spec['messages']:
            sid=uid('guard:'+spec['table']+':'+message); rows=query('sdkmessageprocessingsteps','sdkmessageprocessingstepid,name,stage,mode,statecode,statuscode,_eventhandler_value','sdkmessageprocessingstepid eq '+sid)
            row=rows[0] if rows else {}; steps.append({'id':sid,'kind':'guard','table':spec['table'],'message':message,'found':bool(rows),'correct':bool(rows and row.get('stage')==20 and row.get('mode')==0 and row.get('statecode')==0 and row.get('_eventhandler_value')==guard_id)})
    post=uid('acquisition-post:workqueueitem:Update'); image=uid('acquisition-post:workqueueitem:Update:Before')
    post_rows=query('sdkmessageprocessingsteps','sdkmessageprocessingstepid,stage,mode,statecode,_eventhandler_value','sdkmessageprocessingstepid eq '+post)
    image_rows=query('sdkmessageprocessingstepimages','sdkmessageprocessingstepimageid,name,imagetype,attributes,_sdkmessageprocessingstepid_value,messagepropertyname','sdkmessageprocessingstepimageid eq '+image)
    steps += [{'id':post,'kind':'acquisition-post','found':bool(post_rows),'correct':bool(post_rows and post_rows[0].get('stage')==40 and post_rows[0].get('mode')==0 and post_rows[0].get('statecode')==0 and post_rows[0].get('_eventhandler_value')==acquisition_id)},{'id':image,'kind':'acquisition-preimage','found':bool(image_rows),'correct':bool(image_rows and image_rows[0].get('name')=='Before' and image_rows[0].get('imagetype')==0 and image_rows[0].get('attributes')=='statecode,workqueueid' and image_rows[0].get('_sdkmessageprocessingstepid_value')==post and image_rows[0].get('messagepropertyname')=='Target')}]
    tables=[]
    for logical in TABLES:
        name='qmcp_'+logical
        rows=query('EntityDefinitions(LogicalName='+"'"+name+"'"+')','LogicalName,EntitySetName,OwnershipType,IsOptimisticConcurrencyEnabled','LogicalName eq '+"'"+name+"'",top=1,expand='Keys($select=EntityKeyIndexStatus,SchemaName)')
        keys=rows[0].get('Keys',[]) if rows else []
        tables.append({'logicalName':name,'found':bool(rows),'optimisticConcurrency':rows[0].get('IsOptimisticConcurrencyEnabled') if rows else None,'keyStatus':sorted({k.get('EntityKeyIndexStatus') for k in keys if k.get('EntityKeyIndexStatus')}) or None})
    refs={}
    for package, expected_refs in _connection_expectations().items():
        refs[package]={'expected':expected_refs,'found':[]}
        for ref, connector_id in expected_refs.items():
            rows=query('connectionreferences','connectionreferencelogicalname,connectorid,connectionid',"connectionreferencelogicalname eq '"+ref+"'",top=1)
            refs[package]['found'] += [{'logicalName':r.get('connectionreferencelogicalname'),'connectorId':r.get('connectorid'),'mapped':bool(r.get('connectionid')),'correct':bool(r.get('connectionid')) and bool(r.get('connectorid')) and r.get('connectorid')==connector_id} for r in rows]
    flows=[]
    for name in FLOW_NAMES:
        fid=uid('flow:'+name); rows=query('workflows','workflowid,name,statecode,statuscode,category','workflowid eq '+fid,top=1)
        flows.append({'name':name,'id':fid,'found':bool(rows),'statecode':rows[0].get('statecode') if rows else None,'statuscode':rows[0].get('statuscode') if rows else None})
    checks={'solutions':solutions,'apis':apis,'tables':tables,'registrationSteps':steps,'connectionReferences':refs,'flows':flows}
    observable_complete=not unknown and all(s.get('uniqueName') in expected_solutions and s.get('version')==expected_solutions.get(s.get('uniqueName')) for s in solutions) and len(solutions)==len(expected_solutions) and len(apis)==len(api_names) and all(a['bound'] and a.get('pluginTypeId')==runtime_id for a in apis) and all(t['found'] and t.get('optimisticConcurrency') is True and t.get('keyStatus')==['Active'] for t in tables) and all(s['found'] and s.get('correct') for s in steps) and all(f['found'] for f in flows) and all(len(v['found'])==len(v['expected']) and all(x.get('correct') for x in v['found']) for v in refs.values()) and all(p['status']=='verified-local' for p in packages)
    manual={'licensesCapacity':'unknown','targetUserPrivileges':'unknown','connectionOwnership':'unknown'}
    return {'classification':'read-only-live-installation-preflight','organizationId':expected,'environmentUrl':origin,'releaseVersion':release['version'],'manifestVersion':manifest.get('version'),'packages':packages,'checks':checks,'manualPrerequisites':manual,'unknown':unknown,'observableComplete':observable_complete,'ready':False,'writesPerformed':False,'clientdataIncluded':False}

if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--binding',required=True); args=parser.parse_args()
    try: print(json.dumps(preflight(json.loads(Path(args.binding).read_text())),indent=2))
    except (ValueError,KeyError,OSError,json.JSONDecodeError): raise SystemExit('INSTALL_PREFLIGHT_FAILED')
