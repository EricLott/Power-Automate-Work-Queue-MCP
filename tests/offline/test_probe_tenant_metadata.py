import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

import scripts.probe_tenant_metadata as probe
from scripts.generate_sources import uid


class MetadataProbeTests(unittest.TestCase):
    def runner(self, calls):
        def run(args, **kwargs):
            calls.append(args)
            path = args[args.index('--path') + 1]
            class Result:
                returncode = 0
                stderr = ''
            if path.endswith('WhoAmI'):
                body = {'OrganizationId': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'}
            elif '/solutions?' in path:
                body = {'value': [{'uniquename': 'WQCore', 'version': '0.1.0.0'}]}
            elif '/customapis?' in path:
                body = {'value': [{'uniquename': 'qmcp_WQ_AcquireNext', '_plugintypeid_value': 'x'}]}
            elif '/workflows?' in path:
                expected = next(name for name in ['ProcessOne', 'OnQueueChanged', 'SweepQueue', 'Intake', 'Watchdog', 'TestCoordinator', 'EmailSender']
                                if uid('flow:' + name) in path)
                body = {'value': [{'workflowid': uid('flow:' + expected), 'name': expected, 'statecode': 1, 'statuscode': 2}]}
            elif '/sdkmessageprocessingsteps?' in path:
                body = {'value': [{'name': 'Queue framework guard: Create qmcp_wqdefinition'}]}
            else:
                raise AssertionError(path)
            Result.stdout = json.dumps(body)
            return Result()
        return run

    def test_probe_scopes_solutions_and_flows(self):
        calls = []
        with patch.object(probe, '_cli_command', return_value=['fake']):
            with tempfile.TemporaryDirectory() as directory:
                binding = {'environmentUrl': 'https://dev.crm.dynamics.com',
                           'organizationId': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
                           'environmentClass': 'development'}
                report = probe.probe(binding, Path(directory) / 'report.json', self.runner(calls))
        self.assertEqual(len(report['flows']['found']), 7)
        self.assertEqual(report['flows']['draftCount'], 0)
        self.assertEqual(report['solutions'][0]['uniqueName'], 'WQCore')
        workflow_paths = [a[a.index('--path') + 1] for a in calls if '/workflows?' in a[a.index('--path') + 1]]
        self.assertEqual(len(workflow_paths), 7)
        self.assertTrue(all('workflowid eq ' in urllib.parse.unquote_plus(path) for path in workflow_paths))

    def test_wrong_org_fails_closed(self):
        calls = []
        with patch.object(probe, '_cli_command', return_value=['fake']):
            with self.assertRaisesRegex(ValueError, 'ENVIRONMENT_MISMATCH'):
                probe.probe({'environmentUrl': 'https://dev.crm.dynamics.com',
                             'organizationId': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
                             'environmentClass': 'development'}, 'ignored.json',
                            self.runner(calls))
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
