import json, sys, tempfile, unittest, uuid, threading
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'scripts'))
from prove_acquisition_identity import fault_from_stdout, main

class AcquisitionIdentityProofTests(unittest.TestCase):
    def test_fault_parser_accepts_only_expected_structured_faults(self):
        self.assertEqual('ACQUIRE_BUSY', fault_from_stdout(json.dumps({'error':{'message':'ACQUIRE_BUSY'}})))
        self.assertEqual('REQUEST_CONFLICT', fault_from_stdout(json.dumps({'error':{'message':json.dumps({'error':{'message':'REQUEST_CONFLICT'}})}})))
        self.assertIsNone(fault_from_stdout(json.dumps({'error':{'message':'DATAVERSE_CLI_FAILED'}})))
        self.assertIsNone(fault_from_stdout('timeout'))

    def test_dry_run_rejects_unallowlisted_queue_without_cli_or_output(self):
        binding={"environmentUrl":"https://synthetic.crm.dynamics.com","organizationId":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","environmentClass":"development","queueKeys":["mail"]}
        fixture={"queueKey":"qmcp-proof-test","queue":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"}
        with tempfile.TemporaryDirectory() as d:
            b=Path(d)/'b'; f=Path(d)/'f'; o=Path(d)/'o'; b.write_text(json.dumps(binding)); f.write_text(json.dumps(fixture))
            with patch('prove_acquisition_identity._cli_command',side_effect=AssertionError('cli')):
                with self.assertRaisesRegex(ValueError,'SYNTHETIC_QUEUE_NOT_BOUND'): main(['--binding',str(b),'--fixture-ledger',str(f),'--output-dir',str(o),'--run-id','proof'])
            self.assertFalse(o.exists())


    def test_mocked_complete_request_sequence_and_generic_failure(self):
        for generic in (False, True):
            with self.subTest(generic=generic), tempfile.TemporaryDirectory() as directory:
                base=Path(directory); output=base/'proof'
                queue=str(uuid.uuid4()); actor=str(uuid.uuid4()); org=str(uuid.uuid4())
                binding={'environmentUrl':'https://synthetic.crm.dynamics.com','organizationId':org,'environmentClass':'development','queueKeys':['qmcp-proof-test']}
                ledger={'queueKey':'qmcp-proof-test','queue':queue,'user':actor,'team':str(uuid.uuid4())}
                (base/'binding').write_text(json.dumps(binding)); (base/'fixture').write_text(json.dumps(ledger))
                items={}; winner=[None]; business={}; lock=threading.Lock()
                def cli_result(args, **kwargs):
                    return SimpleNamespace(returncode=1,stdout=json.dumps({'error':{'message':args[0]}}))
                def call(command,origin,method,path,body=None,runner=None):
                    with lock:
                        def rejected(code):
                            runner([code]); raise ValueError('DATAVERSE_CLI_FAILED')
                        if path=='WhoAmI': return {'OrganizationId':org,'UserId':actor}
                        if path.startswith('workflows('): return {'statecode':0}
                        if path.startswith('qmcp_wqdefinitions?'):return {'value':[{'qmcp_document':json.dumps({'Enabled':True,'NativeQueueId':queue})}]}
                        if path.startswith('workqueueitems?'):return {'value':[dict(row) for row in items.values() if row['statecode']!=2]}
                        if path=='qmcp_WQ_Enqueue':
                            item=str(uuid.uuid4());items[item]={'workqueueitemid':item,'uniqueidbyqueue':item,'statecode':0,'statuscode':0,'@odata.etag':'one'}
                            return {'ResultJson':json.dumps({'Outcome':'Enqueued','ItemId':item})}
                        if path=='qmcp_WQ_PrepareAcquire':
                            if json.loads(body['DataJson'])['flowId']=='changed-identity':return rejected('REQUEST_CONFLICT')
                            if winner[0] is None:winner[0]=body['RequestId']
                            if winner[0]!=body['RequestId']:return rejected('timeout' if generic else 'ACQUIRE_BUSY')
                            return {'ResultJson':json.dumps({'Outcome':'Prepared','RequestId':winner[0],'NativeQueueId':queue})}
                        if 'Microsoft.Dynamics.CRM.Dequeue' in path:
                            row=next(iter(items.values()));row.update(statecode=1,statuscode=1);return {'workqueueitemid':row['workqueueitemid']}
                        if path=='qmcp_WQ_ResolveAcquire':
                            self.assertEqual(winner[0],body['RequestId']); row=next(iter(items.values()))
                            return {'ResultJson':json.dumps({'Outcome':'Acquired','ItemId':row['workqueueitemid'],'AttemptId':'attempt','Generation':1,'BusinessKey':row['uniqueidbyqueue'],'SourceKey':'source'})}
                        if path.startswith('qmcp_wqattempts?'):
                            first=next(iter(items));return {'value':[{'qmcp_wqattemptid':'attempt'}] if first in path else []}
                        if path=='qmcp_emailrequests':business.update(body);return {}
                        if path.startswith('qmcp_emailrequests('):return dict(business)
                        if path=='qmcp_WQ_Complete':
                            items[body['ItemId']].update(statecode=2,statuscode=2);return {'ResultJson':json.dumps({'Outcome':'Processed'})}
                        if path.startswith('workqueueitems('):return dict(items[path.split('(')[1].split(')')[0]])
                        raise AssertionError(path)
                args=['--binding',str(base/'binding'),'--fixture-ledger',str(base/'fixture'),'--output-dir',str(output),'--run-id','mock','--execute']
                with patch('prove_acquisition_identity._cli_command',return_value=['cli']), patch('prove_acquisition_identity._cli_request',side_effect=call), patch('prove_acquisition_identity.subprocess.run',side_effect=cli_result):
                    if generic:
                        with self.assertRaisesRegex(ValueError,'DISTINCT_PREPARE_ASSERTION_FAILED'):main(args)
                    else:main(args)
                evidence=json.loads((output/'evidence.json').read_text())
                self.assertEqual(not generic,evidence['completed'])
                if not generic:
                    self.assertEqual([0,2],sorted(x['statecode'] for x in evidence['nativeFinal'].values()))
                    self.assertEqual('REQUEST_CONFLICT',evidence['changedArguments'])
                    self.assertEqual(evidence['nativeBeforePrepare'],evidence['nativeAfterPrepare'])
                else:self.assertTrue(all(x['statecode']==0 for x in items.values()))

if __name__=='__main__': unittest.main()
