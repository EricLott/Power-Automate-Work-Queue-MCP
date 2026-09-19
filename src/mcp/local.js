import { spawn } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { readFile, mkdir, writeFile, realpath } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { DataverseClient } from './dataverse.js';
import { DataverseCliClient } from './cli.js';
import { validateFlow } from './flow-validation.js';

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export const state = path.resolve(process.env.QMCP_SIM_STATE || path.join(root, 'artifacts/local/state.json'));
export const dll = path.join(root, 'src/simulator/bin/Release/net8.0/QueueFramework.Simulator.dll');
export const hash = value => createHash('sha256').update(value).digest('hex');
let liveClient;
async function boundClient() {
  if (!process.env.QMCP_ENVIRONMENT_BINDING) return null;
  if (!liveClient) {
    const binding = JSON.parse(await readFile(process.env.QMCP_ENVIRONMENT_BINDING, 'utf8'));
    const transport = process.env.QMCP_DATAVERSE_TRANSPORT || 'cli';
    if (!['cli', 'token'].includes(transport)) throw new Error('DATAVERSE_TRANSPORT_INVALID');
    liveClient = transport === 'cli' ? new DataverseCliClient(binding) : new DataverseClient(binding, () => process.env.QMCP_DATAVERSE_TOKEN);
  }
  return liveClient;
}
export async function command(operation, queueKey, data = {}, fields = {}, { spawnProcess = spawn } = {}) {
  const allowed = ['RegisterQueue','RegisterContract','Enqueue','GetItemStatus','GetQueueHealth','RequestRetry','StartTestRun','CancelTestRun','GetTestRun','CleanupTestRun'];
  if (!allowed.includes(operation)) throw new Error('OPERATION_NOT_EXPOSED');
  if (!/^[a-z][a-z0-9_-]{0,63}$/.test(queueKey)) throw new Error('QUEUE_KEY_INVALID');
  const live = await boundClient();
  if (live) return live.invoke(operation, queueKey, data, fields, fields.RequestId || randomUUID());
  const payload = JSON.stringify({ ...fields, Operation: operation, QueueKey: queueKey, RequestId: fields.RequestId || randomUUID(), DataJson: JSON.stringify(data) });
  if (Buffer.byteLength(payload) > 180000) throw new Error('INPUT_TOO_LARGE');
  return new Promise((resolve, reject) => {
    const child = spawnProcess('dotnet', [dll], { cwd: root, env: { ...process.env, QMCP_SIM_STATE: state }, windowsHide: true, stdio: ['pipe','pipe','pipe'] });
    let output = '', done = false; const finish = (error, result) => { if (done) return; done = true; clearTimeout(timer); error ? reject(error) : resolve(result); };
    const timer = setTimeout(() => { finish(new Error('LOCAL_RUNTIME_TIMEOUT')); child.kill(); }, 30000);
    child.stdout.on('data', data => { output += data; if (Buffer.byteLength(output) > 1000000) { finish(new Error('LOCAL_RUNTIME_RESPONSE_TOO_LARGE')); child.kill(); } });
    // Drain diagnostics without retaining unbounded child-process output.
    child.stderr.resume();
    child.on('error', () => finish(new Error('LOCAL_RUNTIME_UNAVAILABLE')));
    child.on('close', code => { if (done) return; if (code !== 0) return finish(new Error('LOCAL_RUNTIME_FAILED')); try { const result = JSON.parse(output.trim()); if (result.Error) finish(new Error(result.Error)); else finish(null, result); } catch { finish(new Error('LOCAL_RUNTIME_RESPONSE_INVALID')); } });
    child.stdin.end(payload + '\n');
  });
}
export async function inspect() {
  const release = JSON.parse(await readFile(path.join(root, 'config/release.json'), 'utf8'));
  const live = await boundClient();
  if (live) return { mode: 'dataverse-development', target: live.binding.environmentUrl, release, identity: await live.verify(), liveGates: 'require-recorded-evidence' };
  return { mode: 'local-simulation', target: state, release, tenantConnected: false, liveGates: 'not-run' };
}
export async function plan(queueKey) {
  if (process.env.QMCP_ENVIRONMENT_BINDING) throw new Error('LOCAL_MODE_REQUIRED');
  if (!/^[a-z][a-z0-9_-]{0,63}$/.test(queueKey)) throw new Error('QUEUE_KEY_INVALID');
  const config = await readFile(path.join(root, 'config/reference.json'), 'utf8');
  const body = { version: 1, mode: 'local-simulation', queueKey, configHash: hash(config), target: state, operations: ['RegisterQueue','RegisterContract'] };
  return { ...body, planHash: hash(JSON.stringify(body)) };
}
export async function provision(queueKey, planHash) {
  const current = await plan(queueKey); if (current.planHash !== planHash) throw new Error('PLAN_STALE');
  const config = JSON.parse(await readFile(path.join(root, 'config/reference.json'), 'utf8'));
  // Only the local synthetic store is reachable; live deployment is a separate human-run script.
  let exists = false;
  try { await command('GetQueueHealth', queueKey); exists = true; }
  catch (error) { if (error.message !== 'QUEUE_NOT_FOUND') throw error; }
  if (!exists) await command('RegisterQueue', queueKey, config.policy);
  await command('RegisterContract', queueKey, config.contract);
  return { outcome: exists ? 'ContractVerifiedForExistingQueue' : 'Provisioned', mode: 'local-simulation', queueKey };
}
export async function scaffold(name) {
  if (!/^[a-z][a-z0-9_-]{0,40}$/.test(name)) throw new Error('NAME_INVALID');
  const directory = path.join(root, 'artifacts/scaffolds', name);
  await mkdir(path.dirname(directory), { recursive: true });
  // Exclusive directory creation avoids overwriting any customer work, including symlink destinations.
  const parent = await realpath(path.dirname(directory));
  if (!parent.startsWith((await realpath(root)) + path.sep)) throw new Error('PATH_INVALID');
  await mkdir(directory);
  const manifest = JSON.parse(await readFile(path.join(root, 'templates/catalog.json'), 'utf8'));
  const flowIds = Object.fromEntries(manifest.customerFlows.map(file => {
    const h = hash('qmcp:customer:' + name + ':' + file);
    return [file, `${h.slice(0,8)}-${h.slice(8,12)}-5${h.slice(13,16)}-a${h.slice(17,20)}-${h.slice(20,32)}`];
  }));
  for (const file of manifest.customerFlows) {
    if (!/^[A-Za-z]+\.json$/.test(file)) throw new Error('TEMPLATE_PATH_INVALID');
    const flow = JSON.parse(await readFile(path.join(root, 'templates/flows', file), 'utf8'));
    const remap = value => { if (value && typeof value === 'object') { if (value.workflowReferenceName) value.workflowReferenceName = flowIds['ProcessOne.json']; for (const child of Object.values(value)) remap(child); } };
    remap(flow);
    await writeFile(path.join(directory, file), JSON.stringify(flow, null, 2), { flag: 'wx' });
  }
  await writeFile(path.join(directory, 'ownership.json'), JSON.stringify({ owner: 'customer', name, flowIds, templateVersion: manifest.version, liveValidated: false }, null, 2), { flag: 'wx' });
  return { directory, templateVersion: manifest.version, liveValidated: false };
}
export async function validateScaffold(name) {
  if (!/^[a-z][a-z0-9_-]{0,40}$/.test(name)) throw new Error('NAME_INVALID');
  const directory = path.join(root, 'artifacts/scaffolds', name);
  const manifest = JSON.parse(await readFile(path.join(root, 'templates/catalog.json'), 'utf8'));
  const ownership = JSON.parse(await readFile(path.join(directory, 'ownership.json'), 'utf8'));
  const results = [];
  for (const file of manifest.customerFlows) {
    const actual = JSON.parse(await readFile(path.join(directory, file), 'utf8'));
    const expected = JSON.parse(await readFile(path.join(root, 'templates/flows', file), 'utf8'));
    const remap = value => { if (value && typeof value === 'object') { if (value.workflowReferenceName) value.workflowReferenceName = ownership.flowIds['ProcessOne.json']; for (const child of Object.values(value)) remap(child); } };
    remap(expected);
    results.push({ file, modifiedFromTemplate: hash(JSON.stringify(actual)) !== hash(JSON.stringify(expected)), jsonValid: !!actual.properties?.definition, staticValidation: validateFlow(actual) });
  }
  return { classification: 'local-template-drift-and-safety-check', files: results, tenantValidated: false, guidance: 'Modified customer logic needs the source validator and tenant testing; drift alone is not an error.' };
}
