import json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'scripts'))
from prove_direct_acquisition import exact_fault, main

class DirectAcquisitionProofTests(unittest.TestCase):
    def test_exact_structured_fault_is_distinct_from_generic(self):
        result=type('R',(),{'returncode':1,'stdout':json.dumps({'error':{'message':'ACQUISITION_HANDOFF_REQUIRED'}})})()
        generic=type('R',(),{'returncode':1,'stdout':'timeout'})()
        self.assertTrue(exact_fault(result)); self.assertFalse(exact_fault(generic))

    def test_dry_run_makes_no_output_or_calls(self):
        binding={"environmentUrl":"https://synthetic.crm.dynamics.com","organizationId":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","environmentClass":"development","queueKeys":["qmcp-proof-test"]}
        fixture={"queueKey":"qmcp-proof-test","queue":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","itemId":"cccccccc-cccc-cccc-cccc-cccccccccccc","user":"dddddddd-dddd-dddd-dddd-dddddddddddd"}
        with tempfile.TemporaryDirectory() as d:
            b=Path(d)/'b.json'; f=Path(d)/'f.json'; o=Path(d)/'o.json'; b.write_text(json.dumps(binding)); f.write_text(json.dumps(fixture))
            with patch('prove_direct_acquisition._cli_command',side_effect=AssertionError('network')):
                main(['--binding',str(b),'--fixture-ledger',str(f),'--output',str(o)])
            self.assertFalse(o.exists())

    def _run_execute(self, generic=False, changed=False):
        binding={"environmentUrl":"https://synthetic.crm.dynamics.com","organizationId":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","environmentClass":"development","queueKeys":["qmcp-proof-test"]}
        fixture={"queueKey":"qmcp-proof-test","queue":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","itemId":"cccccccc-cccc-cccc-cccc-cccccccccccc","user":"dddddddd-dddd-dddd-dddd-dddddddddddd"}
        with tempfile.TemporaryDirectory() as d:
            b=Path(d)/'b.json'; f=Path(d)/'f.json'; o=Path(d)/'o.json'; b.write_text(json.dumps(binding)); f.write_text(json.dumps(fixture)); item={"workqueueitemid":fixture["itemId"],"uniqueidbyqueue":"key","statecode":0,"statuscode":0,"_workqueueid_value":fixture["queue"],"@odata.etag":"W/\"1\""}; reads=[0]
            def req(command, origin, method, path, body=None, runner=None):
                if path=='WhoAmI': return {"OrganizationId":binding["organizationId"],"UserId":fixture["user"]}
                if path.startswith('workflows('): return {"statecode":0}
                if path.startswith('workqueueitems('):
                    reads[0]+=1; return {**item, "@odata.etag":"W/\"2\""} if changed and reads[0]>1 else item
                if path.startswith('qmcp_wqattempts'): return {"value":[]}
                if path.startswith('qmcp_wqcommands'): return {"value":[]}
                if path.startswith('qmcp_WQ_AcceptAcquire'):
                    if runner is not None:
                        runner(['cli'],capture_output=True,text=True,timeout=60,check=False)
                    raise ValueError('DATAVERSE_CLI_FAILED')
                raise AssertionError(path)
            result=type('R',(),{'returncode':1,'stdout':json.dumps({'error':{'message':'ACQUISITION_HANDOFF_REQUIRED'}}) if not generic else 'timeout'})()
            with patch('prove_direct_acquisition._cli_command',return_value=['cli']), patch('prove_direct_acquisition._cli_request',side_effect=req), patch('prove_direct_acquisition.subprocess.run',return_value=result):
                if generic:
                    with self.assertRaisesRegex(ValueError,'DIRECT_REJECTION_UNVERIFIED'): main(['--binding',str(b),'--fixture-ledger',str(f),'--output',str(o),'--execute'])
                elif changed:
                    with self.assertRaisesRegex(ValueError,'NATIVE_ITEM_MUTATED'): main(['--binding',str(b),'--fixture-ledger',str(f),'--output',str(o),'--execute'])
                else: main(['--binding',str(b),'--fixture-ledger',str(f),'--output',str(o),'--execute'])
            return json.loads(o.read_text())

    def test_mocked_exact_rejection_is_complete_without_mutation(self):
        evidence=self._run_execute(); self.assertTrue(evidence['completed']); self.assertEqual(0,evidence['attemptCount']); self.assertEqual(0,evidence['receiptCount'])

    def test_mocked_generic_failure_and_changed_item_cannot_pass(self):
        self.assertFalse(self._run_execute(generic=True)['completed'])
        self.assertFalse(self._run_execute(changed=True)['completed'])

if __name__=='__main__': unittest.main()
