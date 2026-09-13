import sys,unittest,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from prove_stale_worker import request_ids

class StaleProofRequestTests(unittest.TestCase):
    def test_resolve_uses_the_persisted_prepare_request_identity(self):
        proof=str(uuid.uuid4()); ids=request_ids(proof)
        self.assertEqual(ids,request_ids(proof))
        for attempt in ('old','new'):
            self.assertEqual(ids['prepare-'+attempt],ids['resolve-'+attempt])
        mutating=[value for label,value in ids.items() if not label.startswith('resolve-')]
        self.assertEqual(len(mutating),len(set(mutating)))
        self.assertNotEqual(ids['fail-old'],ids['stale-fail'])
        self.assertNotEqual(ids['prepare-old'],ids['prepare-new'])
