import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.probe_schema_keys as probe


class SchemaKeyProbeTests(unittest.TestCase):
    def runner(self, calls):
        def run(args, **kwargs):
            calls.append(args)
            path = args[args.index("--path") + 1]

            class Result:
                returncode = 0
                stderr = ""

            if path.endswith("WhoAmI"):
                body = {"OrganizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
            elif "/Keys?" in path:
                logical = re.search(r"LogicalName='([^']+)'", path).group(1)
                body = {"value": [{"SchemaName": logical + "_identity",
                                   "LogicalName": logical + "_identity",
                                   "EntityKeyIndexStatus": "Active"}]}
            elif "EntityDefinitions(LogicalName=" in path:
                logical = re.search(r"LogicalName='([^']+)'", path).group(1)
                body = {"LogicalName": logical,
                        "EntitySetName": logical + "s",
                        "PrimaryIdAttribute": logical + "id"}
            else:
                raise AssertionError(path)
            Result.stdout = json.dumps(body)
            return Result()

        return run

    def test_probe_records_active_key_without_writes(self):
        calls = []
        with patch.object(probe, "_cli_command", return_value=["fake"]):
            with patch.object(probe, "_validate_binding",
                              return_value=("https://dev.crm.dynamics.com",
                                            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")):
                with tempfile.TemporaryDirectory() as directory:
                    report = probe.probe(
                        {"environmentUrl": "https://dev.crm.dynamics.com",
                         "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                         "environmentClass": "development"},
                        Path(directory) / "report.json", self.runner(calls))
        self.assertTrue(report["allExpectedKeysActive"])
        self.assertFalse(report["writesPerformed"])
        self.assertEqual(1 + (13 * 2), len(calls))


if __name__ == "__main__":
    unittest.main()
