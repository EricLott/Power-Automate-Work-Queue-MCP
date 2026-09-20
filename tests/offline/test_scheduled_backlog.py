import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from prove_scheduled_backlog import main, validate


class ScheduledBacklogProofTests(unittest.TestCase):
    def setUp(self):
        self.binding = {
            "environmentUrl": "https://org.example.crm.dynamics.com",
            "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "environmentClass": "development",
            "queueKeys": ["qmcp-proof-test"],
        }
        self.ledger = {
            "queueKey": "qmcp-proof-test",
            "queue": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "team": "cccccccc-cccc-cccc-cccc-cccccccccccc",
            "user": "dddddddd-dddd-dddd-dddd-dddddddddddd",
        }

    def test_validate_requires_bound_synthetic_queue_and_ids(self):
        origin, organization, queue = validate(self.binding, self.ledger)
        self.assertEqual(origin, self.binding["environmentUrl"])
        self.assertEqual(organization, self.binding["organizationId"])
        self.assertEqual(queue, "qmcp-proof-test")
        invalid = dict(self.binding, queueKeys=["mail"])
        with self.assertRaisesRegex(ValueError, "SYNTHETIC_QUEUE_NOT_BOUND"):
            validate(invalid, self.ledger)

    def test_dry_run_makes_no_tenant_call_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            binding_path = Path(directory) / "binding.json"
            ledger_path = Path(directory) / "ledger.json"
            output_path = Path(directory) / "evidence.json"
            binding_path.write_text(json.dumps(self.binding), encoding="utf-8")
            ledger_path.write_text(json.dumps(self.ledger), encoding="utf-8")
            with patch("prove_scheduled_backlog._cli_command", side_effect=AssertionError("CLI")):
                main(["--binding", str(binding_path), "--fixture-ledger", str(ledger_path), "--output", str(output_path)])
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
