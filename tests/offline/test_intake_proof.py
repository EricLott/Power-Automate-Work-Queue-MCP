import copy, json, sys, unittest, uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from prove_intake_duplicates import safe_error, prove

class IntakeProofTests(unittest.TestCase):
    def run_proof(self, fault='KEY_CONTENT_CONFLICT', changed=False, extra=False, concurrent=False):
        observed={}; reads=0; posts=0
        def call(method,path,body=None):
            nonlocal reads, posts
            if method=='GET':
                reads+=1
                rows=[] if reads==1 else [{'workqueueitemid':'item','input':'changed' if changed and reads==3 else 'original','statecode':0}]
                if extra and reads==3: rows.append(copy.deepcopy(rows[0]))
                return {'value':rows}
            posts+=1
            if posts==3:
                if fault: raise ValueError(fault)
                return {'ResultJson':json.dumps({'Outcome':'Enqueued','ItemId':'other'})}
            return {'ResultJson':json.dumps({'Outcome':'Enqueued' if posts==1 else 'Existing','ItemId':'item'})}
        prove(call,'qmcp-proof-test',str(uuid.uuid4()),lambda **values: observed.update(values),concurrent=concurrent)
        return observed
    def test_native_reads_confirm_conflict_and_unchanged_input(self):
        result=self.run_proof()
        self.assertTrue(result['completed']); self.assertEqual(1,result['nativeCountAfter'])
        self.assertEqual(result['inputSha256Before'],result['inputSha256After'])
    def test_transport_failures_cannot_pass(self):
        for error in ('DATAVERSE_ACCESS_DENIED','DATAVERSE_CLI_TIMEOUT','DATAVERSE_CLI_FAILED'):
            with self.subTest(error=error),self.assertRaisesRegex(ValueError,error): self.run_proof(fault=error)
    def test_concurrent_submissions_still_require_one_native_item(self):
        self.assertTrue(self.run_proof(concurrent=True)['completed'])
        with self.assertRaisesRegex(ValueError,'NATIVE_ITEM_CHANGED'): self.run_proof(concurrent=True,extra=True)
    def test_changed_native_input_cannot_pass(self):
        with self.assertRaisesRegex(ValueError,'NATIVE_INPUT_CHANGED'): self.run_proof(changed=True)
    def test_extra_native_item_cannot_pass(self):
        with self.assertRaisesRegex(ValueError,'NATIVE_ITEM_CHANGED'): self.run_proof(extra=True)
    def test_accepted_conflict_cannot_pass(self):
        with self.assertRaisesRegex(ValueError,'CONFLICT_NOT_REJECTED'): self.run_proof(fault=None)
    def test_only_exact_framework_fault_is_exposed(self):
        self.assertEqual('KEY_CONTENT_CONFLICT',safe_error(json.dumps({'error':{'code':'0x80040265','message':'KEY_CONTENT_CONFLICT'}}),1))
        for body in ('not-json','[]',json.dumps({'error':{'message':'token KEY_CONTENT_CONFLICT'}}),json.dumps({'error':{'message':'Access denied'}})):
            self.assertEqual('DATAVERSE_CLI_FAILED',safe_error(body,1))
        self.assertEqual('',safe_error('{"ResultJson":"{}"}',0))
