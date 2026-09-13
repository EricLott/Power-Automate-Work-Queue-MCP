// Read a persisted deployment through the actual MCP stdio interface.
import { Client } from '../src/mcp/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js';
import { StdioClientTransport } from '../src/mcp/node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const requestId = process.argv[2];
if (!requestId || !process.env.QMCP_ENVIRONMENT_BINDING) throw new Error('BINDING_AND_REQUEST_REQUIRED');
const client = new Client({ name: 'deployment-status-probe', version: '0.1.0' });
try {
  await client.connect(new StdioClientTransport({ command: 'node', args: [path.join(root, 'src/mcp/server.js')], env: { ...process.env }, stderr: 'pipe' }));
  const response = await client.callTool({ name: 'deployment_status', arguments: { requestId } });
  if (response.isError) throw new Error('DEPLOYMENT_STATUS_FAILED');
  const value = JSON.parse(response.content[0].text);
  console.log(JSON.stringify({ requestId, status: value.status, source: value.source, liveState: value.liveState,
    organizationId: value.journal?.organizationId, steps: value.journal?.steps?.map(s => ({ package: s.package, status: s.status })) }, null, 2));
} finally { await client.close(); }
