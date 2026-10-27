import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import { test } from 'node:test';
import ts from 'typescript';
const require = createRequire(import.meta.url);
function load(relative, mocks = {}, globals = {}) {
  const source = readFileSync(new URL(relative, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  runInNewContext(compiled, { exports, require: id => id in mocks ? mocks[id] : require(id), Buffer, Date, Map, Set, URLSearchParams, process: { env: {} }, ...globals });
  return exports;
}
const auth = load('../lib/auth.ts');
test('auth sessions reject expired, altered, old-password and permanent legacy cookies', () => {
  const now = 10000000;
  const token = auth.createAuthSession('test-password', now);
  assert.equal(auth.validAuthSession(token, 'test-password', now), true);
  assert.equal(auth.validAuthSession(token, 'test-password', now + auth.SESSION_SECONDS * 1000), false);
  assert.equal(auth.validAuthSession(token, 'changed-password', now), false);
  assert.equal(auth.validAuthSession(token.replace(/^\d+/, '9999999999999'), 'test-password', now), false);
  assert.equal(auth.validAuthSession('a'.repeat(64), 'test-password', now), false);
  assert.notEqual(token, auth.createAuthSession('test-password', now));
});
test('login throttles per-client attempts and distributed attempts, then recovers', () => {
  const limiter = load('../lib/login-limiter.ts');
  for (let i = 0; i < 5; i++) assert.equal(limiter.consumeLoginAttempt('one', 1000), 0);
  assert.equal(limiter.consumeLoginAttempt('one', 1000), 600);
  for (let i = 0; i < 55; i++) assert.equal(limiter.consumeLoginAttempt(`client-${i}`, 1000), 0);
  assert.equal(limiter.consumeLoginAttempt('another', 1000), 600);
  assert.equal(limiter.consumeLoginAttempt('one', 601001), 0);
});
test('stale advice is explicit even without suggestions or after a prior accepted change', () => {
  const { coachingState } = load('../lib/coaching-state.ts');
  for (const applied_candidate_id of [null, 'saved']) {
    assert.match(coachingState({ stale: true, status: 'ready', suggestions: [], applied_candidate_id }, null), /Outdated advice/);
  }
  assert.match(coachingState({ stale: false, status: 'ready', suggestions: ['choice'], applied_candidate_id: null }, null), /awaiting your approval/);
  assert.match(coachingState(null, 'queued'), /saved.*queued/);
});
test('Home uses backend primary identity and never chooses a later walk or shakeout', () => {
  const { primaryRunId } = load('../lib/activity-selection.ts');
  const activities = [
    { id: 3, date: '2026-10-20T18:00:00', type: 'walk', distance_miles: 1 },
    { id: 2, date: '2026-10-20T17:00:00', type: 'easy', distance_miles: 2 },
    { id: 1, date: '2026-10-20T08:00:00', type: 'workout', distance_miles: 7, session: { title: '3x8min' } },
  ];
  assert.equal(primaryRunId(activities, '2026-10-20'), 1);
  assert.equal(primaryRunId(activities.slice(0, 1), '2026-10-20'), undefined);
  assert.equal(primaryRunId(activities.slice(0, 1), '2026-10-20', 99), 99);
});
test('schedule change notices compare saved and current preferences without rest-day-order noise', () => {
  const { scheduleChanged } = load('../lib/plan-preferences.ts');
  const saved = { days_per_week: 5, rest_days: ['friday', 'sunday'], long_run_day: 'saturday', workout_format: 'time' };
  const current = { ...saved, rest_days: 'sunday,friday' };
  assert.equal(scheduleChanged(saved, current), false);
  assert.equal(scheduleChanged(saved, { ...current, days_per_week: 6 }), true);
  assert.equal(scheduleChanged(saved, { ...current, workout_format: 'distance' }), true);
  assert.equal(scheduleChanged(undefined, current), false);
});
test('readiness fails closed when backend is unhealthy or times out', async () => {
  for (const fetch of [async () => ({ ok: false }), async () => { throw Error('timeout'); }]) {
    const route = load('../app/healthz/route.ts', {}, { fetch, Response, AbortSignal });
    assert.equal((await route.GET()).status, 503);
  }
  const route = load('../app/healthz/route.ts', {}, { fetch: async () => ({ ok: true }), Response, AbortSignal });
  assert.equal((await route.GET()).status, 200);
});
test('sign-in route issues expiring secure sessions, rejects external redirects and throttles failures', async () => {
  class NextResponse extends Response {
    constructor(body, init) { super(body, init); this.savedCookies = []; this.cookies = { set: (...args) => this.savedCookies.push(args) }; }
  }
  const limiter = load('../lib/login-limiter.ts');
  const route = load('../app/auth/route.ts', {
    'next/server': { NextResponse }, '@/lib/auth': auth, '@/lib/login-limiter': limiter,
  }, { process: { env: { STRIDE_PASSWORD: 'test-password' } } });
  const request = (password, next, ip = 'first') => ({ headers: new Headers({ 'x-forwarded-for': ip, 'x-forwarded-proto': 'https' }), formData: async () => new Map([['password', password], ['next', next]]) });
  const success = await route.POST(request('test-password', '/\\evil.example'));
  assert.equal(success.status, 303);
  assert.equal(success.headers.get('location'), '/');
  assert.equal(success.savedCookies[0][2].secure, true);
  assert.equal(success.savedCookies[0][2].httpOnly, true);
  assert.equal(success.savedCookies[0][2].maxAge, auth.SESSION_SECONDS);
  assert.equal(auth.validAuthSession(success.savedCookies[0][1], 'test-password'), true);
  for (let i = 0; i < 5; i++) assert.equal((await route.POST(request('wrong', '/plan', 'blocked'))).status, 303);
  const blocked = await route.POST(request('test-password', '/plan', 'blocked'));
  assert.equal(blocked.status, 429);
  assert.ok(Number(blocked.headers.get('retry-after')) > 0);
  assert.equal(blocked.savedCookies.length, 0);
});
test('sign-out expires only the Stride session cookie and redirects to login', async () => {
  class NextResponse extends Response {
    constructor(body, init) { super(body, init); this.savedCookies = []; this.cookies = { set: (...args) => this.savedCookies.push(args) }; }
  }
  const route = load('../app/auth/logout/route.ts', { 'next/server': { NextResponse }, '@/lib/auth': auth });
  const response = await route.POST();
  assert.equal(response.headers.get('location'), '/login');
  assert.equal(response.savedCookies[0][0], auth.AUTH_COOKIE);
  assert.equal(response.savedCookies[0][1], '');
  assert.equal(response.savedCookies[0][2].maxAge, 0);
});
test('schedule descriptions read naturally for the plan banner', () => {
  const { describeSchedule } = load('../lib/plan-preferences.ts');
  assert.equal(describeSchedule(7, ['']), '7 run days, no rest day');
  assert.equal(describeSchedule(6, ['sunday']), '6 run days, rest Sunday');
  assert.equal(describeSchedule(1, ['monday', ' friday']), '1 run day, rest Monday & Friday');
});
