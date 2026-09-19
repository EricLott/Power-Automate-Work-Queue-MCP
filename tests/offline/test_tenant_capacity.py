import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from profile_tenant_capacity import main, validate


class TenantCapacityProfileTests(unittest.TestCase):
    binding = {
        "environmentUrl": "https://synthetic.crm.dynamics.com",
        "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "environmentClass": "development",
        "queueKeys": ["qmcp-proof-test"],
    }
    ledger = {
        "queueKey": "qmcp-proof-test",
        "queue": "cccccccc-cccc-cccc-cccc-cccccccccccc",
        "team": "dddddddd-dddd-dddd-dddd-dddddddddddd",
        "user": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
    }

    def test_validate_bounds_profile_and_requires_synthetic_queue(self):
        with self.assertRaisesRegex(ValueError, "ITEM_COUNT_OUT_OF_RANGE"):
            validate(self.binding, self.ledger, 0)
        with self.assertRaisesRegex(ValueError, "SYNTHETIC_QUEUE"):
            validate(self.binding, {**self.ledger, "queueKey": "mail"}, 1)

    def test_dry_run_makes_no_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binding = root / "binding.json"
            ledger = root / "ledger.json"
            output = root / "profile.json"
            binding.write_text(json.dumps(self.binding))
            ledger.write_text(json.dumps(self.ledger))
            main(["--binding", str(binding), "--fixture-ledger", str(ledger), "--items", "1", "--output", str(output)])
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
