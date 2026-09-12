import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const operations = require('../../operations/retry.js');
const id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
test('operator request carries the inspected version and safe reconciliation', () => {
  const request = operations.request('RequestRetry','mail',id,{reason:'Existing source result reconciled',reconciliation:'VerifiedSafe'},42,id);
  assert.equal(request.ExpectedVersion,'42');assert.equal(request.getMetadata().operationName,'qmcp_WQ_RequestRetry');
});
test('operator request rejects missing reconciliation and arbitrary operations', () => {
  assert.throws(() => operations.request('RequestRetry','mail',id,{reason:'retry'},42,id), /RECONCILIATION_REQUIRED/);
  assert.throws(() => operations.request('SetStatus','mail',id,{},42,id), /OPERATION_INVALID/);
});
test('operator request validates GUIDs, versions, and bounded input', () => {
  assert.equal(operations.request('GetItemStatus', 'mail', id, {}, '', id).ExpectedVersion, '');
  assert.throws(() => operations.request('RequestRetry','mail','not-a-guid', { reason: 'retry', reconciliation: 'VerifiedSafe' }, 42, id), /IDENTITY_INVALID/);
  assert.throws(() => operations.request('RequestRetry','mail',id, { reason: 'retry', reconciliation: 'VerifiedSafe' }, 42, 'not-a-guid'), /IDENTITY_INVALID/);
  assert.throws(() => operations.request('RequestRetry','mail',id, { reason: 'retry', reconciliation: 'VerifiedSafe' }, -1, id), /VERSION_INVALID/);
  assert.throws(() => operations.request('GetItemStatus','mail',id, { detail: 'x'.repeat(9000) }, 42, id), /INPUT_TOO_LARGE/);
  assert.throws(() => operations.request('RequestRetry','mail',id, undefined, 42, id), /INPUT_INVALID/);
});
