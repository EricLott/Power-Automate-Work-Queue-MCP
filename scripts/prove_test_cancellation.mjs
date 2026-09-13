// Explicit synthetic live proof. Creates one durable test item; retains its evidence.
import { Client } from '../src/mcp/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js';
import { StdioClientTransport } from '../src/mcp/node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js';
import { randomUUID } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const [flag, queueKey, output] = process.argv.slice(2);
if (!['--execute','--resume'].includes(flag) || !queueKey || !output || !process.env.QMCP_ENVIRONMENT_BINDING) throw new Error('EXPLICIT_EXECUTION_AND_BINDING_REQUIRED');
const binding = JSON.parse(await readFile(process.env.QMCP_ENVIRONMENT_BINDING, 'utf8'));
if (binding.environmentClass !== 'development' || !binding.queueKeys.includes(queueKey)) throw new Error('QUEUE_NOT_BOUND');
const client = new Client({ name: 'qmcp-cancellation-proof', version: '0.1.0' });
const prior = flag === '--resume' ? JSON.parse(await readFile(output, 'utf8')) : null;
if (prior && (prior.organizationId !== binding.organizationId || prior.queueKey !== queueKey || !prior.runId || !prior.cancelRequestId)) throw new Error('PROOF_RESUME_INVALID');
const proofId = prior?.proofId || randomUUID();
const evidence = prior || { classification: 'live-mcp-test-cancellation', proofId, organizationId: binding.organizationId, queueKey, startedAt: new Date().toISOString(), completed: false };
// Exclusive evidence creation prevents accidental overwrite of a previous run.
if (!prior) await writeFile(output, JSON.stringify(evidence, null, 2), { flag: 'wx' });
else { evidence.previousErrors = [...(evidence.previousErrors || []), evidence.error].filter(Boolean); delete evidence.error; evidence.resumedAt = new Date().toISOString(); }
async function call(name, args) {
  const response = await client.callTool({ name, arguments: args });
  const value = JSON.parse(response.content[0].text);
  if (response.isError) throw new Error(value.error);
  return value;
}
try {
  await client.connect(new StdioClientTransport({ command: 'node', args: [path.join(root, 'src/mcp/server.js')], env: { ...process.env }, stderr: 'pipe' }));
  evidence.identity = (await call('inspect_installation', {})).identity;
  evidence.startRequestId ||= randomUUID();
  await writeFile(output, JSON.stringify(evidence, null, 2));
  const run = evidence.runId ? { RunId: evidence.runId } : await call('start_test_run', { queueKey, requestId: evidence.startRequestId, cases: [{ Id: 'cancel-before-acquisition', Input: { envelopeVersion: '1.0', contract: 'mail.v1', correlationId: proofId, deduplicationKey: proofId, source: { kind: 'synthetic' }, payload: { subject: 'Synthetic cancellation proof', senderAddress: 'synthetic@example.invalid', bodyText: 'No external action is required.' } }, Expected: {} }] });
  evidence.runId = run.RunId;
  await writeFile(output, JSON.stringify(evidence, null, 2));
  const args = { queueKey, runId: run.RunId, requestId: evidence.cancelRequestId || randomUUID() };
  evidence.cancelRequestId = args.requestId;
  await writeFile(output, JSON.stringify(evidence, null, 2));
  const cancelled = await call('cancel_test_run', args);
  const replay = await call('cancel_test_run', args);
  const persisted = await call('test_evidence', { queueKey, runId: run.RunId });
  const status = await call('item_status', { queueKey, itemId: persisted.Results[0].ItemId });
  evidence.cancelRequestId = args.requestId;
  evidence.replayEqual = JSON.stringify(cancelled) === JSON.stringify(replay);
  evidence.runState = persisted.State;
  evidence.resultStates = persisted.Results.map(r => r.State);
  evidence.item = status;
  if (!evidence.replayEqual || persisted.State !== 'Cancelled' || persisted.Results.some(r => r.State !== 'Cancelled') || status.Outcome !== 'OnHold' || status.AttemptCount !== 0) throw new Error('CANCELLATION_PROOF_FAILED');
  evidence.completed = true;
} catch (error) {
  evidence.error = /^[A-Z_]+$/.test(error.message) ? error.message : 'PROOF_FAILED';
  process.exitCode = 1;
} finally {
  await client.close();
  await writeFile(output, JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify(evidence, null, 2));
}
