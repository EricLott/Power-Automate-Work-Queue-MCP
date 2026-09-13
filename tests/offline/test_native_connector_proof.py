import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import prove_native_connector as proof


class NativeConnectorProofTests(unittest.TestCase):
    binding = {
        "environmentUrl": "https://synthetic.crm.dynamics.com",
        "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "environmentClass": "development",
    }

    def _files(self, directory):
        base = Path(directory)
        binding = base / "binding.json"; binding.write_text(json.dumps(self.binding), encoding="utf-8")
        output = base / "evidence"
        return binding, output

    def test_dry_run_makes_no_cli_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            binding, output = self._files(directory)
            with patch("prove_native_connector._cli_command", side_effect=AssertionError("CLI called")):
                proof.main(["--binding", str(binding), "--output-dir", str(output), "--run-id", "dry-run"])
            self.assertFalse(output.exists())

    def _request(self, run_id, bad_paused=False):
        notes = {case: str(__import__("uuid").uuid5(__import__("uuid").UUID(proof.QUEUE), run_id + "|" + case)) for case in proof.CASES}
        actor = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        created = False
        active = False
        item_state = 0
        restored = []
        decoded = {
            "available": {"runId": run_id, "case": "available", "flowRunId": "flow-run", "actionStatus": "Succeeded", "body": {"workqueueitemid": proof.ITEM}},
            "empty": {"runId": run_id, "case": "empty", "flowRunId": "flow-run", "actionStatus": "Succeeded", "body": {}},
            "paused": {"runId": run_id, "case": "paused", "flowRunId": "flow-run", "actionStatus": "Failed", "body": {"error": {"errorCode": "RecordNotActive", "message": json.dumps({"errorCode": "RecordNotActive", "message": "Work queue " + proof.QUEUE + " is not active. It is in Paused status."})}}},
        }
        if bad_paused:
            decoded["paused"]["actionStatus"] = "Succeeded"

        def request(command, origin, method, path, body=None, **kwargs):
            nonlocal created, active, item_state
            if path == "WhoAmI": return {"OrganizationId": self.binding["organizationId"], "UserId": actor}
            if path.startswith("workflows(") and method == "GET":
                if path.startswith("workflows(" + str(__import__("uuid").uuid5(__import__("uuid").UUID(proof.QUEUE), run_id + "|flow"))):
                    return {"statecode": 1 if active else 0, "statuscode": 2 if active else 1}
                return {"statecode": 0, "statuscode": 1}
            if path.startswith("workqueues(" + proof.QUEUE + ")?"):
                return {"name": "qmcp empty native dequeue probe", "statecode": 0, "statuscode": 1}
            if path == "workitems-unexpected": raise AssertionError(path)
            if path.startswith("workqueueitems(" + proof.ITEM + ")?"):
                return {"name": "qmcp synthetic native probe", "input": "{}", "statecode": item_state, "statuscode": item_state, "expirydate": None}
            if path.startswith("qmcp_wqqueuebindings?") or path.startswith("workflows?") or path.startswith("annotations?"):
                if path.startswith("annotations?") and created:
                    note_id = next((value for value in notes.values() if value in path), None)
                    if note_id:
                        case = next(case for case, value in notes.items() if value == note_id)
                        if case == "available": item_state = 1
                        return {"value": [{"annotationid": note_id, "notetext": json.dumps(decoded[case]), "_createdby_value": actor}]}
                return {"value": []}
            if path.startswith("workqueueitems?"): return {"value": [{"workqueueitemid": proof.ITEM}]}
            if path == "workflows": created = True; return {}
            if path.startswith("workflows(") and method == "PATCH": active = body["statecode"] == 1; restored.append(("flow", body)); return {}
            if path.startswith("workqueues(") and method == "PATCH": restored.append(("queue", body)); return {}
            if path.startswith("workqueueitems(") and method == "PATCH":
                if item_state == 1 and body["statecode"] == 0:
                    raise ValueError("INVALID_NATIVE_IMMEDIATE_RESET")
                item_state = body["statecode"]; restored.append(("item", body)); return {}
            raise AssertionError((method, path, body))

        return request, notes, restored

    def _run(self, bad_paused=False):
        run_id = "connector-proof"
        request, notes, restored = self._request(run_id, bad_paused)
        with tempfile.TemporaryDirectory() as directory:
            binding, output = self._files(directory)
            patches = [patch("prove_native_connector._cli_command", return_value=["cli"]),
                       patch("prove_native_connector._cli_request", side_effect=request),
                       patch("generate_native_connector_probe.generate", return_value={"definition": {}}),
                       patch("prove_native_connector.time.monotonic", side_effect=[0, 1, 2]),
                       patch("prove_native_connector.time.sleep")]
            for item in patches: item.start()
            try:
                if bad_paused:
                    with self.assertRaisesRegex(ValueError, "PAUSED_RESULT_INVALID"):
                        proof.main(["--binding", str(binding), "--output-dir", str(output), "--run-id", run_id, "--execute"])
                    evidence = json.loads((output / "evidence.json").read_text(encoding="utf-8"))
                    self.assertFalse(evidence["completed"])
                else:
                    proof.main(["--binding", str(binding), "--output-dir", str(output), "--run-id", run_id, "--execute"])
                    evidence = json.loads((output / "evidence.json").read_text(encoding="utf-8"))
                    self.assertTrue(evidence["completed"])
                self.assertEqual([kind for kind, _ in restored], ["flow", "flow", "queue", "item", "item"])
                self.assertEqual([body["statecode"] for kind, body in restored if kind == "item"], [4, 0])
            finally:
                for item in reversed(patches): item.stop()

    def test_mocked_success_records_three_notes_and_restores(self):
        self._run()

    def test_failure_records_incomplete_evidence_and_restores(self):
        self._run(bad_paused=True)


if __name__ == "__main__":
    unittest.main()
