import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { preflightInstallation } from '../preflight.js';

const bindingPath = 'C:/safe/binding.json';
const result = {
  classification: 'read-only-live-installation-preflight',
  organizationId: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  environmentUrl: 'https://synthetic.crm.dynamics.com',
  observableComplete: true,
  ready: false,
  writesPerformed: false,
  clientdataIncluded: false,
};

test('live preflight requires an explicit host binding', async () => {
  await assert.rejects(preflightInstallation({ env: {} }), /ENVIRONMENT_BINDING_REQUIRED/);
});

test('live preflight passes a safe direct binding argument and preserves read-only result', async () => {
  let args;
  const actual = await preflightInstallation({
    env: { QMCP_ENVIRONMENT_BINDING: bindingPath },
    cwd: 'C:/workspace',
    run: async (received, options) => { args = { received, options }; return result; },
  });
  assert.deepEqual(actual, result);
  assert.deepEqual(args, { received: ['--binding', path.resolve(bindingPath)], options: { cwd: 'C:/workspace' } });
});

test('live preflight rejects a response that claims it performed writes', async () => {
  await assert.rejects(preflightInstallation({
    env: { QMCP_ENVIRONMENT_BINDING: bindingPath },
    run: async () => ({ ...result, writesPerformed: true }),
  }), /INSTALL_PREFLIGHT_INVALID_RESPONSE/);
});
