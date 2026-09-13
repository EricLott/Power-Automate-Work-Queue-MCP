import json, sys, tempfile, unittest
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'scripts'))
from prove_native_queue_pause import main, validate, is_paused_error
class NativeQueuePauseTests(unittest.TestCase):
    binding={"environmentUrl":"https://synthetic.crm.dynamics.com","organizationId":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","environmentClass":"development","queueKeys":["qmcp-proof-test"]}
    fixture={"queueKey":"qmcp-proof-test","queue":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb","itemId":"cccccccc-cccc-cccc-cccc-cccccccccccc"}
    def test_validate_requires_bound_synthetic_ids(self):
        with self.assertRaisesRegex(ValueError,'SYNTHETIC_QUEUE'): validate(self.binding,{**self.fixture,'queueKey':'mail'})
        with self.assertRaisesRegex(ValueError,'NATIVE_QUEUE_ID'): validate(self.binding,{**self.fixture,'queue':'bad'})
    def test_dry_run_makes_no_output(self):
        with tempfile.TemporaryDirectory() as d:
            b=Path(d)/'b.json'; f=Path(d)/'f.json'; o=Path(d)/'o.json'; b.write_text(json.dumps(self.binding)); f.write_text(json.dumps(self.fixture)); main(['--binding',str(b),'--fixture-ledger',str(f),'--output',str(o)]); self.assertFalse(o.exists())

    def _execute_mock(self, dequeue_error=False, missing_attempts=False, changed_item=False, changed_queue=False, missing_queue_etag=False):
        queue_id=self.fixture["queue"]; item_id=self.fixture["itemId"]; patches=[]; paused=False
        queue_row={"statecode":0,"statuscode":1,"@odata.etag":"W/\"q1\""}
        if missing_queue_etag: queue_row.pop("@odata.etag")
        item={"workqueueitemid":item_id,"uniqueidbyqueue":"key","statecode":0,"statuscode":0,"@odata.etag":"W/\"i1\""}
        def request(command, origin, method, path, body=None, **kwargs):
            nonlocal paused
            if path == "WhoAmI": return {"OrganizationId":self.binding["organizationId"]}
            if path.startswith("workflows("): return {"statecode":0}
            if path.startswith("workqueues(") and method == "GET": return {"statecode":1,"statuscode":3,"@odata.etag":"W/\"q2\""} if paused else queue_row
            if path.startswith("workqueues(") and method == "PATCH": patches.append(body); paused=body["statecode"]==1; return {}
            if path.startswith("qmcp_wqdefinitions"): return {"value":[{"qmcp_document":json.dumps({"Enabled":True,"NativeQueueId":queue_id}),"versionnumber":1}]}
            if path.startswith("workqueueitems?"): return {"value":[item]}
            if path.startswith("workqueueitems("): return item
            if path.startswith("qmcp_WQ_PrepareAcquire"): return {"ResultJson":json.dumps({"Outcome":"Prepared","NativeQueueId":queue_id})}
            if path.endswith("/Microsoft.Dynamics.CRM.Dequeue"):
                if dequeue_error: raise ValueError("DATAVERSE_CLI_FAILED")
                return {}
            if path.startswith("qmcp_WQ_ResolveAcquire"): return {"ResultJson":json.dumps({"Outcome":"Pending"})}
            if path.startswith("qmcp_wqattempts"): return {} if missing_attempts else {"value":[]}
            raise AssertionError(path)
        return request, patches

    def test_mocked_transport_failure_restores_and_stays_incomplete(self):
        with tempfile.TemporaryDirectory() as d:
            b=Path(d)/'b.json'; f=Path(d)/'f.json'; o=Path(d)/'o.json'; b.write_text(json.dumps(self.binding)); f.write_text(json.dumps(self.fixture)); request,patches=self._execute_mock(True)
            with patch("prove_native_queue_pause._cli_command",return_value=["cli"]), patch("prove_native_queue_pause._cli_request",side_effect=request):
                with self.assertRaisesRegex(ValueError,"NATIVE_PAUSE_DEQUEUE_UNVERIFIED"): main(["--binding",str(b),"--fixture-ledger",str(f),"--output",str(o),"--execute"])
            evidence=json.loads(o.read_text()); self.assertFalse(evidence["completed"]); self.assertTrue(evidence["policyRestored"]); self.assertEqual([1,0],[p["statecode"] for p in patches])

    def test_mocked_empty_dequeue_completes_after_restore(self):
        with tempfile.TemporaryDirectory() as d:
            b=Path(d)/'b.json'; f=Path(d)/'f.json'; o=Path(d)/'o.json'; b.write_text(json.dumps(self.binding)); f.write_text(json.dumps(self.fixture)); request,patches=self._execute_mock(False)
            with patch("prove_native_queue_pause._cli_command",return_value=["cli"]), patch("prove_native_queue_pause._cli_request",side_effect=request): main(["--binding",str(b),"--fixture-ledger",str(f),"--output",str(o),"--execute"])
            evidence=json.loads(o.read_text()); self.assertTrue(evidence["completed"]); self.assertEqual({},evidence["dequeueResult"]); self.assertTrue(evidence["seededItemUnchanged"]); self.assertEqual([1,0],[p["statecode"] for p in patches])
    def test_paused_error_is_exact_and_queue_scoped(self):
        queue=self.fixture['queue']
        error={'code':'0x80048d0b','message':json.dumps({'errorCode':'RecordNotActive','message':'Work queue '+queue+' is not active. It is in Paused status.'})}
        self.assertTrue(is_paused_error(error,queue))
        self.assertFalse(is_paused_error(error,self.fixture['itemId']))
        self.assertFalse(is_paused_error({**error,'code':'generic'},queue))
        self.assertFalse(is_paused_error({'code':'0x80048d0b','message':'RecordNotActive'},queue))

if __name__=='__main__': unittest.main()


