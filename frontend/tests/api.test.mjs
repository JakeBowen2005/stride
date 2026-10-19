import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

// Execute the actual shared client without a browser, server or network.
const source = readFileSync(new URL('../lib/api.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
function client(fetch) {
  const exports = {};
  runInNewContext(compiled, { exports, fetch, process: { env: {} } });
  return exports;
}

test('API errors cannot masquerade as empty training history', async () => {
  for (const status of [401, 404, 500]) {
    const api = client(async () => ({ status, ok: false, json: async () => ({ detail: 'backend failed' }) }));
    await assert.rejects(api.getJson('/runs'), (error) => error.status === status);
  }
});

test('missing plan is optional only when explicitly requested', async () => {
  const api = client(async () => ({ status: 404, ok: false }));
  assert.equal(await api.getJson('/plan', { allowNotFound: true }), null);
  await assert.rejects(api.getJson('/plan'));
});

test('network and malformed responses remain visible failures', async () => {
  const offline = client(async () => { throw Error('offline'); });
  await assert.rejects(offline.getJson('/runs'), /reach Stride/);
  const malformed = client(async () => ({ status: 200, ok: true, json: async () => { throw Error('invalid JSON'); } }));
  await assert.rejects(malformed.getJson('/runs'), /invalid JSON/);
});

test('a successful empty history remains a valid empty result', async () => {
  const api = client(async () => ({ status: 200, ok: true, json: async () => [] }));
  assert.equal((await api.getJson('/runs')).length, 0);
});
