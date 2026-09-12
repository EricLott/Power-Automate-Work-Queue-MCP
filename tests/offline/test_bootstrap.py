import json
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
