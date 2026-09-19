import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { root } from './local.js';
import { planInstallation } from './install.js';

const policyPath = path.join(root, 'config/upgrade-policy.json');
const versionPattern = /^\d+(?:\.\d+){1,3}$/;
const names = value => Array.isArray(value) ? new Set(value) : new Set();

function versionParts(value) {
  if (typeof value !== 'string' || !versionPattern.test(value)) throw new Error('UPGRADE_VERSION_INVALID');
  return value.split('.').map(Number);
}

function assertVersionIncrease(from, to) {
  const left = versionParts(from), right = versionParts(to);
  for (let i = 0; i < Math.max(left.length, right.length); i++) {
    const a = left[i] || 0, b = right[i] || 0;
    if (b > a) return;
    if (b < a) throw new Error('UPGRADE_VERSION_DECREASED');
  }
  throw new Error('UPGRADE_VERSION_NOT_NEWER');
}

function packageMap(release) {
  if (!release || !Array.isArray(release.packages) || !release.packages.length) throw new Error('UPGRADE_RELEASE_INVALID');
  const result = new Map();
  for (const pkg of release.packages) {
    if (!pkg || typeof pkg.name !== 'string' || !/^[A-Za-z][A-Za-z0-9]*$/.test(pkg.name) || result.has(pkg.name)) throw new Error('UPGRADE_RELEASE_INVALID');
    const requires = pkg.requires === undefined ? [] : pkg.requires;
    if (!Array.isArray(requires) || requires.some(value => typeof value !== 'string') || new Set(requires).size !== requires.length) throw new Error('UPGRADE_RELEASE_INVALID');
    result.set(pkg.name, { ...pkg, requires: [...requires].sort() });
  }
  for (const pkg of result.values()) if (pkg.requires.some(dep => !result.has(dep) || dep === pkg.name)) throw new Error('UPGRADE_RELEASE_INVALID');
  return result;
}

function apiOperations(value) {
  if (!value || typeof value !== 'object' || typeof value.prefix !== 'string' || !Array.isArray(value.operations)) throw new Error('UPGRADE_API_CATALOG_INVALID');
  if (new Set(value.operations).size !== value.operations.length || value.operations.some(operation => typeof operation !== 'string' || !/^[A-Za-z][A-Za-z0-9]*$/.test(operation))) throw new Error('UPGRADE_API_CATALOG_INVALID');
  return new Set(value.operations);
}

/**
 * Compare two release descriptors without contacting a tenant. The previous
 * descriptor is supplied only by offline tests or a release-review harness;
 * the public MCP plan is deliberately candidate-only.
 */
export function compareUpgrade(previous, current) {
  if (!previous || !current || typeof previous !== 'object' || typeof current !== 'object') throw new Error('UPGRADE_RELEASE_INVALID');
  assertVersionIncrease(previous.version, current.version);
  if (previous.publisher !== current.publisher) throw new Error('UPGRADE_PUBLISHER_CHANGED');
  if (previous.prefix !== current.prefix) throw new Error('UPGRADE_PREFIX_CHANGED');
  const oldPackages = packageMap(previous), newPackages = packageMap(current);
  const addedPackages = [...newPackages.keys()].filter(name => !oldPackages.has(name)).sort();
  const retainedPackages = [...oldPackages.keys()].sort();
  for (const name of retainedPackages) {
    if (!newPackages.has(name)) throw new Error('UPGRADE_PACKAGE_REMOVED');
    const before = names(oldPackages.get(name).requires), after = names(newPackages.get(name).requires);
    for (const dependency of before) if (!after.has(dependency)) throw new Error('UPGRADE_DEPENDENCY_REMOVED');
  }
  const oldApis = apiOperations(previous.apiCatalog), newApis = apiOperations(current.apiCatalog);
  for (const operation of oldApis) if (!newApis.has(operation)) throw new Error('UPGRADE_API_REMOVED');
  return {
    compatible: true,
    fromVersion: previous.version,
    toVersion: current.version,
    packageChanges: { retained: retainedPackages, added: addedPackages },
    apiChanges: { retained: [...oldApis].sort(), added: [...newApis].filter(operation => !oldApis.has(operation)).sort() },
    rollback: { uninstallReinstall: false, approvedRecovery: 'forward-fix-or-environment-recovery' },
    tenantValidation: 'required'
  };
}

function validatePolicy(policy) {
  if (!policy || policy.version !== '1' || policy.activeAttemptHandling !== 'pause-and-drain-before-import' || policy.incomingEvents !== 'retain-and-reconcile-after-cutover' || policy.workerCutover !== 'one-compatible-version-per-queue' || policy.failureHandling !== 'stop-at-failed-package-and-preserve-journal' || policy.rollback?.uninstallReinstall !== false || policy.rollback?.approvedRecovery !== 'forward-fix-or-environment-recovery' || policy.tenantValidationRequired !== true) throw new Error('UPGRADE_POLICY_INVALID');
  return policy;
}

export async function planUpgrade() {
  const release = JSON.parse(await readFile(path.join(root, 'config/release.json'), 'utf8'));
  const catalog = JSON.parse(await readFile(path.join(root, 'config/api-catalog.json'), 'utf8'));
  const registration = JSON.parse(await readFile(path.join(root, 'config/registration.json'), 'utf8'));
  const policy = validatePolicy(JSON.parse(await readFile(policyPath, 'utf8')));
  const installation = await planInstallation();
  const operations = apiOperations(catalog);
  return {
    classification: 'local-upgrade-procedure',
    status: 'candidate-only',
    releaseVersion: release.version,
    publisher: release.publisher,
    prefix: release.prefix,
    packagePlan: { installOrder: installation.installOrder, localArtifacts: installation.localArtifacts },
    stableIdentity: { apiPrefix: catalog.prefix, apiCount: operations.size, registrationVersion: registration.version, registrationPath: 'config/registration.json' },
    policy,
    rollback: policy.rollback,
    tenantValidated: false,
    tenantImport: 'not-run',
    limitations: [
      'A real upgrade must inspect active attempts and native queue state before import.',
      'Managed import, queue migration, customer-flow continuity and recovery require a real development tenant.',
      'Uninstall/reinstall is not represented as rollback.'
    ]
  };
}
