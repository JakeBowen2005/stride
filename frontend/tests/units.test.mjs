import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

function moduleFrom(file, dependencies = {}) {
  const code = ts.transpileModule(readFileSync(new URL(file, import.meta.url), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  runInNewContext(code, { exports, require: (name) => dependencies[name] });
  return exports;
}
const format = moduleFrom('../lib/format.ts');
const units = moduleFrom('../lib/units.ts', { '@/lib/format': format });
test('changing preferred units converts presentation, retaining canonical miles', () => {
  assert.equal(units.distanceInUnits(10,'km'),'16.1');
  assert.equal(units.distanceInUnits(10,'miles'),'10');
  assert.equal(units.unitLabel('km'),'km');
  assert.equal(units.unitLabel('miles'),'mi');
});
test('pace ranges convert both endpoints with correct minute carry', () => {
  assert.equal(units.paceInUnits('9:00-9:55','km'),'5:36-6:10');
  assert.equal(units.paceInUnits('9:00-9:55','miles'),'9:00-9:55');
});
