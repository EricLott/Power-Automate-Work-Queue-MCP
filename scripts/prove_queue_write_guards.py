"""Opt-in direct-write comparison using disposable synthetic native items."""
import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap_tenant import _cli_command, _cli_request
from probe_effective_identity import probe
from probe_tenant_metadata import _validate_binding
from prove_native_queue_pause import FLOW_IDS

REGISTERED = '33fd4458-5922-5be7-85d1-07a9176c9957'
UNREGISTERED = 'd14ec06b-3109-57e6-b18e-43763044a876'


def exact_denial(result):
    if not result.returncode:
        return False
    try:
        return json.loads(result.stdout).get('error', {}).get('message') == 'LIFECYCLE_BYPASS'
    except (ValueError, AttributeError, TypeError):
        return False


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('binding', 'caller-object-id', 'expected-user-id', 'output'):
        p.add_argument('--' + arg, required=True)
    p.add_argument('--queue-key', default='qmcp-proof-20260912',
                   help='synthetic registered queue key present in the binding')
    p.add_argument('--registered-queue-id', default=REGISTERED,
                   help='native queue ID corresponding to --queue-key')
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    binding = json.loads(Path(a.binding).read_text(encoding='utf-8-sig'))
    origin, organization = _validate_binding(binding)
    caller, expected = str(uuid.UUID(a.caller_object_id)), str(uuid.UUID(a.expected_user_id))
    registered_queue = str(uuid.UUID(a.registered_queue_id))
    if binding.get('queueKeys') != [a.queue_key]:
        raise ValueError('EXACT_QUEUE_ALLOWLIST_REQUIRED')
    if not a.execute:
        print(json.dumps({'ready': True, 'tenantCalls': False}))
        return
    output = Path(a.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = {'classification': 'synthetic-native-direct-write-comparison',
                'organizationId': organization, 'completed': False,
                'queueKey': a.queue_key,
                'registeredQueueId': registered_queue, 'unregisteredQueueId': UNREGISTERED,
                'newItemIds': [str(uuid.uuid4()), str(uuid.uuid4())], 'cases': [],
                'cleanup': {'completed': False},
                'limitations': ['Second effective identity has existing administrator privileges; not least-privilege proof.',
                                'Registered Delete and companion-table matrix are outside this run.']}
    with output.open('x', encoding='utf-8') as stream:
        json.dump(evidence, stream, indent=2)
    def save():
        output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    identity = probe(binding, caller, expected, str(output) + '.identity.json', execute=True)
    if not identity['completed']:
        raise ValueError('IDENTITY_NOT_PROVEN')
    evidence['effectiveIdentityVerified'] = True
    cmd = _cli_command()
    def call(method, path, body=None, impersonate=False, capture=None):
        def runner(args, **kwargs):
            if impersonate:
                args = args + ['--header', 'CallerObjectId: ' + caller]
            result = subprocess.run(args, **kwargs)
            if capture is not None:
                capture['exactDenial'] = exact_denial(result)
            return result
        return _cli_request(cmd, origin, method, path, body, runner=runner)
    def rows(path):
        response = call('GET', path)
        if not isinstance(response.get('value'), list) or response.get('@odata.nextLink'):
            raise ValueError('UNVERIFIED_QUERY')
        return response['value']
    for flow in FLOW_IDS:
        if call('GET', 'workflows(' + flow + ')?$select=statecode').get('statecode') != 0:
            raise ValueError('FLOWS_MUST_BE_DRAFT')
    for queue, registered in ((registered_queue, True), (UNREGISTERED, False)):
        bindings = rows("qmcp_wqqueuebindings?$select=qmcp_key&$filter=qmcp_key eq '" + queue + "'&$top=2")
        if len(bindings) != (1 if registered else 0):
            raise ValueError('QUEUE_BINDING_MISMATCH')
        native = call('GET', 'workqueues(' + queue + ')?$select=name,statecode')
        if native.get('statecode') != 0 or 'qmcp' not in native.get('name', '').lower():
            raise ValueError('SYNTHETIC_ACTIVE_QUEUE_REQUIRED')
    forbidden, disposable = evidence['newItemIds']
    def item_rows(item):
        return rows('workqueueitems?$select=workqueueitemid,name,statecode,statuscode,_workqueueid_value&$filter=workqueueitemid eq ' + item + '&$top=2')
    if item_rows(forbidden) or item_rows(disposable):
        raise ValueError('FIXTURE_IDS_NOT_NEW')
    def deny(label, method, path, body):
        observed = {}
        try:
            call(method, path, body, True, observed)
        except ValueError:
            if not observed.get('exactDenial'):
                raise ValueError('EXPECTED_GUARD_FAULT_MISSING')
        else:
            raise ValueError('UNEXPECTED_DIRECT_WRITE_SUCCESS')
        evidence['cases'].append({'case': label, 'error': 'LIFECYCLE_BYPASS'})
        save()
    def body(item, queue):
        envelope = {'envelopeVersion': '1.0', 'contract': 'mail.v1',
                    'correlationId': item, 'deduplicationKey': item,
                    'source': {'kind': 'synthetic'},
                    'payload': {'subject': 'Synthetic direct-write proof',
                                'senderAddress': 'synthetic@example.invalid',
                                'bodyText': 'Synthetic guard validation only.'}}
        return {'workqueueitemid': item, 'name': 'qmcp disposable direct-write proof',
                'input': json.dumps(envelope), 'workqueueid@odata.bind': '/workqueues(' + queue + ')'}
    created = False
    try:
        deny('registered-create', 'POST', 'workqueueitems', body(forbidden, registered_queue))
        if item_rows(forbidden):
            raise ValueError('DENIED_CREATE_LEFT_ROW')
        call('POST', 'workqueueitems', body(disposable, UNREGISTERED), True)
        created = True
        current = item_rows(disposable)
        if len(current) != 1 or current[0].get('_workqueueid_value') != UNREGISTERED:
            raise ValueError('DISPOSABLE_CREATE_UNVERIFIED')
        evidence['cases'].append({'case': 'unregistered-create', 'verified': True})
        call('PATCH', 'workqueueitems(' + disposable + ')', {'name': 'qmcp disposable updated proof'}, True)
        before = item_rows(disposable)
        if len(before) != 1 or before[0].get('name') != 'qmcp disposable updated proof':
            raise ValueError('DISPOSABLE_UPDATE_UNVERIFIED')
        evidence['cases'].append({'case': 'unregistered-update', 'verified': True})
        deny('move-into-registered', 'PATCH', 'workqueueitems(' + disposable + ')',
             {'workqueueid@odata.bind': '/workqueues(' + registered_queue + ')'})
        if item_rows(disposable) != before:
            raise ValueError('DENIED_MOVE_CHANGED_ROW')
        call('DELETE', 'workqueueitems(' + disposable + ')', impersonate=True)
        if item_rows(disposable):
            raise ValueError('DISPOSABLE_DELETE_UNVERIFIED')
        created = False
        evidence['cases'].append({'case': 'unregistered-delete', 'verified': True})
        evidence['completed'] = True
    finally:
        # Only this invocation's known disposable item is eligible for cleanup.
        if created:
            remaining = item_rows(disposable)
            if len(remaining) == 1 and remaining[0].get('_workqueueid_value') == UNREGISTERED:
                call('DELETE', 'workqueueitems(' + disposable + ')')
        evidence['cleanup'] = {'completed': not item_rows(disposable) and not item_rows(forbidden)}
        evidence['completed'] = evidence['completed'] and evidence['cleanup']['completed']
        save()
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
