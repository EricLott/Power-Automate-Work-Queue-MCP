"""Narrow JSON/stdin bridge to the authenticated Dataverse CLI. No token export."""
import json
import re
import sys
import uuid

from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding

OPERATIONS = {
    'RegisterQueue', 'RegisterContract', 'Enqueue', 'GetItemStatus',
    'GetQueueHealth', 'StartTestRun', 'CancelTestRun', 'GetTestRun', 'CleanupTestRun',
}


def request(payload, runner=None):
    binding = payload.get('binding')
    if not isinstance(binding, dict):
        raise ValueError('DEVELOPMENT_BINDING_REQUIRED')
    origin, expected = _validate_binding(binding)
    queues = binding.get('queueKeys')
    if (not isinstance(queues, list) or not queues
            or any(not isinstance(q, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', q) for q in queues)
            or len(set(queues)) != len(queues)):
        raise ValueError('QUEUE_ALLOWLIST_REQUIRED')
    route, body = payload.get('route'), payload.get('body')
    if route != 'WhoAmI':
        if route not in {'qmcp_WQ_' + operation for operation in OPERATIONS}:
            raise ValueError('OPERATION_NOT_EXPOSED')
        if not isinstance(body, dict) or body.get('QueueKey') not in queues:
            raise ValueError('QUEUE_NOT_BOUND')
        if set(body) - {'QueueKey', 'RequestId', 'DataJson', 'ItemId', 'AttemptId', 'Generation', 'ExpectedVersion'}:
            raise ValueError('INPUT_INVALID')
        try:
            uuid.UUID(body['RequestId'])
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ValueError('REQUEST_ID_INVALID')
        if not isinstance(body.get('DataJson'), str) or len(body['DataJson'].encode('utf-8')) > 131072:
            raise ValueError('INPUT_TOO_LARGE')
    elif body is not None:
        raise ValueError('INPUT_INVALID')

    command = _cli_command()
    def call(method, relative, value=None):
        options = {} if runner is None else {'runner': runner}
        return _cli_request(command, origin, method, relative, value, **options)

    identity = call('GET', 'WhoAmI')
    if str(identity.get('OrganizationId', '')).lower() != expected:
        raise ValueError('ENVIRONMENT_MISMATCH')
    if route == 'WhoAmI':
        return identity
    return call('POST', route, body)


if __name__ == '__main__':
    try:
        text = sys.stdin.read(200001)
        if len(text.encode('utf-8')) > 200000:
            raise ValueError('INPUT_TOO_LARGE')
        print(json.dumps(request(json.loads(text)), separators=(',', ':')))
    except Exception as error:
        code = str(error) if isinstance(error, ValueError) and re.fullmatch(r'[A-Z_]{2,80}', str(error)) else 'DATAVERSE_CLI_FAILED'
        print(json.dumps({'error': code}))
        sys.exit(1)
