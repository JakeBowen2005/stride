import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { test } from 'node:test';
import ts from 'typescript';

const compiled = ts.transpileModule(readFileSync(new URL('../lib/theme.ts', import.meta.url), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const exports = {};
runInNewContext(compiled, { exports });

for (const [saved, systemDark, expectedDark] of [
  ['light', true, false], ['dark', false, true], ['system', true, true],
  ['system', false, false], [null, false, true], ['invalid', false, true],
]) {
  test(`boot applies ${saved ?? 'default'} before paint (OS dark: ${systemDark})`, () => {
    let dark;
    runInNewContext(exports.THEME_BOOT_SCRIPT, {
      localStorage: { getItem: () => saved }, matchMedia: () => ({ matches: systemDark }),
      document: { documentElement: { classList: { toggle: (key, value) => { assert.equal(key, 'dark'); dark = value; } } } },
    });
    assert.equal(dark, expectedDark);
  });
}

test('storage errors preserve the Dusk default', () => {
  let dark;
  runInNewContext(exports.THEME_BOOT_SCRIPT, {
    localStorage: { getItem: () => { throw Error('disabled'); } },
    document: { documentElement: { classList: { toggle: (_, value) => { dark = value; } } } },
  });
  assert.equal(dark, true);
});
