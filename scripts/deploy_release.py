"""Explicit, hash-bound development imports with a durable execution journal.

The operator supplies the reviewed hash on the CLI. No MCP approval Boolean is
accepted. Imports remain Draft; managed promotion and flow activation are separate.
"""
import argparse
import hashlib
import json
import re
import subprocess
import urllib.parse
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET

import bootstrap_tenant as registration
from generate_sources import ROOT, uid
from probe_tenant_metadata import _validate_binding
from preflight_installation import preflight as live_preflight

PACKAGES = {'WQCore', 'WQTesting', 'WQNotificationsEmail', 'WQReferenceSharedMailbox'}
FLOWS = ['ProcessOne', 'OnQueueChanged', 'SweepQueue', 'Intake', 'Watchdog', 'TestCoordinator', 'EmailSender']


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _query(binding):
    origin, _ = _validate_binding(binding)
    command = registration._cli_command()
    return lambda method, relative, body=None: registration._cli_request(command, origin, method, relative, body)


def _inputs(binding, settings, root):
    origin, organization = _validate_binding(binding)
    queues = binding.get('queueKeys')
    if not isinstance(queues, list) or not queues or any(not isinstance(q, str) or not re.fullmatch('[a-z][a-z0-9_-]{0,63}', q) for q in queues) or len(set(queues)) != len(queues):
        raise ValueError('QUEUE_ALLOWLIST_REQUIRED')
    if set(settings) != PACKAGES:
        raise ValueError('DEPLOYMENT_SETTINGS_REQUIRED')
    release = json.loads((root / 'config/release.json').read_text(encoding='utf-8'))
    entries = release.get('packages', [])
    if len(entries) != len(PACKAGES) or {p.get('name') for p in entries} != PACKAGES:
        raise ValueError('RELEASE_PACKAGES_INVALID')
    dependencies = {p['name']: p.get('requires', []) for p in entries}
    if any(not isinstance(d, list) or any(not isinstance(n, str) or n not in PACKAGES for n in d) or len(set(d)) != len(d) for d in dependencies.values()):
        raise ValueError('RELEASE_DEPENDENCIES_INVALID')
    order = []
    while len(order) < len(entries):
        ready = sorted(n for n, deps in dependencies.items() if n not in order and isinstance(deps, list) and set(deps).issubset(order))
        if not ready:
            raise ValueError('RELEASE_DEPENDENCIES_INVALID')
        order.extend(ready)
    manifest = json.loads((root / 'artifacts/packages/manifest.json').read_text(encoding='utf-8'))
    expected = {n + suffix + '.zip' for n in PACKAGES for suffix in ('', '_managed')}
    files = manifest.get('files', [])
    if (manifest.get('version') != release['version'] or len(files) != len(expected)
            or any(not isinstance(e, dict) or not isinstance(e.get('file'), str) or e['file'] not in expected
                   or not re.fullmatch('[a-fA-F0-9]{64}', str(e.get('sha256', ''))) for e in files)
            or {e['file'] for e in files} != expected):
        raise ValueError('INSTALL_MANIFEST_INVALID')
    artifacts = {}
    for entry in files:
        file = root / 'artifacts/packages' / entry['file']
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != entry['sha256'].lower():
            raise ValueError('PACKAGE_HASH_MISMATCH')
        artifacts[entry['file']] = entry['sha256'].lower()
    mappings = {}
    for name in order:
        file = Path(settings[name]).resolve()
        data = json.loads(file.read_text(encoding='utf-8-sig'))
        refs = data.get('ConnectionReferences')
        if not isinstance(refs, list) or not refs or any(not all(isinstance(r.get(k), str) and r[k] for k in ('LogicalName', 'ConnectionId', 'ConnectorId')) for r in refs):
            raise ValueError('CONNECTION_MAPPING_REQUIRED')
        source = ET.parse(root / 'solutions' / name / 'src/Other/Customizations.xml').getroot()
        expected_refs = {r.get('connectionreferencelogicalname'): r.findtext('connectorid') for r in source.findall('./connectionreferences/connectionreference')}
        if len(refs) != len(expected_refs) or {r['LogicalName']: r['ConnectorId'] for r in refs} != expected_refs:
            raise ValueError('CONNECTION_MAPPING_MISMATCH')
        mappings[name] = {'path': str(file), 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(), 'connectionReferences': sorted(r['LogicalName'] for r in refs)}
    registration_hashes = {name: hashlib.sha256((root / 'config' / name).read_bytes()).hexdigest() for name in ('registration.json', 'api-catalog.json')}
    return {'environmentUrl': origin, 'organizationId': organization, 'releaseVersion': release['version'],
            'packageMode': 'unmanaged-development', 'installOrder': order, 'artifacts': artifacts,
            'settings': mappings, 'queueKeys': sorted(queues), 'registrationHashes': registration_hashes, 'releaseFingerprint': digest(release), 'activation': False}


def plan(binding, settings, root=ROOT, query=None):
    root = Path(root)
    inputs = _inputs(binding, settings, root)
    query = query or _query(binding)
    identity = query('GET', 'WhoAmI')
    if str(identity.get('OrganizationId', '')).lower() != inputs['organizationId']:
        raise ValueError('ENVIRONMENT_MISMATCH')
    installed = []
    for name in inputs['installOrder']:
        params = urllib.parse.urlencode({'$select': 'solutionid,uniquename,version,ismanaged', '$filter': "uniquename eq '" + name + "'", '$top': 2})
        rows = query('GET', 'solutions?' + params).get('value', [])
        if len(rows) > 1:
            raise ValueError('INSTALLATION_AMBIGUOUS')
        if rows and rows[0].get('ismanaged'):
            raise ValueError('MANAGED_TARGET_REQUIRES_RELEASE_UPGRADE')
        if rows and rows[0].get('version') != inputs['releaseVersion']:
            raise ValueError('COMPATIBILITY_REVIEW_REQUIRED')
        installed.append({'name': name, 'records': rows})
    flows = []
    for name in FLOWS:
        params = urllib.parse.urlencode({'$select': 'workflowid,statecode,statuscode', '$filter': 'workflowid eq ' + uid('flow:' + name), '$top': 2})
        rows = query('GET', 'workflows?' + params).get('value', [])
        if len(rows) > 1 or any(r.get('statecode') != 0 for r in rows):
            raise ValueError('FLOW_QUIESCENCE_REQUIRED')
        flows.append({'name': name, 'records': rows})
    body = {**inputs, 'installed': installed, 'flows': flows,
            'manualPrerequisites': ['Verify Dataverse and Power Automate entitlements, request capacity, and any AI Builder capacity.',
                                    'Verify deployment identity privileges and connection ownership in the target.',
                                    'Register the intended queue and contracts; run supported smoke and acceptance tests.',
                                    'Review prompt/mailbox bindings before separately approving flow activation.',
                                    'This repository candidate is not a signed managed production release.'],
            'steps': ['Import packages in dependency order with explicit connection settings',
                      'Repair all API and guard registrations, including existing APIs',
                      'Read installed component health; retain manual prerequisites',
                      'Leave flows Draft for separately validated activation']}
    return {**body, 'planHash': digest(body)}


def _save(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temp.replace(path)


def apply(binding, settings, approved_hash, request_id, root=ROOT, query=None, run=None, bootstrap=None, preflight=None):
    root = Path(root)
    request_id = str(uuid.UUID(request_id))
    if not re.fullmatch('[a-f0-9]{64}', approved_hash):
        raise ValueError('APPROVED_PLAN_REQUIRED')
    inputs = _inputs(binding, settings, root)
    directory = root / 'artifacts/deployments'
    journal_path = directory / (request_id + '.json')
    input_hash = digest(inputs)
    if journal_path.exists():
        previous = json.loads(journal_path.read_text(encoding='utf-8'))
        if previous.get('planHash') != approved_hash or previous.get('inputHash') != input_hash:
            raise ValueError('REQUEST_CONFLICT')
        return previous
    current = plan(binding, settings, root, query)
    if current['planHash'] != approved_hash:
        raise ValueError('PLAN_STALE')
    directory.mkdir(parents=True, exist_ok=True)
    # A failed or interrupted deployment is never restarted from journal state
    # alone. Inspect it and make a new reviewed plan with a new request ID.
    record = {'requestId': request_id, 'planHash': approved_hash, 'inputHash': input_hash,
              'environmentUrl': current['environmentUrl'], 'organizationId': current['organizationId'],
              'status': 'Running', 'steps': [], 'flowsActivated': False}
    with journal_path.open('x', encoding='utf-8') as stream:
        json.dump(record, stream)
    lock = directory / (current['organizationId'] + '.lock')
    acquired = False
    try:
        with lock.open('x', encoding='utf-8') as stream:
            json.dump({'requestId': request_id, 'journal': str(journal_path)}, stream)
        acquired = True
        if plan(binding, settings, root, query)['planHash'] != approved_hash:
            raise ValueError('PLAN_STALE')
        staged = directory / request_id
        staged.mkdir()
        for name in current['installOrder']:
            for source, target, expected in [
                (root / 'artifacts/packages' / (name + '.zip'), staged / (name + '.zip'), current['artifacts'][name + '.zip']),
                (Path(current['settings'][name]['path']), staged / (name + '.settings.json'), current['settings'][name]['sha256'])]:
                payload = source.read_bytes()
                if hashlib.sha256(payload).hexdigest() != expected:
                    raise ValueError('PLAN_STALE')
                target.write_bytes(payload)
        for name in current['installOrder']:
            if digest(_inputs(binding, settings, root)) != input_hash:
                raise ValueError('PLAN_STALE')
            step = {'package': name, 'status': 'Importing'}
            record['steps'].append(step)
            _save(journal_path, record)
            args = ['pwsh', '-NoProfile', '-File', str(root / 'scripts/pac.ps1'), 'solution', 'import',
                    '--path', str(staged / (name + '.zip')),
                    '--settings-file', str(staged / (name + '.settings.json')), '--environment', current['environmentUrl'], '--publish-changes']
            result = run(args) if run else subprocess.run(args, capture_output=True, text=True, timeout=1800, check=False)
            diagnostic = (getattr(result, 'stdout', '') or '') + '\n' + (getattr(result, 'stderr', '') or '')
            diagnostic = re.sub(r'(?i)(bearer\s+|access_token["\s:=]+|refresh_token["\s:=]+)\S+', r'\1[REDACTED]', diagnostic)
            diagnostic = re.sub(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[REDACTED_TOKEN]', diagnostic)
            log = staged / (name + '.import.log')
            log.write_text(diagnostic[:200000], encoding='utf-8')
            step['log'] = str(log)
            if result.returncode:
                raise ValueError('SOLUTION_IMPORT_FAILED')
            step['status'] = 'Imported'
            _save(journal_path, record)
        record['registration'] = bootstrap() if bootstrap else registration.execute(binding, registration.plan()['planHash'], dataverse_cli=True)
        _save(journal_path, record)
        health = preflight() if preflight else live_preflight(binding)
        record['componentHealth'] = health
        if not health.get('observableComplete'):
            raise ValueError('POST_IMPORT_COMPONENT_CHECK_FAILED')
        record['affectedSolutions'] = (query or _query(binding))('GET', 'solutions?' + urllib.parse.urlencode({
            '$select': 'solutionid,uniquename,version', '$filter': ' or '.join("uniquename eq '" + n + "'" for n in current['installOrder']), '$top': 4})).get('value', [])
        if {s.get('uniquename') for s in record['affectedSolutions']} != PACKAGES:
            raise ValueError('POST_IMPORT_COMPONENT_CHECK_FAILED')
        record['status'] = 'ImportedAwaitingAcceptance'
    except Exception as error:
        record['status'] = 'Failed'
        record['error'] = str(error) if isinstance(error, ValueError) and re.fullmatch('[A-Z_]+', str(error)) else 'DEPLOYMENT_FAILED'
    finally:
        _save(journal_path, record)
        if acquired:
            lock.unlink()
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--binding', required=True)
    parser.add_argument('--settings', required=True, help='JSON map of solution names to settings file paths')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--approved-plan-hash')
    parser.add_argument('--request-id')
    args = parser.parse_args()
    try:
        binding = json.loads(Path(args.binding).read_text(encoding='utf-8-sig'))
        settings = json.loads(Path(args.settings).read_text(encoding='utf-8-sig'))
        if args.execute and (not args.approved_plan_hash or not args.request_id):
            raise ValueError('APPROVED_PLAN_AND_REQUEST_REQUIRED')
        result = apply(binding, settings, args.approved_plan_hash, args.request_id) if args.execute else plan(binding, settings)
        print(json.dumps(result, indent=2))
        if result.get('status') == 'Failed':
            raise SystemExit(1)
    except Exception as error:
        code = str(error) if re.fullmatch('[A-Z_]+', str(error)) else 'DEPLOYMENT_FAILED'
        # Detached MCP callers need a terminal record even when planning rejects
        # execution before apply() creates its journal. Never overwrite a record.
        if args.execute:
            try:
                request_id = str(uuid.UUID(args.request_id))
                origin, organization = _validate_binding(binding)
                directory = ROOT / 'artifacts/deployments'
                directory.mkdir(parents=True, exist_ok=True)
                with (directory / (request_id + '.json')).open('x', encoding='utf-8') as stream:
                    json.dump({'requestId': request_id, 'planHash': args.approved_plan_hash,
                               'organizationId': organization, 'environmentUrl': origin,
                               'status': 'Rejected', 'error': code, 'flowsActivated': False}, stream)
            except (ValueError, TypeError, KeyError, OSError, NameError):
                pass
        raise SystemExit(code)
