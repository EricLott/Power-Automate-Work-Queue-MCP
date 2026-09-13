import unittest

from scripts.generate_native_connector_probe import CONNECTION, generate


QUEUE = "d14ec06b-3109-57e6-b18e-43763044a876"
NOTES = {
    "available": "11111111-1111-5111-8111-111111111111",
    "empty": "22222222-2222-5222-8222-222222222222",
    "paused": "33333333-3333-5333-8333-333333333333",
}


class NativeConnectorProbeTests(unittest.TestCase):
    def setUp(self):
        self.flow = generate(QUEUE, "proof-run-001", NOTES)
        self.definition = self.flow["properties"]["definition"]
        self.actions = self.definition["actions"]

    def test_action_inputs_and_synthetic_notes(self):
        self.assertEqual(self.flow["properties"]["connectionReferences"].keys(), {CONNECTION})
        for name in ("DequeueAvailable", "DequeueEmpty", "DequeuePaused"):
            params = self.actions[name]["inputs"]["parameters"]
            self.assertEqual(params["entityName"], "workqueues")
            self.assertEqual(params["actionName"], "Microsoft.Dynamics.CRM.Dequeue")
        for case, action in (("available", "RecordAvailable"), ("empty", "RecordEmpty"), ("paused", "RecordPaused")):
            params = self.actions[action]["inputs"]["parameters"]
            self.assertEqual(params["entityName"], "annotations")
            self.assertEqual(params["item/annotationid"], NOTES[case])
            self.assertIn("qmcp native connector proof proof-run-001 " + case, params["item/subject"])
            self.assertIn("runId", params["item/notetext"])
            self.assertIn("'runId', 'proof-run-001'", params["item/notetext"])
            self.assertIn("flowRunId", params["item/notetext"])
            self.assertIn("body", params["item/notetext"])
            self.assertIn("error", params["item/notetext"])

    def test_failure_run_afters_and_restoration(self):
        for record, dequeue in (("RecordAvailable", "DequeueAvailable"), ("RecordEmpty", "DequeueEmpty"), ("RecordPaused", "DequeuePaused")):
            self.assertEqual(self.actions[record]["runAfter"][dequeue], ["Succeeded", "Failed", "TimedOut"])
        self.assertEqual(self.actions["DequeueEmpty"]["runAfter"], {"RecordAvailable": ["Succeeded"]})
        self.assertEqual(self.actions["PauseQueue"]["runAfter"], {"RecordEmpty": ["Succeeded"]})
        self.assertEqual(self.actions["DequeuePaused"]["runAfter"], {"PauseQueue": ["Succeeded"]})
        self.assertEqual(self.actions["RestoreQueue"]["runAfter"]["RecordPaused"], ["Succeeded", "Failed", "TimedOut", "Skipped"])
        restore = self.actions["RestoreQueue"]["inputs"]["parameters"]
        self.assertEqual((restore["item/statecode"], restore["item/statuscode"]), (0, 1))

    def test_rejects_invalid_identifiers(self):
        with self.assertRaisesRegex(ValueError, "QUEUE_INVALID_UUID"):
            generate("bad", "proof-run-001", NOTES)
        with self.assertRaisesRegex(ValueError, "RUN_ID_INVALID"):
            generate(QUEUE, "bad run", NOTES)
        with self.assertRaisesRegex(ValueError, "NOTE_IDS_MUST_BE_DISTINCT"):
            generate(QUEUE, "proof-run-001", dict.fromkeys(NOTES, NOTES["available"]))

    def test_forbidden_external_operations_absent(self):
        operations = [a["inputs"]["host"]["operationId"] for a in self.actions.values()]
        self.assertNotIn("SendEmailV2", operations)
        self.assertNotIn("Http", operations)
        self.assertEqual(set(self.flow["properties"]["connectionReferences"]), {CONNECTION})


if __name__ == "__main__":
    unittest.main()
