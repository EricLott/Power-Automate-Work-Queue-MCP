import json
import os
import urllib.parse
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
import bootstrap_tenant as bootstrap

class BootstrapTests(unittest.TestCase):
    def test_plan_is_stable_and_never_activates(self):
        a=bootstrap.plan();b=bootstrap.plan();self.assertEqual(a['planHash'],b['planHash']);self.assertFalse(a['activation']);self.assertGreaterEqual(len(a['apis']),19)
    def test_stale_plan_cannot_open_network(self):
        with patch('urllib.request.build_opener') as network:
            with self.assertRaisesRegex(ValueError,'PLAN_STALE'):bootstrap.execute({},'wrong')
            network.assert_not_called()
    def test_production_target_rejected_before_credentials(self):
        with patch('urllib.request.build_opener') as network:
            binding={'environmentUrl':'https://synthetic.crm.dynamics.com','organizationId':'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','environmentClass':'production'}
            with self.assertRaisesRegex(ValueError,'DEVELOPMENT_ENVIRONMENT_REQUIRED'):bootstrap.execute(binding,bootstrap.plan()['planHash'])
            network.assert_not_called()
    def test_no_credential_execution_is_denied(self):
        with patch.dict('os.environ',{},clear=True),patch('urllib.request.build_opener') as network:
            binding={'environmentUrl':'https://synthetic.crm.dynamics.com','organizationId':'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','environmentClass':'development'}
            with self.assertRaisesRegex(ValueError,'ACCESS_TOKEN_REQUIRED'):bootstrap.execute(binding,bootstrap.plan()['planHash'])
            network.assert_not_called()
    def test_wrong_organization_cannot_reach_registration(self):
        binding={'environmentUrl':'https://synthetic.crm.dynamics.com','organizationId':'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','environmentClass':'development'}
        with patch.dict('os.environ',{'QMCP_DATAVERSE_TOKEN':'synthetic-test-token'},clear=True),patch('urllib.request.build_opener') as network:
            network.return_value.open.return_value.__enter__.return_value.read.return_value=json.dumps({'OrganizationId':'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'}).encode()
            with self.assertRaisesRegex(ValueError,'ENVIRONMENT_MISMATCH'):
                bootstrap.execute(binding,bootstrap.plan()['planHash'])
            calls=network.return_value.open.call_args_list
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0].args[0].get_method(),'GET')
            self.assertTrue(calls[0].args[0].full_url.endswith('/WhoAmI'))

    def test_dataverse_cli_wrong_organization_cannot_reach_registration(self):
        binding={'environmentUrl':'https://synthetic.crm.dynamics.com','organizationId':'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','environmentClass':'development'}
        calls=[]
        def runner(args,**kwargs):
            calls.append(args)
            return type('Result',(),{'returncode':0,'stdout':json.dumps({'OrganizationId':'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'}),'stderr':''})()
        with patch.dict('os.environ',{},clear=True),patch.object(bootstrap,'_cli_command',return_value=['dataverse']):
            with self.assertRaisesRegex(ValueError,'ENVIRONMENT_MISMATCH'):
                bootstrap.execute(binding,bootstrap.plan()['planHash'],dataverse_cli=True,runner=runner)
        self.assertEqual(len(calls),1)
        self.assertIn('--target',calls[0]);self.assertIn('dataverse',calls[0])

    def test_dataverse_cli_body_file_is_removed(self):
        observed={}
        def runner(args,**kwargs):
            path=args[args.index('--body-file')+1]
            observed['path']=path
            observed['exists_during']=os.path.exists(path)
            with open(path,encoding='utf-8') as stream: observed['body']=json.load(stream)
            return type('Result',(),{'returncode':0,'stdout':'{}','stderr':'secret must not escape'})()
        result=bootstrap._cli_request(['dataverse'],'https://synthetic.crm.dynamics.com','PATCH','customapis(id)',{'x':1},runner=runner)
        self.assertEqual(result,{})
        self.assertTrue(observed['exists_during']);self.assertEqual(observed['body'],{'x':1})
        self.assertFalse(os.path.exists(observed['path']))

    def test_dataverse_cli_uses_web_api_path_prefix(self):
        seen={}
        def runner(args,**kwargs):
            seen['args']=args
            return type('Result',(),{'returncode':0,'stdout':'{}','stderr':''})()
        bootstrap._cli_request(['dataverse'],'https://synthetic.crm.dynamics.com','GET','WhoAmI',runner=runner)
        self.assertEqual(seen['args'][seen['args'].index('--path')+1],'/api/data/v9.2/WhoAmI')

    def test_cli_registration_uses_logical_name_and_case_sensitive_binding(self):
        expected='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        fixture={'planHash':'hash','packageManifest':{'files':[]},'apiType':'Runtime','guardType':'Guard',
            'acquisitionPostType':'AcquisitionPost','acquisitionPostStep':{'table':'workqueueitem','message':'Update','stage':40,'mode':0,
                'preImage':{'name':'Before','imageType':0,'attributes':'statecode,workqueueid'}},
            'apis':['DoThing'],'guardSteps':[{'table':'account','messages':['Create']}]}
        calls=[]
        patch_bodies=[]
        def runner(args,**kwargs):
            path=args[args.index('--path')+1];calls.append(path)
            if '--body-file' in args:
                with open(args[args.index('--body-file')+1],encoding='utf-8') as stream: patch_bodies.append(json.load(stream))
            if path.endswith('/WhoAmI'): value={'OrganizationId':expected}
            elif path.startswith('/api/data/v9.2/plugintypes?') and 'Runtime' in path: value={'value':[{'plugintypeid':'runtime'}]}
            elif path.startswith('/api/data/v9.2/plugintypes?'): value={'value':[{'plugintypeid':'guard'}]}
            elif 'customapis?' in path: value={'value':[{'customapiid':'api'}]}
            elif "EntityDefinitions(LogicalName='account')" in path: value={'ObjectTypeCode':1}
            elif "EntityDefinitions(LogicalName='workqueueitem')" in path: value={'ObjectTypeCode':150}
            elif 'sdkmessages?' in path: value={'value':[{'sdkmessageid':'message'}]}
            elif 'sdkmessagefilters?' in path: value={'value':[{'sdkmessagefilterid':'filter'}]}
            elif 'sdkmessageprocessingsteps?' in path: value={'value':[]}
            elif 'sdkmessageprocessingstepimages?' in path: value={'value':[]}
            else: value={}
            return type('Result',(),{'returncode':0,'stdout':json.dumps(value),'stderr':''})()
        binding={'environmentUrl':'https://synthetic.crm.dynamics.com','organizationId':expected,'environmentClass':'development'}
        with patch.dict('os.environ',{},clear=True),patch.object(bootstrap,'plan',return_value=fixture),patch.object(bootstrap,'_cli_command',return_value=['dataverse']):
            bootstrap.execute(binding,'hash',dataverse_cli=True,runner=runner)
        filters=[path for path in calls if 'sdkmessagefilters?' in path]
        self.assertEqual(len(filters),2)
        decoded_filters=[urllib.parse.unquote_plus(path) for path in filters]
        self.assertTrue(any("primaryobjecttypecode eq 'account'" in path for path in decoded_filters))
        self.assertTrue(any("primaryobjecttypecode eq 'workqueueitem'" in path for path in decoded_filters))
        self.assertTrue(all(path.startswith('/api/data/v9.2/') for path in calls))
        self.assertTrue(any('PluginTypeId@odata.bind' in body for body in patch_bodies))
        self.assertFalse(any('plugintypeid@odata.bind' in body for body in patch_bodies))
        images=[body for body in patch_bodies if 'imagetype' in body]
        self.assertEqual(len(images),1)
        self.assertEqual(images[0]['messagepropertyname'],'Target')

    def test_plan_contains_deterministic_acquisition_post_step(self):
        plan=bootstrap.plan()
        step=plan['acquisitionPostStep']
        self.assertEqual(plan['acquisitionPostType'],'QueueFramework.Plugins.AcquisitionPostPlugin')
        self.assertEqual(step,{'table':'workqueueitem','message':'Update','stage':40,'mode':0,
                               'preImage':{'name':'Before','imageType':0,'attributes':'statecode,workqueueid'}})
        self.assertRegex(bootstrap.uid('acquisition-post:workqueueitem:Update'),r'^[0-9a-f-]{36}$')
