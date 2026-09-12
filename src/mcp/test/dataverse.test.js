import test from 'node:test';
import assert from 'node:assert/strict';
import { DataverseClient } from '../dataverse.js';
const id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const binding = { environmentUrl: 'https://synthetic.crm.dynamics.com', organizationId: id, environmentClass: 'development', queueKeys: ['mail'] };
const response = body => ({ ok: true, text: async () => JSON.stringify(body) });
test('Dataverse adapter verifies identity, scopes queue, and preserves request ID', async () => {
  const calls = []; const client = new DataverseClient(binding, () => 'synthetic-test-token', async (url, options) => { calls.push({ url, options }); return response(url.endsWith('WhoAmI') ? { OrganizationId: id, UserId: id } : { ResultJson: '{"Outcome":"Health"}' }); });
  assert.equal((await client.invoke('GetQueueHealth', 'mail', {}, {}, id)).Outcome, 'Health');
  assert.equal(calls.length, 2); assert.equal(calls[1].options.redirect, 'error'); assert.equal(JSON.parse(calls[1].options.body).RequestId, id);
  await assert.rejects(client.invoke('GetQueueHealth', 'other', {}, {}, id), /QUEUE_NOT_BOUND/); assert.equal(calls.length, 2);
});
test('environment mismatch prevents any mutation', async () => {
  let calls = 0; const client = new DataverseClient(binding, () => 'synthetic', async () => { calls++; return response({ OrganizationId: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' }); });
  await assert.rejects(client.invoke('Enqueue','mail',{}, {},id), /ENVIRONMENT_MISMATCH/);assert.equal(calls,1);
});
test('missing token and production binding fail closed', async () => {
  const client = new DataverseClient(binding, () => undefined, () => { throw new Error('must not call'); });
  await assert.rejects(client.verify(), /ACCESS_TOKEN_REQUIRED/);
  assert.throws(() => new DataverseClient({ ...binding, environmentClass: 'production' }, () => 'synthetic'), /DEVELOPMENT_BINDING_REQUIRED/);
});
test('queue allowlist rejects invalid and duplicate scopes', () => {
  assert.throws(() => new DataverseClient({ ...binding, queueKeys: ['mail', 'mail'] }, () => 'synthetic'), /QUEUE_ALLOWLIST_REQUIRED/);
  assert.throws(() => new DataverseClient({ ...binding, queueKeys: ['Mail'] }, () => 'synthetic'), /QUEUE_ALLOWLIST_REQUIRED/);
});
test('unbound API and service errors cannot look successful', async () => {
  const client = new DataverseClient(binding, () => 'synthetic', async url => response(url.endsWith('WhoAmI') ? { OrganizationId: id } : {}));
  await assert.rejects(client.invoke('StartTestRun','mail',{}, {},id), /API_BINDING_INVALID/);
  const denied = new DataverseClient(binding, () => 'synthetic', async () => ({ ok: false, status: 403, text: async () => 'sensitive server detail' }));
  await assert.rejects(denied.verify(), /DATAVERSE_ACCESS_DENIED/);
});
