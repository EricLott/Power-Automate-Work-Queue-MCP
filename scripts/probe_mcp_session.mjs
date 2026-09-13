// Read-only end-to-end MCP probe using the explicit development binding.
import { Client } from '../src/mcp/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js';
import { StdioClientTransport } from '../src/mcp/node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
if (!process.env.QMCP_ENVIRONMENT_BINDING) throw new Error('DEVELOPMENT_BINDING_REQUIRED');
const client = new Client({ name: 'qmcp-readonly-probe', version: '0.1.0' });
try {
  await client.connect(new StdioClientTransport({ command: 'node', args: [path.join(root, 'src/mcp/server.js')], env: { ...process.env }, stderr: 'pipe' }));
  const tools = await client.listTools();
  const response = await client.callTool({ name: 'inspect_installation', arguments: {} });
  if (response.isError) throw new Error('MCP_INSPECTION_FAILED');
  const result = JSON.parse(response.content[0].text);
  if (result.mode !== 'dataverse-development' || !result.identity?.organizationId) throw new Error('LIVE_BINDING_NOT_VERIFIED');
  console.log(JSON.stringify({ classification: 'read-only-mcp-stdio-probe', transport: process.env.QMCP_DATAVERSE_TRANSPORT || 'cli', toolCount: tools.tools.length, target: result.target, organizationId: result.identity.organizationId, mutations: 0 }, null, 2));
} finally { await client.close(); }
