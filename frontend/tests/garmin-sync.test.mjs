import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { test } from 'node:test';
import ts from 'typescript';
const source = readFileSync(new URL('../lib/garmin-sync.ts', import.meta.url), 'utf8');
const exports = {};
runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
  { exports, setTimeout, clearTimeout, Error });
const { waitForSync, syncMessage } = exports;
test('queued and retrying worker jobs only finish when persisted result is available', async () => {
  const states = [
    { full_sync_job: { state: 'running', status: 'queued' } },
    { full_sync_job: { state: 'running', status: 'retry' } },
    { full_sync_job: { state: 'done', result: { status: 'ok', new: 3 } } },
  ];
  const result = await waitForSync(async () => states.shift(), new AbortController().signal, async () => {});
  assert.equal(states.length, 0);
  assert.equal(syncMessage(result), '3 new runs from Garmin');
});
test('worker failure exposes the connection error and never reports success', async () => {
  await assert.rejects(waitForSync(async () => ({ last_error: 'Garmin rejected the API key',
    full_sync_job: { state: 'error', error: 'GarminAuthError' } }), new AbortController().signal), /rejected the API key/);
});
test('rate limiting, partial wellness and pending jobs never say up to date', async () => {
  assert.equal(syncMessage({status:'backoff',message:'Retry after 14:00'}), 'Retry after 14:00');
  assert.match(syncMessage({status:'ok',wellness:{status:'partial'}}), /health data could not refresh/);
  const result = await waitForSync(async () => ({full_sync_job:{state:'running'}}), new AbortController().signal, async () => {});
  assert.equal(result.status, 'pending');
  assert.match(syncMessage(result), /still pending/);
});
test('unmounted sync polling stops before another request', async () => {
  const controller = new AbortController(); controller.abort();
  await assert.rejects(waitForSync(async () => { throw new Error('must not fetch'); }, controller.signal), /cancelled/);
});
