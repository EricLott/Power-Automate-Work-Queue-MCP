import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import scripts.prove_post_write_recovery as proof


class PostWriteRecoveryProofTests(unittest.TestCase):
    def test_dry_run_is_tenant_free(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = root / "binding.json"
            ledger = root / "ledger.json"
            binding.write_text(json.dumps({
                "environmentUrl": "https://dev.crm.dynamics.com",
                "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "environmentClass": "development",
                "queueKeys": ["qmcp-proof-test"],
            }), encoding="utf-8")
            ledger.write_text(json.dumps({
                "queueKey": "qmcp-proof-test",
                "queue": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "team": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "user": "dddddddd-dddd-dddd-dddd-dddddddddddd",
            }), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                proof.main(["--binding", str(binding), "--fixture-ledger", str(ledger),
                            "--output", str(root / "evidence.json")])
            report = json.loads(output.getvalue())
            self.assertTrue(report["ready"])
            self.assertFalse(report["writes"])
            self.assertFalse((root / "evidence.json").exists())


if __name__ == "__main__":
    unittest.main()
