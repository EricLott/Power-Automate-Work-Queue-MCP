import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.prove_registered_delete_companion_guards as proof


class RegisteredDeleteCompanionGuardTests(unittest.TestCase):
    def test_dry_run_makes_no_tenant_calls_or_output(self):
        binding = {
            "environmentUrl": "https://example.crm.dynamics.com",
            "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "environmentClass": "development",
            "queueKeys": ["qmcp-proof-current"],
        }
        with tempfile.TemporaryDirectory() as directory:
            binding_path = Path(directory) / "binding.json"
            output_path = Path(directory) / "evidence.json"
            binding_path.write_text(json.dumps(binding), encoding="utf-8")
            argv = [
                "proof.py", "--binding", str(binding_path),
                "--caller-object-id", "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "--expected-user-id", "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "--queue-id", "dddddddd-dddd-dddd-dddd-dddddddddddd",
                "--item-id", "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
                "--companion-id", "ffffffff-ffff-ffff-ffff-ffffffffffff",
                "--output", str(output_path),
            ]
            with patch("scripts.prove_registered_delete_companion_guards._cli_command", side_effect=AssertionError):
                with patch("sys.argv", argv):
                    proof.main()
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
