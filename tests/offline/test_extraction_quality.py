import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "templates" / "tests" / "mail-extraction-quality.json"


class MailExtractionQualityFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_has_reviewed_unique_cases_and_valid_envelopes(self):
        fixture = self.fixture
        self.assertEqual("mail-extraction-quality-v1.2", fixture["fixtureVersion"])
        self.assertEqual("mail-extraction-v1.2", fixture["promptVersion"])
        self.assertEqual("not-run", fixture["tenantExecution"])
        self.assertEqual("https://learn.microsoft.com/en-us/ai-builder/add-inputs-prompt", fixture["providerInputPolicy"])
        self.assertEqual(["contact", "category"], fixture["expectedFields"])
        cases = fixture["cases"]
        self.assertEqual(6, len(cases))
        ids = [case.get("Id") for case in cases]
        self.assertEqual(6, len(set(ids)))
        self.assertTrue(all(isinstance(case_id, str) and case_id for case_id in ids))

        for case in cases:
            with self.subTest(case=case["Id"]):
                envelope = case["Input"]
                self.assertEqual("1.0", envelope["envelopeVersion"])
                self.assertEqual("mail.v1", envelope["contract"])
                self.assertTrue(envelope["correlationId"])
                self.assertEqual(envelope["correlationId"], envelope["deduplicationKey"])
                self.assertEqual({"kind"}, set(envelope["source"]))
                self.assertEqual("synthetic", envelope["source"]["kind"])
                payload = envelope["payload"]
                self.assertIsInstance(payload["subject"], str)
                self.assertIsInstance(payload["senderAddress"], str)
                self.assertIsInstance(payload["bodyText"], str)
                self.assertLessEqual(len(payload["bodyText"]), 1000)
                self.assertIn(case["ExpectedOutcome"], {"Processed", "Exception"})
                self.assertEqual(1, case["ExpectedAttemptCount"])
                expected = case["Expected"]
                self.assertTrue(set(expected).issubset({"contact", "category"}))
                self.assertNotIn("summary", expected)
                if payload["senderAddress"] and "contact" in expected:
                    self.assertEqual(payload["senderAddress"], expected.get("contact"))

    def test_failure_cases_do_not_expect_business_output(self):
        by_id = {case["Id"]: case for case in self.fixture["cases"]}
        for case_id in ("ambiguous-no-request", "missing-sender"):
            case = by_id[case_id]
            self.assertEqual("Exception", case["ExpectedOutcome"])
            self.assertEqual({}, case["Expected"])
            self.assertEqual("VALIDATEEXTRACTION_FAILED", case["ExpectedErrorCode"])
        self.assertEqual("", by_id["missing-sender"]["Input"]["payload"]["senderAddress"])
        adversarial = by_id["embedded-instruction-is-data"]
        self.assertEqual("Exception", adversarial["ExpectedOutcome"])
        self.assertEqual("PROMPT_FAILED", adversarial["ExpectedErrorCode"])
        self.assertEqual({}, adversarial["Expected"])


if __name__ == "__main__":
    unittest.main()
