import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

const code = ts.transpileModule(readFileSync(new URL('../lib/plan-spotlight.ts', import.meta.url), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const exports = {};
runInNewContext(code, { exports, Date });
const { pickSpotlight } = exports;

const week = [
  { date: '2026-10-28', type: 'easy', actual: { distance_miles: 6 } },
  { date: '2026-10-29', type: 'threshold' },
  { date: '2026-10-30', type: 'easy' },
  { date: '2026-10-31', type: 'rest' },
  { date: '2026-11-01', type: 'long_run' },
];

test("today's run leads while it is still to do", () => {
  const s = pickSpotlight(week, '2026-10-29');
  assert.equal(s.focus.date, '2026-10-29');
  assert.equal(s.when, 'Today');
});

test("once today is run, tomorrow's run leads", () => {
  const done = week.map((d) => d.date === '2026-10-29' ? { ...d, actual: { distance_miles: 7 } } : d);
  const s = pickSpotlight(done, '2026-10-29');
  assert.equal(s.focus.date, '2026-10-30');
  assert.equal(s.when, 'Tomorrow');
  assert.ok(s.todayDay.actual);
});

test('rest days, skipped and moved sessions are passed over for the next run', () => {
  const days = [
    { date: '2026-10-30', type: 'easy', skipped: true },
    { date: '2026-10-31', type: 'rest' },
    { date: '2026-11-01', type: 'easy', moved_to: '2026-11-02' },
    { date: '2026-11-02', type: 'long_run' },
  ];
  const s = pickSpotlight(days, '2026-10-30');
  assert.equal(s.focus.date, '2026-11-02');
  assert.equal(s.when, 'Monday');
});

test('nothing left in the block shows no spotlight', () => {
  assert.equal(pickSpotlight(week, '2026-11-01').focus.date, '2026-11-01');
  assert.equal(pickSpotlight(week, '2026-11-02').focus, null);
});
