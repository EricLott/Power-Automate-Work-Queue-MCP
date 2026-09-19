import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class OperationsRunbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / 'docs' / 'operations-runbook.md').read_text(encoding='utf-8')

    def test_runbook_covers_required_failure_boundaries(self):
        for term in ('Missing connection or binding', 'Licensing or capacity failure', 'Owner departure or permission loss',
                     'Environment copy or target mismatch', 'Failed or interrupted import', 'MCP host unavailable',
                     'Worker timeout or lost response', 'Backlog, missed wake-up, or expired attempt', 'Core environment outage'):
            self.assertIn(term, self.text)

    def test_runbook_prohibits_false_success_and_self_notification(self):
        self.assertIn('No procedure below treats a timeout, missing output, or persisted `Running` record as proof of success.', self.text)
        self.assertIn('Core cannot reliably notify through the unavailable environment', self.text)
        self.assertIn('Do not silently resume, uninstall/reinstall', self.text)
        self.assertIn('A failed, denied, missing, timed-out or inconclusive observation remains incomplete.', self.text)


if __name__ == '__main__':
    unittest.main()
