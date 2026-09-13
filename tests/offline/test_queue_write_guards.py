import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.prove_queue_write_guards as proof


class Result:
    def __init__(self, body, code=0):
        self.returncode = code
        self.stdout = json.dumps(body)
        self.stderr = ""


class QueueWriteGuardTests(unittest.TestCase):
    def test_exact_denial_is_strict(self):
        self.assertTrue(proof.exact_denial(Result({"error": {"message": "LIFECYCLE_BYPASS"}}, 1)))
        self.assertFalse(proof.exact_denial(Result({}, 0)))
        self.assertFalse(proof.exact_denial(Result({"error": {"message": "RUNTIME_FAILURE"}}, 1)))
        self.assertFalse(proof.exact_denial(Result({"error": {"message": "LIFECYCLE_BYPASS"}}, 0)))
        self.assertFalse(proof.exact_denial(Result("not-json", 1)))

    def test_dry_run_makes_no_tenant_calls(self):
        with patch("scripts.prove_queue_write_guards._cli_command", side_effect=AssertionError):
            with patch("sys.argv", ["prove_queue_write_guards.py", "--binding", "x", "--caller-object-id", "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "--expected-user-id", "cccccccc-cccc-cccc-cccc-cccccccccccc", "--output", "o"]):
                with patch("pathlib.Path.read_text", return_value=json.dumps({"environmentUrl": "https://x.crm.dynamics.com", "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "environmentClass": "development", "queueKeys": ["qmcp-proof-20260912"]})):
                    proof.main()

    def test_mocked_five_case_sequence(self):
        binding = {"environmentUrl": "https://x.crm.dynamics.com", "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "environmentClass": "development", "queueKeys": ["qmcp-proof-20260912"]}
        caller = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"; expected = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        item = "11111111-1111-5111-8111-111111111111"; exists = False; moved = False; calls = []
        def run(args, **kwargs):
            nonlocal exists, moved
            method = args[args.index("--method") + 1]; path = args[args.index("--path") + 1]; calls.append((method, path))
            body = json.loads(Path(args[args.index("--body-file") + 1]).read_text()) if "--body-file" in args else {}
            if "workflows(" in path: return Result({"statecode": 0})
            if "qmcp_wqqueuebindings" in path: return Result({"value": [{"qmcp_key": proof.REGISTERED}] if proof.REGISTERED in path else []})
            if "workqueues(" in path: return Result({"name": "qmcp synthetic queue", "statecode": 0})
            if "workqueueitems?" in path: return Result({"value": [{"workqueueitemid": item, "_workqueueid_value": proof.REGISTERED if moved else proof.UNREGISTERED, "name": "qmcp disposable updated proof", "statecode": 0, "statuscode": 0}] if exists else []})
            if method == "POST" and path.endswith("workqueueitems"):
                envelope = json.loads(body['input'])
                self.assertTrue({'envelopeVersion', 'contract', 'correlationId', 'deduplicationKey', 'source', 'payload'} <= set(envelope))
                self.assertEqual(envelope['source'], {'kind': 'synthetic'})
                self.assertEqual(envelope['contract'], 'mail.v1')
                if body.get("workqueueid@odata.bind", "").endswith(proof.REGISTERED + ")"): return Result({"error": {"message": "LIFECYCLE_BYPASS"}}, 1)
                exists = True; return Result({"workqueueitemid": item})
            if method == "PATCH" and "workqueueitems(" in path:
                if body.get("workqueueid@odata.bind", "").endswith(proof.REGISTERED + ")"): return Result({"error": {"message": "LIFECYCLE_BYPASS"}}, 1)
                return Result({})
            if method == "DELETE": exists = False; return Result({})
            return Result({})
        with tempfile.TemporaryDirectory() as directory:
            bp = Path(directory) / "b.json"; bp.write_text(json.dumps(binding)); out = Path(directory) / "e.json"
            with patch("scripts.prove_queue_write_guards._cli_command", return_value=["fake"]), patch("scripts.prove_queue_write_guards.probe", return_value={"completed": True}), patch("scripts.prove_queue_write_guards._validate_binding", return_value=(binding["environmentUrl"], binding["organizationId"])), patch("scripts.prove_queue_write_guards.subprocess.run", side_effect=run), patch("sys.argv", ["x", "--binding", str(bp), "--caller-object-id", caller, "--expected-user-id", expected, "--output", str(out), "--execute"]):
                proof.main()
            evidence = json.loads(out.read_text())
        self.assertTrue(evidence["completed"])
        self.assertEqual([case["case"] for case in evidence["cases"]], ["registered-create", "unregistered-create", "unregistered-update", "move-into-registered", "unregistered-delete"])

if __name__ == "__main__":
    unittest.main()
