import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.probe_schema_metadata as probe


class SchemaMetadataProbeTests(unittest.TestCase):
    def runner(self, calls):
        def run(args, **kwargs):
            calls.append(args)
            path = args[args.index("--path") + 1]

            class Result:
                returncode = 0
                stderr = ""

            if path.endswith("WhoAmI"):
                body = {"OrganizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
            elif "qmcp_wqcontracts?" in path:
                body = {"value": [{"qmcp_document": json.dumps({
                    "Id": "mail.v1",
                    "Dialect": "http://json-schema.org/draft-07/schema#",
                    "Hash": "a" * 64,
                    "Schema": {"type": "object", "required": ["subject"], "additionalProperties": False},
                })}]}
            elif "/Attributes(LogicalName=" in path:
                body = {"LogicalName": "qmcp_document", "AttributeType": "Memo",
                        "AttributeTypeName": {"Value": "MemoType"}, "Format": "Text",
                        "MaxLength": 1048576, "IsValidForCreate": True, "IsValidForUpdate": True}
            else:
                raise AssertionError(path)
            Result.stdout = json.dumps(body)
            return Result()

        return run

    def test_probe_records_contract_and_column_metadata_without_writes(self):
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
        self.assertTrue(report["allContractDialectsDraft07"])
        self.assertTrue(report["allObservedMemoLimitsAtLeastBytes"])
        self.assertFalse(report["writesPerformed"])
        self.assertEqual(1 + 6 + 1, len(calls))


if __name__ == "__main__":
    unittest.main()
