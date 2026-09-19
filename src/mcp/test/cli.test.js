import test from 'node:test';
import assert from 'node:assert/strict';
import { DataverseCliClient } from '../cli.js';

const binding = { environmentUrl: 'https://synthetic.crm.dynamics.com', organizationId: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', environmentClass: 'development', queueKeys: ['mail'] };

test('injected bridge preserves identity and mutation payload', async () => {
  const calls = [];
  const bridge = async payload => { calls.push(payload); if (payload.route === 'WhoAmI') return { OrganizationId: binding.organizationId, UserId: binding.organizationId }; return { ResultJson: JSON.stringify({ Outcome: 'Health' }) }; };
  const client = new DataverseCliClient(binding, bridge);
  const result = await client.invoke('GetQueueHealth', 'mail', {}, {}, 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb');
  assert.deepEqual(result, { Outcome: 'Health' });
  assert.equal(calls.length, 2);
  assert.equal(calls[0].route, 'WhoAmI');
  assert.equal(calls[1].route, 'qmcp_WQ_GetQueueHealth');
  assert.equal(calls[1].body.QueueKey, 'mail');
});

test('injected bridge client keeps operation and queue guards', async () => {
  const client = new DataverseCliClient(binding, async () => ({ OrganizationId: binding.organizationId }));
  await assert.rejects(client.invoke('DeleteAll', 'mail', {}, {}, 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'), /OPERATION_NOT_EXPOSED/);
  await assert.rejects(client.invoke('GetQueueHealth', 'other', {}, {}, 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'), /QUEUE_NOT_BOUND/);
});
test('injected bridge exposes reviewed retry with expected version', async () => {
  const calls = [];
  const bridge = async payload => { calls.push(payload); if (payload.route === 'WhoAmI') return { OrganizationId: binding.organizationId, UserId: binding.organizationId }; return { ResultJson: JSON.stringify({ Outcome: 'RetryScheduled' }) }; };
  const client = new DataverseCliClient(binding, bridge);
  const result = await client.invoke('RequestRetry', 'mail', { reason: 'reviewed', reconciliation: 'VerifiedSafe' }, { ItemId: 'cccccccc-cccc-cccc-cccc-cccccccccccc', ExpectedVersion: 7 }, 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb');
  assert.equal(result.Outcome, 'RetryScheduled');
  assert.equal(calls[1].route, 'qmcp_WQ_RequestRetry');
  assert.equal(calls[1].body.ExpectedVersion, '7');
});
