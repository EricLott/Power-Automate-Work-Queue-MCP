"""First-import registration plan and opt-in executor. Never used by local build/tests.

Run without --execute to produce a reviewable plan. The executor requires a matching
organization ID and either an execution-time token or an authenticated Dataverse CLI. It does not import,
enable flows, grant roles, or register actor profiles implicitly.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from generate_sources import ROOT, uid

def plan():
    registration=json.loads((ROOT/'config/registration.json').read_text())
    apis=json.loads((ROOT/'config/api-catalog.json').read_text())
    manifest=json.loads((ROOT/'artifacts/packages/manifest.json').read_text())
    body={'version':1,'purpose':'first unmanaged development import only','packageManifest':manifest,
        'apiType':'QueueFramework.Plugins.LifecyclePlugin','guardType':'QueueFramework.Plugins.LifecycleGuard',
        'apis':['qmcp_WQ_'+op for op in apis['operations']],'guardSteps':registration['guardSteps'],
        'activation':False,'createsActorProfiles':False,'assignsSecurityRoles':False}
    body['planHash']=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return body

def _cli_command():
    """Run npm's JS entrypoint directly on Windows, avoiding .cmd shell parsing."""
    launcher=shutil.which('npx.cmd' if os.name=='nt' else 'npx')
    if not launcher:raise ValueError('DATAVERSE_CLI_REQUIRED')
    if os.name=='nt':
        node=shutil.which('node')
        entry=Path(launcher).parent/'node_modules/npm/bin/npx-cli.js'
        if not node or not entry.is_file():raise ValueError('DATAVERSE_CLI_REQUIRED')
        command=[node,str(entry)]
    else:command=[launcher]
    return command+['--yes','@microsoft/dataverse@1.0.77']

def _cli_request(command,origin,method,relative,body=None,solution='WQCore',runner=subprocess.run):
    if '://' in relative or relative.startswith('/'): raise ValueError('RELATIVE_PATH_REQUIRED')
    args=command+['api','request','--target','dataverse','--path',relative,'--method',method,
        '--header','Accept: application/json','--header','OData-MaxVersion: 4.0',
        '--header','OData-Version: 4.0','--header','MSCRM.SolutionUniqueName: '+solution,
        '--environment',origin]
    temporary=None
    try:
        if body is not None:
            temporary=tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',suffix='.json',delete=False)
            with temporary as stream:
                json.dump(body,stream,separators=(',',':'))
            args += ['--header','Content-Type: application/json','--body-file',temporary.name]
        try:
            result=runner(args,capture_output=True,text=True,timeout=60,check=False)
        except subprocess.TimeoutExpired:
            raise ValueError('DATAVERSE_CLI_TIMEOUT')
        if result.returncode:
            # CLI stderr can contain URLs, response bodies, or other sensitive details.
            raise ValueError('DATAVERSE_CLI_FAILED')
        output=result.stdout.strip()
        if not output: return {}
        try: return json.loads(output)
        except json.JSONDecodeError: raise ValueError('DATAVERSE_CLI_INVALID_RESPONSE')
    finally:
        if temporary:
            try: Path(temporary.name).unlink()
            except OSError: pass

def execute(binding,approved_hash,dataverse_cli=False,runner=None):
    p=plan()
    if p['planHash']!=approved_hash:raise ValueError('PLAN_STALE')
    origin=binding['environmentUrl'].rstrip('/');parsed=urllib.parse.urlparse(origin)
    if parsed.scheme!='https' or parsed.path or parsed.query or parsed.fragment or parsed.username or not parsed.hostname:raise ValueError('ENVIRONMENT_URL_INVALID')
    expected=str(uuid.UUID(binding['organizationId']))
    if binding.get('environmentClass')!='development':raise ValueError('DEVELOPMENT_ENVIRONMENT_REQUIRED')
    token=os.environ.get('QMCP_DATAVERSE_TOKEN')
    if not dataverse_cli and not token:raise ValueError('ACCESS_TOKEN_REQUIRED')
    for entry in p['packageManifest']['files']:
        if hashlib.sha256((ROOT/'artifacts/packages'/entry['file']).read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('PACKAGE_HASH_MISMATCH')
    base=origin+'/api/data/v9.2/'
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):raise ValueError('REDIRECT_DENIED')
    opener=urllib.request.build_opener(NoRedirect)
    cli_command=_cli_command() if dataverse_cli else None
    def request(method,relative,body=None,solution='WQCore'):
        if dataverse_cli:
            return _cli_request(cli_command,origin,method,relative,body,solution,runner or subprocess.run)
        if '://' in relative or relative.startswith('/'):raise ValueError('RELATIVE_PATH_REQUIRED')
        headers={'Authorization':'Bearer '+token,'Accept':'application/json','OData-MaxVersion':'4.0','OData-Version':'4.0','Content-Type':'application/json','MSCRM.SolutionUniqueName':solution}
        req=urllib.request.Request(base+relative,data=None if body is None else json.dumps(body).encode(),headers=headers,method=method)
        with opener.open(req,timeout=60) as response:
            data=response.read();return json.loads(data) if data else {}
    def query(entity,select,filter):return request('GET',entity+'?'+urllib.parse.urlencode({'$select':select,'$filter':filter,'$top':2}))['value']
    def one(rows):
        if len(rows)!=1:raise ValueError('REGISTRATION_NOT_UNIQUE')
        return rows[0]
    who=request('GET','WhoAmI')
    if str(who['OrganizationId']).lower()!=expected:raise ValueError('ENVIRONMENT_MISMATCH')
    runtime=one(query('plugintypes','plugintypeid',"typename eq '"+p['apiType']+"'"))['plugintypeid']
    guard=one(query('plugintypes','plugintypeid',"typename eq '"+p['guardType']+"'"))['plugintypeid']
    completed=[]
    for api in p['apis']:
        row=one(query('customapis','customapiid',"uniquename eq '"+api+"'"))
        request('PATCH','customapis('+row['customapiid']+')',{'plugintypeid@odata.bind':'/plugintypes('+runtime+')'},'WQTesting' if any(api.endswith(x) for x in ['StartTestRun','GetTestRun','AdvanceTestRun','CleanupTestRun']) else 'WQCore')
        completed.append(api)
    for specification in p['guardSteps']:
        table=specification['table']
        metadata=request('GET',"EntityDefinitions(LogicalName='"+table+"')?$select=ObjectTypeCode")
        for message in specification['messages']:
            msg=one(query('sdkmessages','sdkmessageid',"name eq '"+message+"'"))['sdkmessageid']
            filter=one(query('sdkmessagefilters','sdkmessagefilterid',"_sdkmessageid_value eq "+msg+" and primaryobjecttypecode eq "+str(metadata['ObjectTypeCode'])))['sdkmessagefilterid']
            step=uid('guard:'+table+':'+message)
            existing=query('sdkmessageprocessingsteps','sdkmessageprocessingstepid','sdkmessageprocessingstepid eq '+step)
            body={'name':'Queue framework guard: '+message+' '+table,'sdkmessageid@odata.bind':'/sdkmessages('+msg+')','sdkmessagefilterid@odata.bind':'/sdkmessagefilters('+filter+')','eventhandler_plugintype@odata.bind':'/plugintypes('+guard+')','stage':20,'mode':0,'rank':1,'supporteddeployment':0,'asyncautodelete':False}
            solution='WQTesting' if table in ['qmcp_wqtestcase','qmcp_wqtestrun','qmcp_wqtestresult'] else 'WQCore'
            if existing:request('PATCH','sdkmessageprocessingsteps('+step+')',body,solution)
            else:body['sdkmessageprocessingstepid']=step;request('POST','sdkmessageprocessingsteps',body,solution)
            completed.append(step)
    return {'organizationId':expected,'completed':completed,'flowsEnabled':False,'liveGates':'still-required','planHash':p['planHash']}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--dataverse-cli',action='store_true');parser.add_argument('--binding');parser.add_argument('--approved-plan-hash');args=parser.parse_args()
    try:
        if args.execute:
            if not args.binding or not args.approved_plan_hash:raise ValueError('BINDING_AND_APPROVED_PLAN_REQUIRED')
            print(json.dumps(execute(json.loads(Path(args.binding).read_text()),args.approved_plan_hash,args.dataverse_cli),indent=2))
        else:print(json.dumps(plan(),indent=2))
    except (ValueError,KeyError,OSError,urllib.error.HTTPError) as error:
        # Never print token, raw HTTP error body, or customer data.
        code=str(error) if re.fullmatch('[A-Z_]+',str(error)) else 'BOOTSTRAP_FAILED'
        raise SystemExit(code)
