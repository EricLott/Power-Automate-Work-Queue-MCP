import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from deploy_release import apply, plan


BINDING = {
    "environmentUrl": "https://synthetic.crm.dynamics.com",
    "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "environmentClass": "development",
    "queueKeys": ["mail"],
}
NAMES = ("WQCore", "WQTesting", "WQNotificationsEmail", "WQReferenceSharedMailbox")


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir()
        (self.root / "artifacts" / "packages").mkdir(parents=True)
        packages = []
        for name in NAMES:
            packages.append({"name": name, "requires": [] if name == "WQCore" else ["WQCore"]})
            (self.root / "artifacts" / "packages" / f"{name}.zip").write_bytes(f"{name}-package".encode())
            logical = f"qmcp_{name.lower()}_dataverse"
            (self.root / f"{name}.json").write_text(json.dumps({"ConnectionReferences": [{"LogicalName": logical, "ConnectionId": "synthetic", "ConnectorId": "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps"}]}))
            source = self.root / "solutions" / name / "src" / "Other"
            source.mkdir(parents=True)
            (source / "Customizations.xml").write_text(f'<ImportExportXml><connectionreferences><connectionreference connectionreferencelogicalname="{logical}"><connectorid>/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps</connectorid></connectionreference></connectionreferences></ImportExportXml>')
        (self.root / "config" / "release.json").write_text(json.dumps({"version": "test", "packages": packages}))
        manifest = []
        import hashlib
        for name in NAMES:
            for suffix in ("", "_managed"):
                filename = f"{name}{suffix}.zip"
                artifact = self.root / "artifacts" / "packages" / filename
                if not artifact.exists():
                    artifact.write_bytes(f"{filename}-package".encode())
                manifest.append({"file": filename, "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()})
        (self.root / "artifacts" / "packages" / "manifest.json").write_text(json.dumps({"version": "test", "files": manifest}))
        (self.root / "config" / "registration.json").write_text("{}")
        (self.root / "config" / "api-catalog.json").write_text("{}")
        self.settings = {name: str(self.root / f"{name}.json") for name in NAMES}

    def query(self, organization=None, calls=None):
        expected = organization or BINDING["organizationId"]
        def request(method, relative, body=None):
            if calls is not None:
                calls.append((method, relative, body))
            if relative == "WhoAmI":
                return {"OrganizationId": expected}
            if relative.startswith("solutions?") and " or " in urllib.parse.unquote_plus(relative):
                return {"value": [{"solutionid": f"{name}-id", "uniquename": name, "version": "test"} for name in NAMES]}
            return {"value": []}
        return request

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_orders_dependencies_and_hashes_settings(self):
        result = plan(BINDING, self.settings, root=self.root, query=self.query())
        self.assertTrue(result["planHash"])
        self.assertEqual(("WQCore", "WQNotificationsEmail", "WQReferenceSharedMailbox", "WQTesting"), tuple(result["installOrder"]))
        before = result["planHash"]
        (self.root / "WQTesting.json").write_text(json.dumps({"ConnectionReferences": [{"LogicalName": "qmcp_wqtesting_dataverse", "ConnectionId": "changed", "ConnectorId": "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps"}]}))
        self.assertNotEqual(before, plan(BINDING, self.settings, root=self.root, query=self.query())["planHash"])

    def test_plan_reports_missing_settings_mapping(self):
        settings = dict(self.settings)
        del settings["WQTesting"]
        with self.assertRaisesRegex(ValueError, "DEPLOYMENT_SETTINGS_REQUIRED"):
            plan(BINDING, settings, root=self.root, query=self.query())

    def test_stale_plan_hash_does_not_mutate(self):
        calls = []
        result = plan(BINDING, self.settings, root=self.root, query=self.query(calls=calls))
        calls.clear()
        with self.assertRaisesRegex(ValueError, "PLAN_STALE"):
            apply(BINDING, self.settings, "0" * 64, "00000000-0000-0000-0000-000000000001", root=self.root, query=self.query(calls=calls))
        self.assertFalse(any(method != "GET" for method, _, _ in calls))
        self.assertFalse((self.root / "artifacts" / "deployments").exists())
        self.assertTrue(result["planHash"])

    def test_wrong_organization_does_not_import(self):
        calls = []
        query = self.query("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", calls)
        with self.assertRaisesRegex(ValueError, "ENVIRONMENT_MISMATCH"):
            plan(BINDING, self.settings, root=self.root, query=query)
        calls.clear()
        self.assertFalse(any(method != "GET" for method, relative, _ in calls))
        reviewed = plan(BINDING, self.settings, root=self.root, query=self.query())
        calls.clear()
        with self.assertRaisesRegex(ValueError, "ENVIRONMENT_MISMATCH"):
            apply(BINDING, self.settings, reviewed["planHash"], "00000000-0000-0000-0000-000000000004", root=self.root, query=query, run=lambda args: (_ for _ in ()).throw(AssertionError("imported")))
        self.assertFalse(any(method != "GET" for method, _, _ in calls))

    def test_request_replay_returns_same_journal_without_second_import(self):
        calls = []
        query = self.query(calls=calls)
        reviewed = plan(BINDING, self.settings, root=self.root, query=query)
        imports = []
        run = lambda args: imports.append(args) or type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        first = apply(BINDING, self.settings, reviewed["planHash"], "00000000-0000-0000-0000-000000000002", root=self.root, query=query, run=run, bootstrap=lambda: {}, preflight=lambda: {"observableComplete": True})
        self.assertEqual("ImportedAwaitingAcceptance", first["status"])
        self.assertEqual(4, len(imports))
        self.assertTrue(all("--settings-file" in args and "--environment" in args for args in imports))
        staged = str(self.root / "artifacts" / "deployments" / "00000000-0000-0000-0000-000000000002")
        self.assertTrue(all(any(staged in item for item in args) for args in imports))
        count = len(imports)
        second = apply(BINDING, self.settings, reviewed["planHash"], "00000000-0000-0000-0000-000000000002", root=self.root, query=query)
        self.assertEqual(first, second)
        self.assertEqual(count, len(imports))

    def test_failed_import_is_journaled_without_activation(self):
        calls = []
        query = self.query(calls=calls)
        reviewed = plan(BINDING, self.settings, root=self.root, query=query)
        def run(args):
            return type("Result", (), {"returncode": 1, "stdout": "", "stderr": "synthetic import failure"})()
        journal = apply(BINDING, self.settings, reviewed["planHash"], "00000000-0000-0000-0000-000000000003", root=self.root, query=query, run=run, bootstrap=lambda: {}, preflight=lambda: {"observableComplete": True})
        self.assertEqual("Failed", journal.get("status"))
        self.assertFalse(any("activate" in str(c).lower() for c in calls))

    def test_settings_change_after_approval_is_rejected_without_import(self):
        reviewed = plan(BINDING, self.settings, root=self.root, query=self.query())
        (self.root / "WQTesting.json").write_text(json.dumps({"ConnectionReferences": [{"LogicalName": "qmcp_wqtesting_dataverse", "ConnectionId": "changed", "ConnectorId": "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps"}]}))
        with self.assertRaisesRegex(ValueError, "PLAN_STALE"):
            apply(BINDING, self.settings, reviewed["planHash"], "00000000-0000-0000-0000-000000000005", root=self.root, query=self.query(), run=lambda args: (_ for _ in ()).throw(AssertionError("imported")))

    def test_settings_change_during_import_stops_before_next_package(self):
        reviewed = plan(BINDING, self.settings, root=self.root, query=self.query())
        calls = []
        def run(args):
            calls.append(args)
            if len(calls) == 1:
                (self.root / "WQTesting.json").write_text(json.dumps({"ConnectionReferences": [{"LogicalName": "qmcp_wqtesting_dataverse", "ConnectionId": "changed", "ConnectorId": "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps"}]}))
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        journal = apply(BINDING, self.settings, reviewed["planHash"], "00000000-0000-0000-0000-000000000006", root=self.root, query=self.query(), run=run, bootstrap=lambda: {}, preflight=lambda: {"observableComplete": True})
        self.assertEqual("Failed", journal["status"])
        self.assertEqual(1, len(calls))


if __name__ == "__main__":
    unittest.main()
