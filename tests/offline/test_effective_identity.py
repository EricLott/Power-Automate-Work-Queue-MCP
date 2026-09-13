import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

from scripts.probe_effective_identity import probe


ORG = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CALLER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
EXPECTED = "cccccccc-cccc-cccc-cccc-cccccccccccc"
BINDING = {"environmentUrl": "https://dev.crm.dynamics.com",
           "organizationId": ORG, "environmentClass": "development"}


class EffectiveIdentityTests(unittest.TestCase):
    def runner(self, calls, who=None, rows=None, impersonated_user=EXPECTED, impersonated_rows=None):
        def run(args, **kwargs):
            calls.append(args)
            path = args[args.index("--path") + 1]
            class Result:
                returncode = 0
                stderr = ""
            if path.endswith("WhoAmI"):
                body = who
            elif "CallerObjectId:" in " ".join(args):
                body = {"value": impersonated_rows if impersonated_rows is not None else [{"systemuserid": impersonated_user}]}
            elif "azureactivedirectoryobjectid" in path:
                body = {"value": rows or []}
            else:
                body = {"value": [{"systemuserid": (who or {}).get("UserId")}]} 
            Result.stdout = json.dumps(body)
            return Result()
        return run

    def test_plan_makes_no_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            with patch("scripts.probe_effective_identity._cli_command", side_effect=AssertionError):
                result = probe(BINDING, CALLER, EXPECTED, Path(directory) / "e.json")
        self.assertFalse(result["tenantCalls"])
        self.assertFalse(calls)

    def test_malformed_identifiers_rejected(self):
        with self.assertRaisesRegex(ValueError, "CALLER_OBJECT_INVALID_UUID"):
            probe(BINDING, "bad", EXPECTED, "ignored")
        with self.assertRaisesRegex(ValueError, "EXPECTED_USER_INVALID_UUID"):
            probe(BINDING, CALLER, "bad", "ignored")

    def test_wrong_org_and_same_operator_fail(self):
        with tempfile.TemporaryDirectory() as directory, patch("scripts.probe_effective_identity._cli_command", return_value=["fake"]):
            calls = []
            with self.assertRaisesRegex(ValueError, "ENVIRONMENT_MISMATCH"):
                probe(BINDING, CALLER, EXPECTED, Path(directory) / "org.json", self.runner(calls, {"OrganizationId": "dddddddd-dddd-dddd-dddd-dddddddddddd", "UserId": CALLER}), True)
            calls.clear()
            with self.assertRaisesRegex(ValueError, "CALLER_DID_NOT_DIFFER"):
                probe(BINDING, CALLER, CALLER, Path(directory) / "same.json", self.runner(calls, {"OrganizationId": ORG, "UserId": CALLER}), True)

    def test_success_checks_mapping_and_header(self):
        with tempfile.TemporaryDirectory() as directory, patch("scripts.probe_effective_identity._cli_command", return_value=["fake"]):
            calls = []
            result = probe(BINDING, CALLER, EXPECTED, Path(directory) / "e.json",
                           self.runner(calls, {"OrganizationId": ORG, "UserId": "dddddddd-dddd-dddd-dddd-dddddddddddd"}, [{"systemuserid": EXPECTED, "azureactivedirectoryobjectid": CALLER}]), True)
            self.assertTrue(result["completed"])
            self.assertEqual(len(calls), 4)
            self.assertNotIn("CallerObjectId: " + CALLER, calls[0])
            self.assertIn("CallerObjectId: " + CALLER, calls[3])
            self.assertIn("azureactivedirectoryobjectid", calls[1][calls[1].index("--path") + 1])
            paths = [urllib.parse.unquote(c[c.index("--path") + 1]) for c in calls]
            self.assertIn("operator='eq'", paths[1])
            self.assertIn("operator='eq-userid'", paths[2])
            self.assertIn("operator='eq-userid'", paths[3])
            self.assertEqual(json.loads((Path(directory) / "e.json").read_text())["impersonatedUser"]["systemUserId"], EXPECTED)

    def test_missing_or_duplicate_expected_user_fails(self):
        with tempfile.TemporaryDirectory() as directory, patch("scripts.probe_effective_identity._cli_command", return_value=["fake"]):
            who = {"OrganizationId": ORG, "UserId": "dddddddd-dddd-dddd-dddd-dddddddddddd"}
            with self.assertRaisesRegex(ValueError, "EXPECTED_USER_NOT_UNIQUE"):
                probe(BINDING, CALLER, EXPECTED, Path(directory) / "missing.json", self.runner([], who, []), True)
            with self.assertRaisesRegex(ValueError, "EXPECTED_USER_MAPPING_MISSING"):
                probe(BINDING, CALLER, EXPECTED, Path(directory) / "mapping.json", self.runner([], who, [{"systemuserid": EXPECTED}]), True)

    def test_ignored_header_or_ambiguous_impersonation_fails(self):
        who = {"OrganizationId": ORG, "UserId": "dddddddd-dddd-dddd-dddd-dddddddddddd"}
        with tempfile.TemporaryDirectory() as directory, patch("scripts.probe_effective_identity._cli_command", return_value=["fake"]):
            with self.assertRaisesRegex(ValueError, "IMPERSONATED_IDENTITY_MISMATCH"):
                probe(BINDING, CALLER, EXPECTED, Path(directory) / "ignored.json", self.runner([], who, [{"systemuserid": EXPECTED, "azureactivedirectoryobjectid": CALLER}], impersonated_user=who["UserId"]), True)
            with self.assertRaisesRegex(ValueError, "IMPERSONATED_USER_NOT_UNIQUE"):
                probe(BINDING, CALLER, EXPECTED, Path(directory) / "ambiguous.json", self.runner([], who, [{"systemuserid": EXPECTED, "azureactivedirectoryobjectid": CALLER}], impersonated_rows=[{"systemuserid": EXPECTED}, {"systemuserid": EXPECTED}]), True)


if __name__ == "__main__":
    unittest.main()
