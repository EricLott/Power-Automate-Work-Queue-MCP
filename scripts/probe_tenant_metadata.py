"""Read-only Dataverse metadata preflight for the first development import.

This utility intentionally uses the same authenticated Dataverse CLI request
transport as ``bootstrap_tenant.py``.  It performs WhoAmI before metadata reads,
never sends POST/PATCH/DELETE, and writes only the requested JSON report path.
"""
import argparse
import json
import sys
import urllib.parse
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap_tenant import _cli_command, _cli_request
from generate_sources import uid


def _validate_binding(binding):
    origin = binding['environmentUrl'].rstrip('/')
    parsed = urllib.parse.urlparse(origin)
    if (parsed.scheme != 'https' or parsed.path or parsed.query or parsed.fragment
            or parsed.username or not parsed.hostname):
        raise ValueError('ENVIRONMENT_URL_INVALID')
    expected = str(uuid.UUID(binding['organizationId'])).lower()
    if binding.get('environmentClass') != 'development':
        raise ValueError('DEVELOPMENT_ENVIRONMENT_REQUIRED')
    return origin, expected


def probe(binding, output_path, runner=None):
    origin, expected = _validate_binding(binding)
    command = _cli_command()
    run = runner

    def get(relative, solution='WQCore'):
        return _cli_request(command, origin, 'GET', relative, solution=solution,
                            runner=run) if run else _cli_request(command, origin, 'GET', relative, solution=solution)

    who = get('WhoAmI')
    actual = str(uuid.UUID(who['OrganizationId'])).lower()
    if actual != expected:
        raise ValueError('ENVIRONMENT_MISMATCH')

    def query(entity, select, filter_text, top=5000):
        query_string = urllib.parse.urlencode({'$select': select, '$filter': filter_text, '$top': top})
        return get(entity + '?' + query_string).get('value', [])

    solution_names = ['WQCore', 'WQTesting', 'WQNotificationsEmail', 'WQReferenceSharedMailbox']
    solutions = []
    for solution_name in solution_names:
        solutions.extend(query('solutions', 'uniquename,version,friendlyname',
                               "uniquename eq '" + solution_name + "'", top=2))
    apis = query('customapis', 'uniquename,_plugintypeid_value',
                 "startswith(uniquename,'qmcp_WQ_')")
    flow_names = ['ProcessOne', 'OnQueueChanged', 'SweepQueue', 'Intake',
                  'Watchdog', 'TestCoordinator', 'EmailSender']
    flows = []
    for flow_name in flow_names:
        flow_id = uid('flow:' + flow_name)
        flows.extend(query('workflows', 'workflowid,name,statecode,statuscode,category',
                           'workflowid eq ' + flow_id, top=2))
    guards = query('sdkmessageprocessingsteps', 'sdkmessageprocessingstepid,name',
                   "startswith(name,'Queue framework guard: ')")
    report = {
        'classification': 'read-only-tenant-metadata-preflight',
        'organizationId': expected,
        'environmentUrl': origin,
        'whoAmI': {'organizationIdMatched': True},
        'solutions': [
            {'uniqueName': row.get('uniquename'), 'version': row.get('version'),
             'friendlyName': row.get('friendlyname')} for row in solutions
        ],
        'apiBindings': {
            'total': len(apis),
            'boundPluginType': sum(1 for row in apis if row.get('_plugintypeid_value')),
            'unboundPluginType': sum(1 for row in apis if not row.get('_plugintypeid_value')),
        },
        'flows': {
            'expected': flow_names,
            'found': [{'name': row.get('name'), 'statecode': row.get('statecode'),
                       'statuscode': row.get('statuscode')} for row in flows],
            'draftCount': sum(1 for row in flows if row.get('statecode') == 0),
        },
        'guardSteps': {'count': len(guards)},
        'writesPerformed': False,
        'limitations': [
            'Metadata reads are filtered public Web API queries and do not prove import, permissions, transactions, or connector activation.',
            'Results are bounded by the requested query page size.'
        ],
    }
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Read-only Dataverse metadata preflight')
    parser.add_argument('--binding', required=True, help='development binding JSON path')
    parser.add_argument('--output', required=True, help='JSON report output path')
    parser.add_argument('--dataverse-cli', action='store_true',
                        help='use the authenticated Dataverse CLI profile')
    args = parser.parse_args()
    if not args.dataverse_cli:
        raise SystemExit('DATAVERSE_CLI_REQUIRED')
    try:
        probe(json.loads(Path(args.binding).read_text(encoding='utf-8')), args.output)
    except (ValueError, KeyError, OSError, json.JSONDecodeError):
        raise SystemExit('TENANT_METADATA_PREFLIGHT_FAILED')
