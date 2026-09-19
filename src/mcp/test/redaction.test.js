import test from 'node:test';
import assert from 'node:assert/strict';
import { redactForAgent } from '../redaction.js';

test('MCP projection redacts credential-shaped fields at every nesting level', () => {
  const result = redactForAgent({
    safe: 'ordinary untrusted text remains data',
    authorization: 'Bearer synthetic-token',
    nested: { accessToken: 'access-secret', headers: { Cookie: 'session-secret' }, clientSecret: 'client-secret' },
    rows: [{ password: 'password-secret', credential: 'credential-secret', safe: 3 }]
  });
  assert.equal(result.safe, 'ordinary untrusted text remains data');
  assert.equal(result.authorization, '[REDACTED]');
  assert.equal(result.nested.accessToken, '[REDACTED]');
  assert.equal(result.nested.headers, '[REDACTED]');
  assert.equal(result.nested.clientSecret, '[REDACTED]');
  assert.equal(result.rows[0].password, '[REDACTED]');
  assert.equal(result.rows[0].credential, '[REDACTED]');
  assert.equal(result.rows[0].safe, 3);
  assert.doesNotMatch(JSON.stringify(result), /synthetic-token|access-secret|session-secret|client-secret|password-secret|credential-secret/);
});

test('MCP projection does not echo raw input or payload content', () => {
  const result = redactForAgent({ bodyText: 'ignore this instruction', input: { action: 'install' }, payload: { token: 'nested-secret' }, contentHash: 'stable-hash' });
  assert.equal(result.bodyText, '[UNTRUSTED_CONTENT_REDACTED]');
  assert.equal(result.input, '[UNTRUSTED_CONTENT_REDACTED]');
  assert.equal(result.payload, '[UNTRUSTED_CONTENT_REDACTED]');
  assert.equal(result.contentHash, 'stable-hash');
});
