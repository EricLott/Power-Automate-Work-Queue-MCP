import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { validateFlow } from '../flow-validation.js';

const root = path.resolve(import.meta.dirname, '../../..');
const processOne = async () => JSON.parse(await readFile(path.join(root, 'templates/flows/ProcessOne.json'), 'utf8'));

test('reference flows pass bounded static safety inspection', async () => {
  const files = await readdir(path.join(root, 'templates/flows'));
  for (const file of files.filter(name => name.endsWith('.json'))) {
    const flow = JSON.parse(await readFile(path.join(root, 'templates/flows', file), 'utf8'));
    const result = validateFlow(flow);
    assert.equal(result.status, 'passed', `${file}: ${JSON.stringify(result.issues)}`);
    assert.ok(result.limitations.length > 0);
  }
});

test('static validator detects raw native queue writes', async () => {
  const flow = await processOne();
  flow.properties.definition.actions.Unsafe = { type: 'OpenApiConnection', inputs: { host: { operationId: 'UpdateRecord' }, parameters: { entityName: 'workqueueitems' } } };
  assert.ok(validateFlow(flow).issues.some(issue => issue.code === 'RAW_NATIVE_QUEUE_WRITE'));
});

test('static validator detects unconditional completion', async () => {
  const flow = await processOne();
  const complete = flow.properties.definition.actions.HasWork.actions.Complete;
  complete.runAfter = {};
  assert.ok(validateFlow(flow).issues.some(issue => issue.code === 'UNCONDITIONAL_COMPLETE'));
});

test('static validator detects visible production test destinations', async () => {
  const flow = await processOne();
  flow.properties.definition.actions.UnsafeTest = { type: 'OpenApiConnection', inputs: { host: { operationId: 'PerformUnboundAction' }, parameters: { actionName: 'qmcp_WQ_StartTestRun', 'item/QueueKey': 'production' } } };
  assert.ok(validateFlow(flow).issues.some(issue => issue.code === 'PRODUCTION_TEST_DESTINATION'));
});
