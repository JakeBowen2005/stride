import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

const code = ts.transpileModule(readFileSync(new URL('../lib/plan-state.ts', import.meta.url), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
function moduleWith(getJson) {
  const exports = {};
  runInNewContext(code, { exports, require: () => ({ USER_ID: 1, getJson }) });
  return exports;
}

test('discarding a preview restores the approved plan, not an empty page', async () => {
  const active = { id: 5, weeks: [{ days: [] }] };
  let preview = { id: 6, preview: true };
  const client = moduleWith(async (path) => path.endsWith('/draft') ? preview : active);
  assert.equal((await client.loadPlanState()).visible, preview);
  preview = null;
  const state = await client.loadPlanState();
  assert.equal(state.visible, active);
  assert.equal(state.active, active);
});

test('first preview remains reviewable when no approved plan exists', async () => {
  const draft = { id: 6, preview: true };
  const client = moduleWith(async (path) => path.endsWith('/draft') ? draft : null);
  assert.equal((await client.loadPlanState()).visible, draft);
});

test('failed current plan fetch is an error, not missing content', async () => {
  const client = moduleWith(async (path) => {
    if (path.endsWith('/current')) throw Error('server unavailable');
    return null;
  });
  await assert.rejects(client.loadPlanState(), /server unavailable/);
});

test('next-block control is unavailable during the approved block', () => {
  const { nextBlockAvailable } = moduleWith(() => {});
  assert.equal(nextBlockAvailable('2026-11-01', '2026-10-19'), false);
  assert.equal(nextBlockAvailable('2026-11-01', '2026-11-01'), false);
  assert.equal(nextBlockAvailable('2026-11-01', '2026-11-02'), true);
});
