import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const origin = /^https:\/\/[^/?#]+$/i;

function runPreflight(args, { cwd = root, spawnImpl = spawn } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawnImpl('python', [path.join(cwd, 'scripts/preflight_installation.py'), ...args], {
      cwd, windowsHide: true, shell: false, stdio: ['ignore', 'pipe', 'pipe'],
    });
    let output = '';
    let finished = false;
    const finish = (error, value) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      error ? reject(error) : resolve(value);
    };
    const timer = setTimeout(() => {
      child.kill?.();
      finish(new Error('INSTALL_PREFLIGHT_TIMEOUT'));
    }, 180000);
    child.stdout?.on('data', chunk => {
      output += chunk;
      if (Buffer.byteLength(output) > 2000000) {
        child.kill?.();
        finish(new Error('RESPONSE_TOO_LARGE'));
      }
    });
    child.stderr?.resume?.();
    child.on?.('error', () => finish(new Error('INSTALL_PREFLIGHT_UNAVAILABLE')));
    child.on?.('close', code => {
      if (finished) return;
      if (code !== 0) return finish(new Error('INSTALL_PREFLIGHT_FAILED'));
      try { finish(null, JSON.parse(output)); }
      catch { finish(new Error('INSTALL_PREFLIGHT_INVALID_RESPONSE')); }
    });
  });
}

function validateReadOnly(result) {
  if (!result || typeof result !== 'object' || Array.isArray(result) ||
      result.classification !== 'read-only-live-installation-preflight' ||
      !uuid.test(String(result.organizationId || '')) ||
      !origin.test(String(result.environmentUrl || '')) ||
      typeof result.observableComplete !== 'boolean' ||
      typeof result.ready !== 'boolean' ||
      result.writesPerformed !== false || result.clientdataIncluded !== false) {
    throw new Error('INSTALL_PREFLIGHT_INVALID_RESPONSE');
  }
  return result;
}

export async function preflightInstallation({ env = process.env, cwd = root, run = runPreflight } = {}) {
  const bindingPath = env.QMCP_ENVIRONMENT_BINDING;
  if (typeof bindingPath !== 'string' || bindingPath.length < 1 || bindingPath.length > 500) {
    throw new Error('ENVIRONMENT_BINDING_REQUIRED');
  }
  const result = await run(['--binding', path.resolve(bindingPath)], { cwd });
  return validateReadOnly(result);
}

