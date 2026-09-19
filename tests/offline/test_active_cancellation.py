import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from prove_active_cancellation import main, validate


class ActiveCancellationProofTests(unittest.TestCase):
    binding = {"environmentUrl": "https://synthetic.crm.dynamics.com", "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "environmentClass": "development", "queueKeys": ["qmcp-proof-test"]}
    ledger = {"queueKey": "qmcp-proof-test", "queue": "cccccccc-cccc-cccc-cccc-cccccccccccc"}

    def test_validate_requires_bound_synthetic_queue(self):
        with self.assertRaisesRegex(ValueError, "SYNTHETIC_QUEUE"):
            validate(self.binding, {"queueKey": "mail", "queue": self.ledger["queue"]})

    def test_dry_run_makes_no_output_or_cli_call(self):
        with tempfile.TemporaryDirectory() as temp:
            b = Path(temp) / "binding.json"; l = Path(temp) / "ledger.json"; out = Path(temp) / "proof.json"
            b.write_text(json.dumps(self.binding)); l.write_text(json.dumps(self.ledger))
            with patch("prove_active_cancellation._cli_command", side_effect=AssertionError("cli")):
                main(["--binding", str(b), "--fixture-ledger", str(l), "--output", str(out)])
            self.assertFalse(out.exists())

    def test_active_cancellation_reconciles_and_replays(self):
        with tempfile.TemporaryDirectory() as temp:
            b = Path(temp) / "binding.json"; l = Path(temp) / "ledger.json"; out = Path(temp) / "proof.json"
            b.write_text(json.dumps(self.binding)); l.write_text(json.dumps(self.ledger))
            run_id = "11111111-1111-1111-1111-111111111111"; item_id = "22222222-2222-2222-2222-222222222222"; attempt_id = "33333333-3333-3333-3333-333333333333"
            state = {"cancelled": False, "failed": False}

            def request(_command, _origin, method, path, body=None, **kwargs):
                if path == "WhoAmI": return {"OrganizationId": self.binding["organizationId"]}
                if path.startswith("workqueueitems?"): return {"value": []}
                if path == "qmcp_WQ_StartTestRun": return {"ResultJson": json.dumps({"RunId": run_id})}
                if path == "qmcp_WQ_PrepareAcquire": return {"ResultJson": json.dumps({"Outcome": "Prepared"})}
                if path.endswith("/Microsoft.Dynamics.CRM.Dequeue"): return {"workqueueitemid": item_id}
                if path == "qmcp_WQ_ResolveAcquire": return {"ResultJson": json.dumps({"Outcome": "Acquired", "ItemId": item_id, "AttemptId": attempt_id, "Generation": 0})}
                if path == "qmcp_WQ_CancelTestRun": state["cancelled"] = True; return {"ResultJson": json.dumps({"State": "Cancelled", "Results": [{"State": "Cancelled"}]})}
                if path == "qmcp_WQ_Fail": state["failed"] = True; return {"ResultJson": json.dumps({"Outcome": "ReviewRequired"})}
                if path == "qmcp_WQ_GetTestRun": return {"ResultJson": json.dumps({"State": "Cancelled", "Results": [{"State": "Cancelled", "ItemId": item_id}]})}
                if path == "qmcp_WQ_GetItemStatus":
                    if not state["cancelled"]: return {"ResultJson": json.dumps({"Outcome": "Processing", "ActiveAttempt": attempt_id})}
                    return {"ResultJson": json.dumps({"Outcome": "Exception" if state["failed"] else "Processing", "ActiveAttempt": attempt_id if not state["failed"] else "", "ReviewRequired": state["failed"]})}
                if path.startswith("workqueueitems("): return {"statecode": 1 if state["failed"] else 0, "statuscode": 1}
                if path.startswith("qmcp_wqattempts?"): return {"value": [{"qmcp_wqattemptid": attempt_id, "qmcp_document": "{}"}]}
                raise AssertionError((method, path, body))

            with patch("prove_active_cancellation._cli_command", return_value=["cli"]), patch("prove_active_cancellation._cli_request", side_effect=request):
                main(["--binding", str(b), "--fixture-ledger", str(l), "--output", str(out), "--execute"])
            evidence = json.loads(out.read_text())
            self.assertTrue(evidence["completed"])
            self.assertTrue(evidence["cancelReplayEqual"])
            self.assertEqual(evidence["failureOutcome"], "ReviewRequired")
            self.assertEqual(evidence["runState"], "Cancelled")


if __name__ == "__main__":
    unittest.main()
