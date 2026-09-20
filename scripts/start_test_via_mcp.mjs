// Start one explicitly bound synthetic test through MCP, then close the client.
import { Client } from '../src/mcp/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js';
import { StdioClientTransport } from '../src/mcp/node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const [queueKey, proofId, requestId] = process.argv.slice(2);
if (!queueKey || !proofId || !requestId || !process.env.QMCP_ENVIRONMENT_BINDING) throw new Error('EXPLICIT_EXECUTION_AND_BINDING_REQUIRED');
const binding = JSON.parse(await readFile(process.env.QMCP_ENVIRONMENT_BINDING, 'utf8'));
if (binding.environmentClass !== 'development' || !binding.queueKeys.includes(queueKey)) throw new Error('QUEUE_NOT_BOUND');
let client;
async function call(name, args) {
  const response = await client.callTool({ name, arguments: args });
  const value = JSON.parse(response.content[0].text);
  if (response.isError) throw new Error(/^[A-Z_]+$/.test(value.error || '') ? value.error : 'MCP_OPERATION_FAILED');
  return value;
}
try {
  client = new Client({ name: 'qmcp-autonomous-disconnect-proof', version: '0.1.0' });
  await client.connect(new StdioClientTransport({ command: 'node', args: [path.join(root, 'src/mcp/server.js')], env: { ...process.env }, stderr: 'pipe' }));
  const identity = (await call('inspect_installation', {})).identity;
  const run = await call('start_test_run', {
    queueKey,
    requestId,
    cases: [{
      Id: 'coordinator-autonomy',
      Input: {
        envelopeVersion: '1.0', contract: 'mail.v1', correlationId: proofId,
        deduplicationKey: proofId, source: { kind: 'synthetic' },
        payload: { subject: 'Printer is offline', senderAddress: 'alex@example.invalid', bodyText: 'Please restore the printer in the west office. It stopped working this morning.' },
      },
      Expected: { contact: 'alex@example.invalid', category: 'service' },
      ExpectedOutcome: 'Processed', ExpectedAttemptCount: 1,
      ExpectedRecordCount: 1, ExpectedUnwantedEffectCount: 0,
    }],
  });
  await client.close();
  client = undefined;
  console.log(JSON.stringify({ identity, run, clientClosed: true }));
} finally {
  if (client) await client.close();
}
