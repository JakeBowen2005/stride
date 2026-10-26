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
test('busy inline sync waits for a newer successful check instead of accepting the old timestamp', async () => {
  const states = [
    {connected:true,last_sync_at:'2026-10-23T10:00:00'},
    {connected:true,last_sync_at:'2026-10-23T10:00:00'},
    {connected:true,last_sync_at:'2026-10-26T13:00:00'},
  ];
  const result = await waitForSync(async () => states.shift(), new AbortController().signal, async () => {});
  assert.equal(result.status, 'ok');
  assert.equal(states.length, 0);
});
test('a failed background retry releases the button with the actual error instead of waiting four minutes', async () => {
  let pauses = 0;
  const result = await waitForSync(async () => ({last_error:'Garmin rejected the API key',
    full_sync_job:{state:'running',status:'retry'}}), new AbortController().signal, async () => { pauses++; });
  assert.equal(result.status, 'backoff');
  assert.equal(syncMessage(result), 'Garmin rejected the API key');
  assert.equal(pauses, 0);
});

test('a disconnected athlete gets a working reconnect link instead of a disabled sync button', async () => {
  const { createRequire } = await import('node:module');
  const require = createRequire(import.meta.url);
  const React = require('react');
  const { renderToStaticMarkup } = require('react-dom/server');
  const source = readFileSync(new URL('../components/garmin-sync.tsx', import.meta.url), 'utf8');
  const component = {};
  let firstState = true;
  const hooks = {
    useState: value => { const current = firstState ? {api_key_present:false,last_sync_at:'2026-10-23T10:00:00',connection_issue:'Garmin was disconnected.'} : value; firstState = false; return [current, () => {}]; },
    useEffect: () => {}, useCallback: fn => fn, useRef: value => ({current:value}),
  };
  runInNewContext(ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,
    {exports:component, require:id => ({
      react:hooks, 'next/link':{default:({children,...props}) => React.createElement('a',props,children)},
      '@/lib/api':{}, '@/lib/garmin-sync':exports,
      '@/components/ui/button':{Button:({children,disabled}) => React.createElement('button',{disabled},children)},
    }[id] || require(id))});
  const html = renderToStaticMarkup(React.createElement(component.GarminSync));
  assert.match(html, /href="\/settings#garmin"/);
  assert.match(html, /Reconnect Garmin/);
  assert.match(html, /Garmin was disconnected/);
  assert.doesNotMatch(html, /disabled/);
});
