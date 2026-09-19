import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from prove_delayed_retry import main, validate


class DelayedRetryProofTests(unittest.TestCase):
    binding = {"environmentUrl": "https://synthetic.crm.dynamics.com", "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "environmentClass": "development", "queueKeys": ["qmcp-proof-test"]}
    ledger = {"queueKey": "qmcp-proof-test", "queue": "cccccccc-cccc-cccc-cccc-cccccccccccc", "itemId": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"}

    def test_validate_requires_synthetic_bound_item(self):
        with self.assertRaisesRegex(ValueError, "SYNTHETIC_QUEUE"):
            validate(self.binding, {"queueKey": "mail", "itemId": self.ledger["itemId"]})
        with self.assertRaisesRegex(ValueError, "SEEDED_ITEM"):
            validate(self.binding, {"queueKey": self.ledger["queueKey"]})

    def test_dry_run_has_no_output(self):
        with tempfile.TemporaryDirectory() as temp:
            b = Path(temp) / "binding.json"; l = Path(temp) / "ledger.json"; out = Path(temp) / "proof.json"
            b.write_text(json.dumps(self.binding)); l.write_text(json.dumps(self.ledger))
            main(["--binding", str(b), "--fixture-ledger", str(l), "--output", str(out)])
            self.assertFalse(out.exists())

    def test_stage_records_native_delay_and_requires_no_early_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            b = Path(temp) / "binding.json"; l = Path(temp) / "ledger.json"; out = Path(temp) / "proof.json"
            b.write_text(json.dumps(self.binding)); l.write_text(json.dumps(self.ledger))
            item = self.ledger["itemId"]

            def request(_command, _origin, method, path, body, runner):
                if method == "GET" and path.startswith("workqueueitems("):
                    if "delayuntil" in path:
                        return {"statecode": 0, "statuscode": 0, "delayuntil": "2099-01-01T00:00:00Z"}
                    return {"statecode": 0, "statuscode": 0, "delayuntil": None}
                if path == "qmcp_WQ_PrepareAcquire":
                    return {"ResultJson": json.dumps({"Outcome": "Prepared"})}
                if path.endswith("/Microsoft.Dynamics.CRM.Dequeue"):
                    return {"workqueueitemid": item}
                if path == "qmcp_WQ_ResolveAcquire":
                    return {"ResultJson": json.dumps({"Outcome": "Acquired", "ItemId": item, "AttemptId": "attempt", "Generation": 1, "BusinessKey": "business", "SourceKey": "source", "ContentHash": "hash"})}
                if path == "qmcp_WQ_Fail":
                    return {"ResultJson": json.dumps({"Outcome": "RetryScheduled"})}
                raise AssertionError((method, path, body))

            with patch("prove_delayed_retry._cli_command", return_value=["cli"]), patch("prove_delayed_retry._cli_request", side_effect=request):
                main(["--binding", str(b), "--fixture-ledger", str(l), "--output", str(out), "--execute"])

            evidence = json.loads(out.read_text())
            self.assertEqual(evidence["stage"], "retry-scheduled")
            self.assertEqual(evidence["delayUntil"], "2099-01-01T00:00:00Z")
            self.assertTrue(evidence["earlyClaimNotProven"])

    def test_finish_requires_a_completed_stage_record(self):
        with tempfile.TemporaryDirectory() as temp:
            b = Path(temp) / "binding.json"; l = Path(temp) / "ledger.json"; out = Path(temp) / "proof.json"
            b.write_text(json.dumps(self.binding)); l.write_text(json.dumps(self.ledger))
            out.write_text(json.dumps({"organizationId": self.binding["organizationId"], "queueKey": self.ledger["queueKey"], "itemId": self.ledger["itemId"], "stage": "not-ready"}))
            with patch("prove_delayed_retry._cli_command") as command, patch("prove_delayed_retry._cli_request") as request:
                with self.assertRaisesRegex(ValueError, "STAGE_EVIDENCE_MISMATCH"):
                    main(["--binding", str(b), "--fixture-ledger", str(l), "--output", str(out), "--finish"])
                command.assert_not_called()
                request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
