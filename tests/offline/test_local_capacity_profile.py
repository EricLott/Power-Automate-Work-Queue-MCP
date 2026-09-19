import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from profile_local_capacity import summarize, validate_args


class LocalCapacityProfileTests(unittest.TestCase):
    def test_profile_bounds_are_conservative(self):
        validate_args(1, 0.05)
        validate_args(100, 5)
        for items, interval, error in ((0, 0.2, "ITEM_COUNT_OUT_OF_RANGE"), (101, 0.2, "ITEM_COUNT_OUT_OF_RANGE"), (10, 0.01, "POLL_INTERVAL_OUT_OF_RANGE"), (10, 6, "POLL_INTERVAL_OUT_OF_RANGE")):
            with self.subTest(items=items, interval=interval):
                with self.assertRaisesRegex(ValueError, error):
                    validate_args(items, interval)

    def test_summary_labels_local_observations_without_tenant_claims(self):
        state = {
            "Native": {"1": {"Queue": "capacity", "Status": "Processed"}},
            "Rows": {
                "command:1": {"Kind": "command", "Queue": "capacity", "Body": '{"Operation":"Enqueue"}'},
                "command:2": {"Kind": "command", "Queue": "capacity", "Body": '{"Operation":"RequestRetry"}'},
                "event:1": {"Kind": "event", "Queue": "capacity", "Body": '{"State":"Pending"}'},
            },
        }
        result = summarize(state, 1, 0.1, 0.2, 0.5, 4, 100, 140)
        self.assertEqual(result["classification"], "local-synthetic-capacity-profile")
        self.assertFalse(result["limits"]["tenantThroughputClaim"])
        self.assertFalse(result["limits"]["costClaim"])
        self.assertEqual(result["observations"]["retryRequests"], 1)
        self.assertEqual(result["observations"]["pendingSenderEvents"], 1)
        self.assertEqual(result["observations"]["storageGrowthBytes"], 40)


if __name__ == "__main__":
    unittest.main()
