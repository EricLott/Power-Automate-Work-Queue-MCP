import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { DataverseClient } from './dataverse.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

export function runCliBridge(payload) {
  return new Promise((resolve, reject) => {
    const child = spawn('python', [path.join(root, 'scripts/mcp_dataverse.py')], {
      cwd: root, windowsHide: true, shell: false, stdio: ['pipe', 'pipe', 'pipe'],
    });
    let output = '';
    const timer = setTimeout(() => { child.kill(); reject(new Error('DATAVERSE_CLI_TIMEOUT')); }, 135000);
    child.stdout.on('data', chunk => {
      output += chunk;
      if (Buffer.byteLength(output) > 1000000) { child.kill(); reject(new Error('RESPONSE_TOO_LARGE')); }
    });
    // Do not expose CLI stderr or credentials through the MCP result.
    child.stderr.resume();
    child.stdin.on('error', () => {});
    child.on('error', () => { clearTimeout(timer); reject(new Error('DATAVERSE_CLI_UNAVAILABLE')); });
    child.on('close', code => {
      clearTimeout(timer);
      try {
        const result = JSON.parse(output);
        if (code !== 0 || result.error) {
          const safe = typeof result.error === 'string' && /^[A-Z_]{2,80}$/.test(result.error);
          reject(new Error(safe ? result.error : 'DATAVERSE_CLI_FAILED'));
        } else resolve(result);
      } catch { reject(new Error('DATAVERSE_CLI_INVALID_RESPONSE')); }
    });
    child.stdin.end(JSON.stringify(payload));
  });
}

export class DataverseCliClient extends DataverseClient {
  constructor(binding, bridge = runCliBridge) {
    super(binding, () => null);
    this.bridge = bridge;
  }
  async request(route, body) {
    return this.bridge({ binding: this.binding, route, body });
  }
}
