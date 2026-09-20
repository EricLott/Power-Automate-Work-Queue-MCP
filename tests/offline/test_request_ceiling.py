import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.probe_request_ceiling as probe


class RequestCeilingProbeTests(unittest.TestCase):
    def runner(self, calls):
        def run(args, **kwargs):
            calls.append(args)
            path = args[args.index("--path") + 1]

            class Result:
                stderr = ""

            if path.endswith("WhoAmI"):
                Result.returncode = 0
                Result.stdout = json.dumps({"OrganizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"})
                return Result()

            body_path = args[args.index("--body-file") + 1]
            body = json.loads(Path(body_path).read_text(encoding="utf-8"))
            if len(body["DataJson"].encode("utf-8")) <= 131072:
                Result.returncode = 0
                Result.stdout = "{}"
            else:
                Result.returncode = 1
                Result.stdout = ""
            return Result()

        return run

    def test_exact_payload_sizes_and_boundary_classification(self):
        calls = []
        with patch.object(probe, "_cli_command", return_value=["fake"]):
            with tempfile.TemporaryDirectory() as directory:
                report = probe.probe(
                    {"environmentUrl": "https://dev.crm.dynamics.com",
                     "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                     "environmentClass": "development",
                     "queueKeys": ["qmcp-proof-test"]},
                    Path(directory) / "report.json", "qmcp-proof-test",
                    (131072, 131073), self.runner(calls))
        self.assertEqual(report["maxAcceptedDataJsonBytes"], 131072)
        self.assertEqual(report["firstRejectedDataJsonBytes"], 131073)
        self.assertEqual([row["classification"] for row in report["observations"]], ["accepted", "rejected"])
        self.assertFalse(report["writesPerformed"])
        self.assertEqual(3, len(calls))
        self.assertTrue(all(call[call.index("--path") + 1].endswith("qmcp_WQ_GetQueueHealth") for call in calls[1:]))

    def test_unbound_queue_fails_before_tenant_call(self):
        with patch.object(probe, "_cli_command", return_value=["fake"]):
            with self.assertRaisesRegex(ValueError, "QUEUE_NOT_BOUND"):
                probe.probe(
                    {"environmentUrl": "https://dev.crm.dynamics.com",
                     "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                     "environmentClass": "development",
                     "queueKeys": ["qmcp-proof-test"]},
                    "ignored.json", "other-queue", (131072,), self.runner([]))


if __name__ == "__main__":
    unittest.main()
