import { spawn } from 'node:child_process';
import { readFile, writeFile, mkdir, rename } from 'node:fs/promises';
import path from 'node:path';
import { root as defaultRoot } from './local.js';
import { DataverseClient } from './dataverse.js';

const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const hash = /^[a-f0-9]{64}$/;
function id(value) { if (!uuid.test(value)) throw new Error('REQUEST_ID_INVALID'); return value.toLowerCase(); }
async function context(opts) {
  const env = opts.env || process.env;
  if (!env.QMCP_ENVIRONMENT_BINDING) throw new Error('DEVELOPMENT_BINDING_REQUIRED');
  const bindingPath = path.resolve(env.QMCP_ENVIRONMENT_BINDING);
  const value = JSON.parse(await readFile(bindingPath, 'utf8'));
  const binding = new DataverseClient(value, () => null).binding;
  return { env, bindingPath, binding, directory: path.join(opts.root || defaultRoot, 'artifacts/deployments') };
}
function matches(record, c) {
  return record.organizationId?.toLowerCase() === c.binding.organizationId.toLowerCase()
    && record.environmentUrl === c.binding.environmentUrl;
}
async function optional(file) { try { return JSON.parse(await readFile(file, 'utf8')); } catch (e) { if (e.code === 'ENOENT') return null; throw e; } }
async function save(file, record) { const temp = file + '.tmp'; await writeFile(temp, JSON.stringify(record, null, 2)); await rename(temp, file); }
function launchPython(args, root) {
  return new Promise((resolve, reject) => {
    const child = spawn('python', args, { cwd: root, windowsHide: true, shell: false, detached: true, stdio: 'ignore' });
    child.once('error', () => reject(new Error('DEPLOYMENT_LAUNCH_FAILED')));
    child.once('spawn', () => { child.unref(); resolve({ pid: child.pid }); });
  });
}
export async function applyDeployment({ planHash, requestId }, opts = {}) {
  requestId = id(requestId);
  const c = await context(opts);
  if (!c.env.QMCP_DEPLOYMENT_SETTINGS || !c.env.QMCP_APPROVED_DEPLOYMENT_PLAN) throw new Error('DEPLOYMENT_APPROVAL_REQUIRED');
  if (!hash.test(planHash) || c.env.QMCP_APPROVED_DEPLOYMENT_PLAN !== planHash) throw new Error('PLAN_APPROVAL_MISMATCH');
  const settingsPath = path.resolve(c.env.QMCP_DEPLOYMENT_SETTINGS);
  JSON.parse(await readFile(settingsPath, 'utf8'));
  const file = path.join(c.directory, requestId + '.launch.json');
  const compatible = old => {
    if (old.planHash !== planHash || !matches(old, c) || old.settingsPath !== settingsPath || old.bindingPath !== c.bindingPath) throw new Error('REQUEST_CONFLICT');
    return old;
  };
  const old = await optional(file);
  if (old) return compatible(old);
  // A CLI-started request is also durable; do not start it a second time.
  const existing = await optional(path.join(c.directory, requestId + '.json'));
  if (existing) {
    if (existing.planHash !== planHash || !matches(existing, c)) throw new Error('REQUEST_CONFLICT');
    return { requestId, status: existing.status, journal: existing, liveState: 'unknown' };
  }
  const record = { requestId, planHash, organizationId: c.binding.organizationId, environmentUrl: c.binding.environmentUrl,
    settingsPath, bindingPath: c.bindingPath, status: 'LaunchRequested', liveState: 'unknown' };
  await mkdir(c.directory, { recursive: true });
  try { await writeFile(file, JSON.stringify(record, null, 2), { flag: 'wx' }); }
  catch (error) { if (error.code === 'EEXIST') return compatible(await optional(file)); throw error; }
  const root = opts.root || defaultRoot;
  const args = [path.join(root, 'scripts/deploy_release.py'), '--execute', '--binding', c.bindingPath,
    '--settings', settingsPath, '--approved-plan-hash', planHash, '--request-id', requestId];
  try {
    const launched = await (opts.launch || (a => launchPython(a, root)))(args);
    record.status = 'AwaitingJournal';
    if (Number.isInteger(launched?.pid)) record.processId = launched.pid;
  } catch { record.status = 'LaunchFailed'; record.error = 'DEPLOYMENT_LAUNCH_FAILED'; }
  await save(file, record);
  return record;
}
export async function deploymentStatus({ requestId }, opts = {}) {
  requestId = id(requestId);
  const c = await context(opts);
  const launch = await optional(path.join(c.directory, requestId + '.launch.json'));
  const journal = await optional(path.join(c.directory, requestId + '.json'));
  if (!launch && !journal) throw new Error('DEPLOYMENT_NOT_FOUND');
  if ((launch && !matches(launch, c)) || (journal && !matches(journal, c))
      || (launch && journal && launch.planHash !== journal.planHash)) throw new Error('DEPLOYMENT_RECORD_MISMATCH');
  return { requestId, source: 'local-deployment-journal', status: journal?.status || launch.status,
    liveState: 'unknown', ...(launch ? { launch } : {}), ...(journal ? { journal } : {}) };
}
