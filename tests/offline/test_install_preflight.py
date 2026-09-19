import json
import re
import sys
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import preflight_installation as preflight

VALID = {'environmentUrl':'https://synthetic.crm.dynamics.com','organizationId':'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','environmentClass':'development','queueKeys':['mail']}

class PreflightTests(unittest.TestCase):
    def test_preflight_is_get_only_and_incomplete_when_metadata_missing(self):
        calls = []
        def request(command, origin, method, relative, **kwargs):
            calls.append((method, relative))
            if relative == 'WhoAmI': return {'OrganizationId': VALID['organizationId']}
            return {'value': []}
        with patch.object(preflight.bootstrap, '_cli_command', return_value=['dataverse']), patch.object(preflight.bootstrap, '_cli_request', side_effect=request):
            result = preflight.preflight(VALID)
        self.assertTrue(calls)
        self.assertTrue(all(method == 'GET' for method, _ in calls))
        self.assertFalse(result['ready'])
        self.assertFalse(result['writesPerformed'])
        self.assertFalse(result['clientdataIncluded'])
        self.assertEqual(result['manualPrerequisites']['licensesCapacity'], 'unknown')

    def test_wrong_organization_fails_before_metadata_reads(self):
        calls = []
        def request(command, origin, method, relative, **kwargs):
            calls.append(relative)
            return {'OrganizationId':'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'} if relative == 'WhoAmI' else {'value': []}
        with patch.object(preflight.bootstrap, '_cli_command', return_value=['dataverse']), patch.object(preflight.bootstrap, '_cli_request', side_effect=request):
            with self.assertRaisesRegex(ValueError, 'ENVIRONMENT_MISMATCH'):
                preflight.preflight(VALID)
        self.assertEqual(calls, ['WhoAmI'])

    def test_single_entity_definition_response_is_recorded(self):
        def request(command, origin, method, relative, **kwargs):
            if relative == 'WhoAmI': return {'OrganizationId': VALID['organizationId']}
            if relative.startswith("EntityDefinitions(LogicalName='qmcp_wqdefinition')"):
                return {'LogicalName':'qmcp_wqdefinition','EntitySetName':'qmcp_wqdefinitions','IsOptimisticConcurrencyEnabled':True,'Keys':[{'EntityKeyIndexStatus':'Active'}]}
            return {'value': []}
        with patch.object(preflight.bootstrap, '_cli_command', return_value=['dataverse']), patch.object(preflight.bootstrap, '_cli_request', side_effect=request):
            result = preflight.preflight(VALID)
        table = next(t for t in result['checks']['tables'] if t['logicalName'] == 'qmcp_wqdefinition')
        self.assertTrue(table['found'])
        self.assertEqual(table['keyStatus'], ['Active'])

    def test_complete_observable_state_is_still_not_ready_with_manual_unknowns(self):
        runtime, guard, acquisition = 'runtime-id', 'guard-id', 'acquisition-id'
        expected_refs = preflight._connection_expectations()
        def request(command, origin, method, relative, **kwargs):
            decoded = urllib.parse.unquote_plus(relative)
            if relative == 'WhoAmI': return {'OrganizationId': VALID['organizationId']}
            if relative.startswith('solutions?'):
                names = re.findall(r"uniquename eq '([^']+)'", decoded)
                return {'value':[{'uniquename':name,'version':'0.1.0.0','ismanaged':False} for name in names]}
            if relative.startswith('customapis?'):
                names = re.findall(r"uniquename eq '([^']+)'", decoded)
                return {'value':[{'uniquename':name,'_plugintypeid_value':runtime} for name in names]}
            if relative.startswith('plugintypes?'):
                types = re.findall(r"typename eq '([^']+)'", decoded)
                return {'value':[{'plugintypeid':runtime if typ.endswith('LifecyclePlugin') else acquisition if typ.endswith('AcquisitionPostPlugin') else guard,'typename':typ} for typ in types]}
            if relative.startswith('sdkmessageprocessingstepimages?'):
                return {'value':[{'sdkmessageprocessingstepimageid':relative.split('eq%20')[-1],'name':'Before','imagetype':0,'attributes':'statecode,workqueueid','_sdkmessageprocessingstepid_value':preflight.uid('acquisition-post:workqueueitem:Update'),'messagepropertyname':'Target'}]}
            if relative.startswith('sdkmessageprocessingsteps?'):
                post = preflight.uid('acquisition-post:workqueueitem:Update')
                ids = re.findall(r'sdkmessageprocessingstepid eq ([0-9a-f-]+)', decoded)
                return {'value':[{'sdkmessageprocessingstepid':ident,'stage':40 if ident==post else 20,'mode':0,'statecode':0,'_eventhandler_value':acquisition if ident==post else guard} for ident in ids]}
            if relative.startswith('EntityDefinitions('):
                return {'LogicalName':'qmcp_wqdefinition','EntitySetName':'qmcp_wqdefinitions','IsOptimisticConcurrencyEnabled':True,'Keys':[{'EntityKeyIndexStatus':'Active'}]}
            if relative.startswith('connectionreferences?'):
                logicals = re.findall(r"connectionreferencelogicalname eq '([^']+)'", decoded)
                return {'value':[{'connectionreferencelogicalname':logical,'connectorid':next(c for refs in expected_refs.values() for ref,c in refs.items() if ref == logical),'connectionid':'synthetic-connection'} for logical in logicals]}
            if relative.startswith('workflows?'):
                ids = re.findall(r'workflowid eq ([0-9a-f-]+)', decoded)
                return {'value':[{'workflowid':ident,'name':'flow','statecode':0,'statuscode':1} for ident in ids]}
            return {'value':[]}
        with patch.object(preflight.bootstrap, '_cli_command', return_value=['dataverse']), patch.object(preflight.bootstrap, '_cli_request', side_effect=request):
            result = preflight.preflight(VALID)
        self.assertTrue(result['observableComplete'])
        self.assertFalse(result['ready'])

    def test_active_event_flow_without_callback_registration_is_incomplete(self):
        def request(command, origin, method, relative, **kwargs):
            decoded = urllib.parse.unquote_plus(relative)
            if relative == 'WhoAmI': return {'OrganizationId': VALID['organizationId']}
            if relative.startswith('solutions?'):
                names = re.findall(r"uniquename eq '([^']+)'", decoded)
                return {'value':[{'uniquename':name,'version':'0.1.0.0','ismanaged':False} for name in names]}
            if relative.startswith('customapis?'):
                names = re.findall(r"uniquename eq '([^']+)'", decoded)
                return {'value':[{'uniquename':name,'_plugintypeid_value':'runtime-id'} for name in names]}
            if relative.startswith('plugintypes?'):
                types = re.findall(r"typename eq '([^']+)'", decoded)
                return {'value':[{'plugintypeid':'runtime-id' if typ.endswith('LifecyclePlugin') else 'acquisition-id' if typ.endswith('AcquisitionPostPlugin') else 'guard-id','typename':typ} for typ in types]}
            if relative.startswith('sdkmessageprocessingstepimages?'):
                return {'value':[{'name':'Before','imagetype':0,'attributes':'statecode,workqueueid','_sdkmessageprocessingstepid_value':preflight.uid('acquisition-post:workqueueitem:Update'),'messagepropertyname':'Target'}]}
            if relative.startswith('sdkmessageprocessingsteps?'):
                post = preflight.uid('acquisition-post:workqueueitem:Update')
                ids = re.findall(r'sdkmessageprocessingstepid eq ([0-9a-f-]+)', decoded)
                return {'value':[{'sdkmessageprocessingstepid':ident,'stage':40 if ident == post else 20,'mode':0,'statecode':0,'_eventhandler_value':'acquisition-id' if ident == post else 'guard-id'} for ident in ids]}
            if relative.startswith('EntityDefinitions('):
                return {'LogicalName':'qmcp_wqdefinition','EntitySetName':'qmcp_wqdefinitions','IsOptimisticConcurrencyEnabled':True,'Keys':[{'EntityKeyIndexStatus':'Active'}]}
            if relative.startswith('connectionreferences?'):
                logicals = re.findall(r"connectionreferencelogicalname eq '([^']+)'", decoded)
                return {'value':[{'connectionreferencelogicalname':logical,'connectorid':next(c for refs in preflight._connection_expectations().values() for ref,c in refs.items() if ref == logical),'connectionid':'synthetic-connection'} for logical in logicals]}
            if relative.startswith('workflows?'):
                ids = re.findall(r'workflowid eq ([0-9a-f-]+)', decoded)
                return {'value':[{'workflowid':ident,'name':'OnQueueChanged' if '656a2463' in ident else 'flow','statecode':1 if '656a2463' in ident else 0,'statuscode':2} for ident in ids]}
            if relative.startswith('callbackregistrations?'):
                return {'value':[]}
            return {'value':[]}
        with patch.object(preflight.bootstrap, '_cli_command', return_value=['dataverse']), patch.object(preflight.bootstrap, '_cli_request', side_effect=request):
            result = preflight.preflight(VALID)
        self.assertTrue(result['checks']['eventCallbackRegistration']['activeEventFlow'])
        self.assertFalse(result['checks']['eventCallbackRegistration']['present'])
        self.assertFalse(result['observableComplete'])

if __name__ == '__main__': unittest.main()
