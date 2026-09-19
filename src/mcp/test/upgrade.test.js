import test from 'node:test';
import assert from 'node:assert/strict';
import { compareUpgrade, planUpgrade } from '../upgrade.js';

const base = {
  version: '0.1.0.0', publisher: 'QueueFramework', prefix: 'qmcp',
  packages: [{ name: 'Core', requires: [] }, { name: 'Reference', requires: ['Core'] }],
  apiCatalog: { prefix: 'qmcp_WQ_', operations: ['Enqueue', 'Complete'] }
};

test('upgrade comparison permits additive packages and APIs while retaining identities', () => {
  const next = {
    ...base,
    version: '0.2.0.0',
    packages: [...base.packages, { name: 'Notifications', requires: ['Core'] }],
    apiCatalog: { prefix: 'qmcp_WQ_', operations: ['Enqueue', 'Complete', 'GetQueueHealth'] }
  };
  const result = compareUpgrade(base, next);
  assert.deepEqual(result.packageChanges, { retained: ['Core', 'Reference'], added: ['Notifications'] });
  assert.deepEqual(result.apiChanges.added, ['GetQueueHealth']);
  assert.equal(result.rollback.uninstallReinstall, false);
  assert.equal(result.tenantValidation, 'required');
});

test('upgrade comparison rejects breaking identity, dependency, API and version changes', () => {
  const cases = [
    ['UPGRADE_VERSION_NOT_NEWER', { ...base }],
    ['UPGRADE_PUBLISHER_CHANGED', { ...base, version: '0.2.0.0', publisher: 'Other' }],
    ['UPGRADE_PREFIX_CHANGED', { ...base, version: '0.2.0.0', prefix: 'other' }],
    ['UPGRADE_PACKAGE_REMOVED', { ...base, version: '0.2.0.0', packages: [{ name: 'Core', requires: [] }] }],
    ['UPGRADE_DEPENDENCY_REMOVED', { ...base, version: '0.2.0.0', packages: [{ name: 'Core', requires: [] }, { name: 'Reference', requires: [] }] }],
    ['UPGRADE_API_REMOVED', { ...base, version: '0.2.0.0', apiCatalog: { prefix: 'qmcp_WQ_', operations: ['Enqueue'] } }]
  ];
  for (const [error, next] of cases) assert.throws(() => compareUpgrade(base, next), new RegExp(error));
});

test('public upgrade plan is explicit about local-only evidence and recovery boundary', async () => {
  const result = await planUpgrade();
  assert.equal(result.classification, 'local-upgrade-procedure');
  assert.equal(result.status, 'candidate-only');
  assert.equal(result.tenantImport, 'not-run');
  assert.equal(result.tenantValidated, false);
  assert.equal(result.policy.activeAttemptHandling, 'pause-and-drain-before-import');
  assert.equal(result.rollback.uninstallReinstall, false);
  assert.equal(result.packagePlan.localArtifacts, 'verified');
});
