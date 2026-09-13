import json
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
                name = next(n for n in ('WQCore','WQTesting','WQNotificationsEmail','WQReferenceSharedMailbox') if n in decoded)
                return {'value':[{'uniquename':name,'version':'0.1.0.0','ismanaged':False}]}
            if relative.startswith('customapis?'):
                name = decoded.split("'")[1]; return {'value':[{'uniquename':name,'_plugintypeid_value':runtime}]}
            if relative.startswith('plugintypes?'):
                typ = decoded.split("'")[1]; ident = runtime if typ.endswith('LifecyclePlugin') else acquisition if typ.endswith('AcquisitionPostPlugin') else guard
                return {'value':[{'plugintypeid':ident,'typename':typ}]}
            if relative.startswith('sdkmessageprocessingstepimages?'):
                return {'value':[{'sdkmessageprocessingstepimageid':relative.split('eq%20')[-1],'name':'Before','imagetype':0,'attributes':'statecode,workqueueid','_sdkmessageprocessingstepid_value':preflight.uid('acquisition-post:workqueueitem:Update'),'messagepropertyname':'Target'}]}
            if relative.startswith('sdkmessageprocessingsteps?'):
                post = preflight.uid('acquisition-post:workqueueitem:Update'); ident = post if post in decoded else 'guard'
                return {'value':[{'sdkmessageprocessingstepid':ident,'stage':40 if ident==post else 20,'mode':0,'statecode':0,'_eventhandler_value':acquisition if ident==post else guard}]}
            if relative.startswith('EntityDefinitions('):
                return {'LogicalName':'qmcp_wqdefinition','EntitySetName':'qmcp_wqdefinitions','IsOptimisticConcurrencyEnabled':True,'Keys':[{'EntityKeyIndexStatus':'Active'}]}
            if relative.startswith('connectionreferences?'):
                logical = decoded.split("'")[1]
                connector = next(c for refs in expected_refs.values() for ref,c in refs.items() if ref == logical)
                return {'value':[{'connectionreferencelogicalname':logical,'connectorid':connector,'connectionid':'synthetic-connection'}]}
            if relative.startswith('workflows?'):
                return {'value':[{'name':'flow','statecode':0,'statuscode':1}]}
            return {'value':[]}
        with patch.object(preflight.bootstrap, '_cli_command', return_value=['dataverse']), patch.object(preflight.bootstrap, '_cli_request', side_effect=request):
            result = preflight.preflight(VALID)
        self.assertTrue(result['observableComplete'])
        self.assertFalse(result['ready'])

if __name__ == '__main__': unittest.main()
