import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from prove_concurrent_cancellation import fault_from_stdout, main, safe_fault_markers, validate


class ConcurrentCancellationProofTests(unittest.TestCase):
    binding = {"environmentUrl": "https://synthetic.crm.dynamics.com", "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "environmentClass": "development", "queueKeys": ["qmcp-proof-test"]}
    ledger = {"queueKey": "qmcp-proof-test", "queue": "cccccccc-cccc-cccc-cccc-cccccccccccc"}

    def test_validate_requires_bound_synthetic_queue(self):
        with self.assertRaisesRegex(ValueError, "SYNTHETIC_QUEUE"):
            validate(self.binding, {"queueKey": "mail", "queue": self.ledger["queue"]})

    def test_fault_parser_accepts_nested_version_conflict(self):
        payload = {"error": {"message": json.dumps({"error": {"code": "VERSION_CONFLICT"}})}}
        self.assertEqual(fault_from_stdout(json.dumps(payload)), "VERSION_CONFLICT")

    def test_safe_fault_markers_keep_only_known_tokens(self):
        text = "secret@example.invalid https://org.crm.dynamics.com error -2147088254 HTTP_STATUS_412"
        self.assertEqual(safe_fault_markers(text), ["-2147088254", "HTTP_STATUS_412"])

    def test_dry_run_makes_no_output_or_cli_call(self):
        with tempfile.TemporaryDirectory() as temp:
            b = Path(temp) / "binding.json"; l = Path(temp) / "ledger.json"; out = Path(temp) / "proof.json"
            b.write_text(json.dumps(self.binding)); l.write_text(json.dumps(self.ledger))
            with patch("prove_concurrent_cancellation._cli_command", side_effect=AssertionError("cli")):
                main(["--binding", str(b), "--fixture-ledger", str(l), "--output", str(out)])
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
