import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from prove_prepared_pause import policies_equal, scoped_dequeue_runner, validate


class PreparedPauseProofTests(unittest.TestCase):
    def binding(self):
        return {"environmentUrl": "https://synthetic.crm.dynamics.com", "organizationId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "environmentClass": "development", "queueKeys": ["qmcp-proof-test"]}

    def ledger(self):
        return {"queueKey": "qmcp-proof-test", "queue": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"}

    def seed(self):
        return {"organizationId": self.binding()["organizationId"], "queueKey": "qmcp-proof-test", "itemId": "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "completed": True, "seededItemLeftQueued": True}

    def test_validate_requires_exact_completed_seed(self):
        self.assertEqual(self.seed()["itemId"], validate(self.binding(), self.ledger(), self.seed())[-1])
        with self.assertRaisesRegex(ValueError, "SEED_ARTIFACT_NOT_QUEUED"):
            validate(self.binding(), self.ledger(), {**self.seed(), "completed": False})

    def test_validate_rejects_seed_from_another_environment_or_item(self):
        with self.assertRaisesRegex(ValueError, "SEED_ARTIFACT_MISMATCH"):
            validate(self.binding(), self.ledger(), {**self.seed(), "organizationId": "dddddddd-dddd-4ddd-8ddd-dddddddddddd"})
        with self.assertRaisesRegex(ValueError, "SEEDED_ITEM_REQUIRED"):
            validate(self.binding(), self.ledger(), {**self.seed(), "itemId": "not-a-uuid"})

    def test_dry_run_has_no_output(self):
        from prove_prepared_pause import main
        with tempfile.TemporaryDirectory() as temp:
            binding, ledger, seed, output = (Path(temp) / name for name in ("binding.json", "ledger.json", "seed.json", "out.json"))
            binding.write_text(json.dumps(self.binding()))
            ledger.write_text(json.dumps(self.ledger()))
            seed.write_text(json.dumps(self.seed()))
            main(["--binding", str(binding), "--fixture-ledger", str(ledger), "--seed-evidence", str(seed), "--output", str(output)])
            self.assertFalse(output.exists())

    def test_policy_comparison_ignores_revision_only(self):
        original = {"Enabled": True, "Revision": 1, "NativeQueueId": self.ledger()["queue"]}
        self.assertTrue(policies_equal(original, {**original, "Revision": 2}))
        self.assertFalse(policies_equal(original, {**original, "Enabled": False}))

    def test_scoped_dequeue_recognizes_only_exact_structured_pause_fault(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        for stdout, expected in ((json.dumps({"error": {"message": "QUEUE_PAUSED"}}), True),
                                 (json.dumps({"error": {"message": "transport QUEUE_PAUSED"}}), False),
                                 ("QUEUE_PAUSED", False)):
            state = {"value": False}
            result = SimpleNamespace(returncode=1, stdout=stdout, stderr="QUEUE_PAUSED")
            with patch("prove_prepared_pause.subprocess.run", return_value=result):
                scoped_dequeue_runner(state, ["fake"], capture_output=True, text=True)
            self.assertEqual(expected, state["value"])

    def test_scoped_dequeue_accepts_exact_wrapped_lifecycle_bypass(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        item = self.seed()["itemId"]
        inner = {"errorCode": "InternalServerError", "message": "Fail to update work queue item " + item + " to Processing because: LIFECYCLE_BYPASS. Fault ErrorCode: -2147220891"}
        payload = {"error": {"code": "0x80048d0a", "message": json.dumps(inner)}}
        state = {"value": False, "itemId": item}
        result = SimpleNamespace(returncode=1, stdout=json.dumps(payload), stderr="")
        with patch("prove_prepared_pause.subprocess.run", return_value=result):
            scoped_dequeue_runner(state, ["fake"], capture_output=True, text=True)
        self.assertTrue(state["value"])
        self.assertEqual("LIFECYCLE_BYPASS", state["fault"])

    def test_scoped_dequeue_rejects_wrong_item_code_or_reason(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        item = self.seed()["itemId"]
        cases = [
            {"errorCode": "InternalServerError", "message": "Fail to update work queue item dddddddd-dddd-4ddd-8ddd-dddddddddddd to Processing because: LIFECYCLE_BYPASS. Fault ErrorCode: -2147220891"},
            {"errorCode": "BadRequest", "message": "Fail to update work queue item " + item + " to Processing because: LIFECYCLE_BYPASS. Fault ErrorCode: -2147220891"},
            {"errorCode": "InternalServerError", "message": "Fail to update work queue item " + item + " to Processing because: OTHER. Fault ErrorCode: -2147220891"},
        ]
        for inner in cases:
            state = {"value": False, "itemId": item}
            payload = {"error": {"code": "0x80048d0a", "message": json.dumps(inner)}}
            result = SimpleNamespace(returncode=1, stdout=json.dumps(payload), stderr="")
            with patch("prove_prepared_pause.subprocess.run", return_value=result):
                scoped_dequeue_runner(state, ["fake"], capture_output=True, text=True)
            self.assertFalse(state["value"])

    def test_execute_asserts_pending_resolution_and_restores_policy(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from prove_prepared_pause import main
        with tempfile.TemporaryDirectory() as temp:
            binding = Path(temp) / "binding.json"; ledger = Path(temp) / "ledger.json"
            seed = Path(temp) / "seed.json"; output = Path(temp) / "out.json"
            binding.write_text(json.dumps(self.binding())); ledger.write_text(json.dumps(self.ledger())); seed.write_text(json.dumps(self.seed()))
            policy = {"Enabled": True, "NativeQueueId": self.ledger()["queue"], "Revision": 3}
            item = {"workqueueitemid": self.seed()["itemId"], "uniqueidbyqueue": "synthetic", "statecode": 0, "statuscode": 0, "@odata.etag": 'W/"1"'}
            def request(command, origin, method, relative, body=None, runner=None):
                if relative == "WhoAmI": return {"OrganizationId": self.binding()["organizationId"]}
                if relative.startswith("workflows("): return {"statecode": 0}
                if relative.startswith("qmcp_wqdefinitions?"): return {"value": [{"qmcp_document": json.dumps(policy), "versionnumber": policy["Revision"]}]}
                if relative.startswith("workqueueitems("): return item
                if relative.startswith("workqueueitems?"): return {"value": [item]}
                if relative.startswith("qmcp_wqattempts?"): return {"value": []}
                if relative == "qmcp_WQ_RegisterQueue":
                    requested = json.loads(body["DataJson"]); policy.clear(); policy.update(requested); return {"ResultJson": json.dumps({"Outcome": "Registered"})}
                if relative == "qmcp_WQ_PrepareAcquire": return {"ResultJson": json.dumps({"Outcome": "Prepared", "NativeQueueId": self.ledger()["queue"]})}
                if relative == "qmcp_WQ_ResolveAcquire": return {"ResultJson": json.dumps({"Outcome": "Pending"})}
                if "Microsoft.Dynamics.CRM.Dequeue" in relative:
                    result = runner(["fake"], returncode=1, stdout=json.dumps({"error": {"message": "QUEUE_PAUSED"}}), stderr="")
                    raise ValueError("DATAVERSE_CLI_FAILED")
                raise AssertionError(relative)
            with patch("prove_prepared_pause._cli_command", return_value=["fake"]), patch("prove_prepared_pause._cli_request", side_effect=request):
                with patch("prove_prepared_pause.subprocess.run", return_value=SimpleNamespace(returncode=1, stdout=json.dumps({"error": {"message": "QUEUE_PAUSED"}}), stderr="")):
                    main(["--binding", str(binding), "--fixture-ledger", str(ledger), "--seed-evidence", str(seed), "--output", str(output), "--execute"])
            evidence = json.loads(output.read_text())
            self.assertTrue(evidence["completed"])
            self.assertEqual("Pending", evidence["resolveOutcome"]["Outcome"])
            self.assertTrue(evidence["policyRestored"])


if __name__ == "__main__":
    unittest.main()
