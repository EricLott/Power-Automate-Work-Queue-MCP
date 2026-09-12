import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
delete process.env.QMCP_ENVIRONMENT_BINDING;
delete process.env.QMCP_DATAVERSE_TOKEN;
const root = path.resolve(import.meta.dirname, '../../..');
const config = JSON.parse(await readFile(path.join(root, 'config/reference.json')));
const envelope = { envelopeVersion: '1.0', contract: 'mail.v1', correlationId: 'synthetic', deduplicationKey: 'synthetic', source: { type: 'fixture' }, payload: { subject: 'Service', senderAddress: 'alex@example.com', bodyText: 'Need service' } };
async function connect(state) {
  const transport = new StdioClientTransport({ command: 'node', args: [path.join(root, 'src/mcp/server.js')], env: { ...process.env, QMCP_SIM_STATE: state }, stderr: 'pipe' });
  const client = new Client({ name: 'local-test', version: '1.0.0' }); await client.connect(transport); return client;
}
async function call(client, name, args) { const response = await client.callTool({ name, arguments: args }); if (response.isError) throw new Error(JSON.parse(response.content[0].text).error); return JSON.parse(response.content[0].text); }
test('MCP session ends; independent runtime finishes durable test; a new session reads evidence', { timeout: 45000 }, async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'qmcp-')); const state = path.join(dir, 'state.json'); let client, worker;
  try {
    client = await connect(state);
    const tools = await client.listTools(); assert.equal(tools.tools.length, 10);
    const p = await call(client, 'plan_queue', { queueKey: 'mail' });
    await assert.rejects(call(client, 'provision_local_queue', { queueKey: 'mail', planHash: '0'.repeat(64) }), /PLAN_STALE/);
    await call(client, 'provision_local_queue', { queueKey: 'mail', planHash: p.planHash });
    const run = await call(client, 'start_test_run', { queueKey: 'mail', requestId: '11111111-1111-4111-a111-111111111111', cases: [{ Id: 'valid', Input: envelope, Expected: { contact: 'alex@example.com' }, Repetitions: 3 }] });
    await client.close(); client = undefined;
    worker = spawn('dotnet', [path.join(root, 'src/simulator/bin/Release/net8.0/QueueFramework.Simulator.dll'), '--worker', 'mail'], { env: { ...process.env, QMCP_SIM_STATE: state }, windowsHide: true, stdio: 'ignore' });
    client = await connect(state);
    let evidence;
    for (let i = 0; i < 60; i++) { evidence = await call(client, 'test_evidence', { queueKey: 'mail', runId: run.RunId }); if (evidence.State !== 'Running') break; await new Promise(resolve => setTimeout(resolve, 100)); }
    assert.equal(evidence.State, 'Passed'); assert.equal(evidence.Results.length, 3);
    assert.ok(evidence.Results.every(r => r.Evidence.fields.contact === 'alex@example.com'));
    const result = await call(client, 'cleanup_test', { queueKey: 'mail', runId: run.RunId }); assert.ok(result.Results.every(r => r.Cleanup === 'Completed'));
  } finally { if (client) await client.close(); if (worker) { worker.kill(); await new Promise(resolve => worker.once('exit', resolve)); } await rm(dir, { recursive: true, force: true }); }
});
test('scaffolding rejects traversal and only exposes a local target', async () => {
  const { scaffold, inspect } = await import('../local.js');
  await assert.rejects(scaffold('../outside'), /NAME_INVALID/);
  assert.equal((await inspect()).tenantConnected, false);
  assert.equal(config.contract.Id, 'mail.v1');
});
