import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from prove_queue_pause import policies_equal, validate


class QueuePauseProofTests(unittest.TestCase):
    def binding(self):
        return {"environmentUrl": "https://synthetic.crm.dynamics.com", "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "environmentClass": "development", "queueKeys": ["qmcp-proof-test"]}

    def test_validate_requires_bound_synthetic_queue_and_native_id(self):
        with self.assertRaisesRegex(ValueError, "SYNTHETIC_QUEUE"):
            validate(self.binding(), {"queueKey": "mail", "queue": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"})
        with self.assertRaisesRegex(ValueError, "NATIVE_QUEUE_ID"):
            validate(self.binding(), {"queueKey": "qmcp-proof-test"})

    def test_dry_run_has_no_output_or_tenant_call(self):
        from prove_queue_pause import main
        with tempfile.TemporaryDirectory() as temp:
            binding = Path(temp) / "binding.json"
            ledger = Path(temp) / "ledger.json"
            output = Path(temp) / "evidence.json"
            binding.write_text(json.dumps(self.binding()))
            ledger.write_text(json.dumps({"queueKey": "qmcp-proof-test", "queue": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}))
            main(["--binding", str(binding), "--fixture-ledger", str(ledger), "--output", str(output)])
            self.assertFalse(output.exists())

    def test_policy_equality_ignores_only_revision_without_mutating_inputs(self):
        original = {"Enabled": True, "Grants": {"worker": ["worker"]}, "Revision": 3, "Destinations": ["ops"]}
        same = {**original, "Revision": 4}
        self.assertTrue(policies_equal(original, same))
        self.assertFalse(policies_equal(original, {**same, "Enabled": False}))
        self.assertFalse(policies_equal(original, {**same, "Grants": {"worker": ["worker"], "producer": ["producer"]}}))
        self.assertEqual(3, original["Revision"])

    def _inputs(self, temp):
        binding = Path(temp) / "binding.json"
        ledger = Path(temp) / "ledger.json"
        output = Path(temp) / "evidence.json"
        binding.write_text(json.dumps(self.binding()))
        ledger.write_text(json.dumps({"queueKey": "qmcp-proof-test", "queue": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}))
        return binding, ledger, output

    def _cli_fake(self, policy, fail_pause=True, concurrent_change=False):
        item = {"workqueueitemid": "dddddddd-dddd-dddd-dddd-dddddddddddd", "uniqueidbyqueue": "synthetic", "statecode": 0, "statuscode": 0}
        original = json.loads(json.dumps(policy))
        calls = []

        def request(command, origin, method, relative, body=None, **kwargs):
            calls.append((method, relative, body))
            if relative == "WhoAmI": return {"OrganizationId": self.binding()["organizationId"]}
            if relative.startswith("workflows("): return {"statecode": 0}
            if relative.startswith("qmcp_wqdefinitions?"): return {"value": [{"qmcp_document": json.dumps(policy), "versionnumber": 7}]}
            if relative.startswith("workqueueitems("): return item
            if method == "POST" and relative == "qmcp_WQ_Enqueue": return {"ResultJson": json.dumps({"ItemId": item["workqueueitemid"]})}
            if method == "POST" and relative == "qmcp_WQ_RegisterQueue":
                requested = json.loads(body["DataJson"])
                if not requested["Enabled"]:
                    policy.clear(); policy.update(requested)
                    if concurrent_change:
                        policy["SafeEffects"] = not policy.get("SafeEffects", True)
                    if fail_pause: raise ValueError("DATAVERSE_CLI_FAILED")
                else:
                    policy.clear(); policy.update(requested)
                return {"ResultJson": json.dumps({"Outcome": "Registered"})}
            raise AssertionError((method, relative, body))
        return request, calls, original

    def test_lost_pause_response_restores_original_policy(self):
        from prove_queue_pause import main
        with tempfile.TemporaryDirectory() as temp:
            binding, ledger, output = self._inputs(temp)
            policy = {"Enabled": True, "NativeQueueId": self.binding()["organizationId"], "Revision": 3, "SafeEffects": True}
            fake, calls, original = self._cli_fake(policy)
            with patch("prove_queue_pause._cli_command", return_value=["fake"]), patch("prove_queue_pause._cli_request", side_effect=fake):
                with self.assertRaisesRegex(ValueError, "DATAVERSE_CLI_FAILED"):
                    main(["--binding", str(binding), "--fixture-ledger", str(ledger), "--output", str(output), "--execute"])
            evidence = json.loads(output.read_text())
            self.assertFalse(evidence["completed"])
            self.assertIn("pauseRequestId", evidence)
            self.assertIn("restoreRequestId", evidence)
            self.assertTrue(evidence["policyRestored"])
            self.assertTrue(policies_equal(evidence["restoredPolicy"], original))
            self.assertEqual(2, sum(method == "POST" and relative == "qmcp_WQ_RegisterQueue" for method, relative, _ in calls))

    def test_concurrent_policy_change_is_not_overwritten_during_restore(self):
        from prove_queue_pause import main
        with tempfile.TemporaryDirectory() as temp:
            binding, ledger, output = self._inputs(temp)
            policy = {"Enabled": True, "NativeQueueId": self.binding()["organizationId"], "Revision": 3, "SafeEffects": True}
            fake, calls, _ = self._cli_fake(policy, concurrent_change=True)
            with patch("prove_queue_pause._cli_command", return_value=["fake"]), patch("prove_queue_pause._cli_request", side_effect=fake):
                with self.assertRaisesRegex(ValueError, "CONCURRENT_POLICY_CHANGE"):
                    main(["--binding", str(binding), "--fixture-ledger", str(ledger), "--output", str(output), "--execute"])
            evidence = json.loads(output.read_text())
            self.assertFalse(evidence["completed"])
            self.assertIn("pauseRequestId", evidence)
            self.assertNotIn("restoreRequestId", evidence)
            self.assertEqual(1, sum(method == "POST" and relative == "qmcp_WQ_RegisterQueue" for method, relative, _ in calls))
            self.assertFalse(policy["Enabled"])
            self.assertFalse(policy["SafeEffects"])


if __name__ == "__main__":
    unittest.main()
