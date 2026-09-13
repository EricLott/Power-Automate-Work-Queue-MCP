import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from prove_reference_quality import digest, observe, validate


class ReferenceQualityProofTests(unittest.TestCase):
    def case(self, outcome="Processed"):
        return {
            "Id": "case-1",
            "Input": {"envelopeVersion": "1.0", "contract": "mail.v1", "correlationId": "c1", "deduplicationKey": "d1", "source": {"kind": "synthetic"}, "payload": {"subject": "Help", "senderAddress": "a@example.invalid", "bodyText": "Please help."}},
            "Expected": {"contact": "a@example.invalid", "category": "service"} if outcome == "Processed" else {},
            "ExpectedOutcome": outcome,
            "ExpectedAttemptCount": 1,
        }

    def test_validate_rejects_unbound_non_synthetic_fixture(self):
        binding = {"environmentUrl": "https://synthetic.crm.dynamics.com", "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "environmentClass": "development", "queueKeys": ["mail"]}
        with self.assertRaisesRegex(ValueError, "SYNTHETIC_QUEUE_REQUIRED"):
            validate(binding, {"queueKey": "mail"}, [self.case()])

    def test_validate_rejects_non_synthetic_input_and_unsupported_outcome(self):
        binding = {"environmentUrl": "https://synthetic.crm.dynamics.com", "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "environmentClass": "development", "queueKeys": ["qmcp-proof-test"]}
        ledger = {"queueKey": "qmcp-proof-test", "queue": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
        non_synthetic = self.case()
        non_synthetic["Input"]["source"] = {"kind": "mailbox"}
        with self.assertRaisesRegex(ValueError, "SYNTHETIC"):
            validate(binding, ledger, [non_synthetic])
        unsupported = self.case()
        unsupported["ExpectedOutcome"] = "Pending"
        with self.assertRaisesRegex(ValueError, "OUTCOME"):
            validate(binding, ledger, [unsupported])

    def test_pending_run_is_never_reported_complete_and_does_not_advance(self):
        run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        native_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        calls = []
        def call(method, path, body=None):
            calls.append((method, path))
            if path.startswith("qmcp_WQ_GetTestRun"):
                return {"ResultJson": json.dumps({"State": "Running", "Results": [{"CaseId": "case-1", "ItemId": native_id, "State": "Pending"}]})}
            if path.startswith("qmcp_emailrequests?"):
                return {"value": []}
            inp = self.case()["Input"]
            inp["deduplicationKey"] = digest(run_id + "|case-1|0")
            return {"workqueueitemid": native_id, "_workqueueid_value": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "uniqueidbyqueue": digest("qmcp-proof-test|" + digest(run_id + "|case-1|0")), "statecode": 0, "statuscode": 0, "input": json.dumps(inp)}
        evidence = {}
        observe(call, evidence, [self.case()], run_id, "qmcp-proof-test", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertFalse(evidence["complete"])
        self.assertFalse(any("AdvanceTestRun" in path for _, path in calls))

    def test_processed_requires_independent_business_provenance(self):
        run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        native_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        original = self.case()
        payload = json.loads(json.dumps(original["Input"]))
        payload["deduplicationKey"] = digest(run_id + "|case-1|0")
        source_key = digest(payload["deduplicationKey"])
        doc = {"testRun": run_id, "sourceKey": source_key, "contentHash": digest(json.dumps({"contract": payload["contract"], "source": payload["source"], "payload": payload["payload"]}, sort_keys=True, separators=(",", ":"))), "fields": {"contact": "a@example.invalid", "category": "service"}, "promptVersion": "mail-extraction-v1.1", "promptModelId": "model"}
        def call(method, path, body=None):
            if path.startswith("qmcp_WQ_GetTestRun"):
                return {"ResultJson": json.dumps({"State": "Passed", "Results": [{"CaseId": "case-1", "ItemId": native_id, "State": "Passed"}]})}
            if path.startswith("qmcp_emailrequests?"):
                return {"value": [{"qmcp_emailrequestid": "dddddddd-dddd-dddd-dddd-dddddddddddd", "qmcp_document": json.dumps(doc), "qmcp_key": digest("qmcp-proof-test|" + digest(run_id + "|case-1|0")), "qmcp_queuekey": "qmcp-proof-test"}]}
            return {"workqueueitemid": native_id, "_workqueueid_value": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "uniqueidbyqueue": digest("qmcp-proof-test|" + digest(run_id + "|case-1|0")), "statecode": 2, "statuscode": 2, "input": json.dumps(payload)}
        evidence = {}
        observe(call, evidence, [original], run_id, "qmcp-proof-test", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertTrue(evidence["complete"])
        self.assertTrue(evidence["checks"][0]["promptProvenancePresent"])

    def test_passed_run_with_pending_or_failed_result_cannot_complete(self):
        run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        native_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        case = self.case()
        def call(method, path, body=None):
            if path.startswith("qmcp_WQ_GetTestRun"):
                return {"ResultJson": json.dumps({"State": "Passed", "Results": [{"CaseId": "case-1", "ItemId": native_id, "State": "Pending"}]})}
            if path.startswith("qmcp_emailrequests?"):
                return {"value": []}
            inp = json.loads(json.dumps(case["Input"]))
            inp["deduplicationKey"] = digest(run_id + "|case-1|0")
            return {"workqueueitemid": native_id, "_workqueueid_value": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "uniqueidbyqueue": digest("qmcp-proof-test|" + digest(run_id + "|case-1|0")), "statecode": 1, "statuscode": 1, "input": json.dumps(inp)}
        evidence = {}
        observe(call, evidence, [case], run_id, "qmcp-proof-test", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertFalse(evidence["complete"])
        self.assertEqual(0, evidence["checks"][0]["businessRecordCount"])
        self.assertFalse(evidence["checks"][0]["businessEvidenceValid"])

    def test_passed_run_with_failed_result_cannot_complete_even_for_expected_exception(self):
        run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        native_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        case = self.case("Exception")
        def call(method, path, body=None):
            if path.startswith("qmcp_WQ_GetTestRun"):
                return {"ResultJson": json.dumps({"State": "Passed", "Results": [{"CaseId": "case-1", "ItemId": native_id, "State": "Failed"}]})}
            if path.startswith("qmcp_emailrequests?"):
                return {"value": []}
            inp = json.loads(json.dumps(case["Input"]))
            inp["deduplicationKey"] = digest(run_id + "|case-1|0")
            return {"workqueueitemid": native_id, "_workqueueid_value": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "uniqueidbyqueue": digest("qmcp-proof-test|" + digest(run_id + "|case-1|0")), "statecode": 4, "statuscode": 4, "input": json.dumps(inp)}
        evidence = {}
        observe(call, evidence, [case], run_id, "qmcp-proof-test", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertFalse(evidence["complete"])

    def test_observation_transport_failure_clears_previous_completion(self):
        evidence = {"complete": True, "checks": [{"old": "stale"}]}
        def call(method, path, body=None):
            raise ValueError("DATAVERSE_CLI_FAILED")
        with self.assertRaisesRegex(ValueError, "DATAVERSE_CLI_FAILED"):
            observe(call, evidence, [self.case()], "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "qmcp-proof-test", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertFalse(evidence["complete"])

    def test_failed_run_cannot_be_complete_even_with_rows(self):
        run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        native_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        case = self.case()
        def call(method, path, body=None):
            if path.startswith("qmcp_WQ_GetTestRun"):
                return {"ResultJson": json.dumps({"State": "Failed", "Results": [{"CaseId": "case-1", "ItemId": native_id, "State": "Failed"}]})}
            if path.startswith("qmcp_emailrequests?"):
                return {"value": []}
            inp = case["Input"]
            inp["deduplicationKey"] = digest(run_id + "|case-1|0")
            return {"workqueueitemid": native_id, "_workqueueid_value": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "uniqueidbyqueue": digest("qmcp-proof-test|" + digest(run_id + "|case-1|0")), "statecode": 4, "statuscode": 4, "input": json.dumps(inp)}
        evidence = {}
        observe(call, evidence, [case], run_id, "qmcp-proof-test", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertFalse(evidence["complete"])
        self.assertEqual(0, evidence["checks"][0]["businessRecordCount"])
        self.assertFalse(evidence["checks"][0]["businessEvidenceValid"])

    def test_duplicate_business_rows_are_recorded_as_invalid_evidence(self):
        run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        native_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        case = self.case()
        def call(method, path, body=None):
            if path.startswith("qmcp_WQ_GetTestRun"):
                return {"ResultJson": json.dumps({"State": "Passed", "Results": [{"CaseId": "case-1", "ItemId": native_id, "State": "Passed"}]})}
            if path.startswith("qmcp_emailrequests?"):
                return {"value": [{"qmcp_key": "same"}, {"qmcp_key": "same"}]}
            return {"workqueueitemid": native_id, "uniqueidbyqueue": digest("qmcp-proof-test|" + digest(run_id + "|case-1|0")), "statecode": 2, "statuscode": 2, "input": json.dumps({**case["Input"], "deduplicationKey": digest(run_id + "|case-1|0")})}
        evidence = {}
        observe(call, evidence, [case], run_id, "qmcp-proof-test", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertFalse(evidence["complete"])
        self.assertEqual(2, evidence["checks"][0]["businessRecordCount"])
        self.assertFalse(evidence["checks"][0]["businessEvidenceValid"])


if __name__ == "__main__":
    unittest.main()


