import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from prove_retention_fixture import main, validate


class RetentionFixtureProofTests(unittest.TestCase):
    binding = {"environmentUrl": "https://synthetic.crm.dynamics.com", "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "environmentClass": "development", "queueKeys": ["qmcp-proof-test"]}
    ledger = {"queueKey": "qmcp-proof-test"}

    def test_validate_requires_bound_synthetic_queue(self):
        with self.assertRaisesRegex(ValueError, "SYNTHETIC_QUEUE"):
            validate(self.binding, {"queueKey": "mail"})

    def test_dry_run_makes_no_tenant_call_or_output(self):
        with tempfile.TemporaryDirectory() as temp:
            binding = Path(temp) / "binding.json"; ledger = Path(temp) / "ledger.json"; output = Path(temp) / "proof.json"
            binding.write_text(json.dumps(self.binding)); ledger.write_text(json.dumps(self.ledger))
            with patch("prove_retention_fixture._cli_command", side_effect=AssertionError("cli")):
                main(["--binding", str(binding), "--fixture-ledger", str(ledger), "--output", str(output)])
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
