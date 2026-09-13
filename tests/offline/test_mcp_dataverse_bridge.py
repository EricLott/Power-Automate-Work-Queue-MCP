import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import mcp_dataverse

BINDING = {'environmentUrl':'https://synthetic.crm.dynamics.com','organizationId':'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','environmentClass':'development','queueKeys':['mail']}
BODY = {'QueueKey':'mail','RequestId':'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb','DataJson':'{}'}

class BridgeTests(unittest.TestCase):
    def fake(self, calls, identity=None):
        def call(command, origin, method, relative, body=None, **kwargs):
            calls.append((method, relative, body))
            if relative == 'WhoAmI': return {'OrganizationId': identity or BINDING['organizationId']}
            return {'ResultJson':'{"Outcome":"Health"}'}
        return call

    def test_whoami_is_get_only(self):
        calls=[]
        with patch.object(mcp_dataverse, '_cli_command', return_value=['dataverse']), patch.object(mcp_dataverse, '_cli_request', side_effect=self.fake(calls)):
            self.assertEqual(mcp_dataverse.request({'binding':BINDING,'route':'WhoAmI'}), {'OrganizationId':BINDING['organizationId']})
        self.assertEqual(calls, [('GET','WhoAmI',None)])

    def test_wrong_org_fails_before_mutation(self):
        calls=[]
        with patch.object(mcp_dataverse, '_cli_command', return_value=['dataverse']), patch.object(mcp_dataverse, '_cli_request', side_effect=self.fake(calls, 'cccccccc-cccc-cccc-cccc-cccccccccccc')):
            with self.assertRaisesRegex(ValueError, 'ENVIRONMENT_MISMATCH'):
                mcp_dataverse.request({'binding':BINDING,'route':'qmcp_WQ_Enqueue','body':BODY})
        self.assertEqual([c[0] for c in calls], ['GET'])

    def test_operation_and_queue_allowlists(self):
        for route, error in [('qmcp_WQ_DeleteAll','OPERATION_NOT_EXPOSED'),('qmcp_WQ_Enqueue','QUEUE_NOT_BOUND')]:
            body = dict(BODY, QueueKey='other') if error == 'QUEUE_NOT_BOUND' else BODY
            with self.assertRaisesRegex(ValueError, error): mcp_dataverse.request({'binding':BINDING,'route':route,'body':body})

    def test_cli_failure_is_safe(self):
        def fail(*args, **kwargs): raise ValueError('DATAVERSE_CLI_FAILED')
        with patch.object(mcp_dataverse, '_cli_command', return_value=['dataverse']), patch.object(mcp_dataverse, '_cli_request', side_effect=fail):
            with self.assertRaisesRegex(ValueError, 'DATAVERSE_CLI_FAILED'): mcp_dataverse.request({'binding':BINDING,'route':'WhoAmI'})

if __name__ == '__main__': unittest.main()
