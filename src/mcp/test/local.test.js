import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { command } from '../local.js';

test('local runtime rejects oversized responses and terminates the child', async () => {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.stderr.resume = () => {};
  child.stdin = { end() {} };
  let killed = false;
  child.kill = () => { killed = true; };

  const pending = command('GetQueueHealth', 'mail', {}, {}, { spawnProcess: () => child });
  await new Promise(resolve => setImmediate(resolve));
  child.stdout.emit('data', Buffer.alloc(1000001, 'x'));

  await assert.rejects(pending, /LOCAL_RUNTIME_RESPONSE_TOO_LARGE/);
  assert.equal(killed, true);
});
