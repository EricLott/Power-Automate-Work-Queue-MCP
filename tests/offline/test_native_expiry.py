import json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'scripts'))
from prove_native_expiry import main

class NativeExpiryTests(unittest.TestCase):
    binding={"environmentUrl":"https://synthetic.crm.dynamics.com","organizationId":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","environmentClass":"development","queueKeys":["qmcp-proof-test"]}
    fixture={"queueId":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","itemId":"cccccccc-cccc-cccc-cccc-cccccccccccc"}
    def test_dry_run_makes_no_cli_or_output(self):
        with tempfile.TemporaryDirectory() as d:
            b=Path(d)/'b'; f=Path(d)/'f'; o=Path(d)/'o'; b.write_text(json.dumps(self.binding)); f.write_text(json.dumps(self.fixture))
            with patch('prove_native_expiry._cli_command',side_effect=AssertionError('cli')): main(['--binding',str(b),'--fixture',str(f),'--output',str(o)])
            self.assertFalse(o.exists())
    def _execute(self, generic=False):
        with tempfile.TemporaryDirectory() as d:
            b=Path(d)/'b'; f=Path(d)/'f'; o=Path(d)/'o'; b.write_text(json.dumps(self.binding)); f.write_text(json.dumps(self.fixture)); expiry='2026-01-01T00:00:00Z'; original={"workqueueitemid":self.fixture['itemId'],"name":"qmcp synthetic native probe","statecode":0,"statuscode":0,"expirydate":None,"delayuntil":None,"input":"{}","_workqueueid_value":self.fixture['queueId'],"@odata.etag":"W/\"1\""}; current=dict(original); patches=[]
            def req(command,origin,method,path,body=None,**kwargs):
                if path=='WhoAmI': return {"OrganizationId":self.binding['organizationId']}
                if path.endswith('/Microsoft.Dynamics.CRM.Dequeue'):
                    if generic: raise ValueError('DATAVERSE_CLI_FAILED')
                    return {}
                if path.startswith('workqueues('): return {"name":"qmcp empty native dequeue probe","statecode":0,"statuscode":1}
                if path.startswith('qmcp_wqqueuebindings'): return {"value":[]}
                if path.startswith('workqueueitems?'): return {"value":[{"workqueueitemid":self.fixture['itemId']}]}
                if path.startswith('workqueueitems(') and method=='GET': return dict(current)
                if path.startswith('workqueueitems(') and method=='PATCH': current['expirydate']=body['expirydate']; patches.append(body); return {}
                raise AssertionError(path)
            with patch('prove_native_expiry._cli_command',return_value=['cli']), patch('prove_native_expiry._cli_request',side_effect=req):
                if generic:
                    with self.assertRaisesRegex(ValueError,'DATAVERSE_CLI_FAILED'): main(['--binding',str(b),'--fixture',str(f),'--output',str(o),'--execute'])
                else: main(['--binding',str(b),'--fixture',str(f),'--output',str(o),'--execute'])
            evidence=json.loads(o.read_text()); self.assertTrue(evidence['restorationVerified']); self.assertFalse(evidence['completed']) if generic else self.assertTrue(evidence['completed']); self.assertGreaterEqual(len(patches),2)
    def test_empty_dequeue_expiry_restores_and_completes(self): self._execute()
    def test_generic_dequeue_error_restores_but_cannot_pass(self): self._execute(True)
if __name__=='__main__': unittest.main()
