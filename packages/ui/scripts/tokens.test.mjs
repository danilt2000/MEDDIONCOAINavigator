import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { SEED, tokensCss } from './tokens.mjs';

test('every M3 role used by @material/web has a light and a dark value', () => {
  const css = tokensCss(SEED);
  for (const role of ['primary', 'on-primary', 'primary-container', 'surface', 'on-surface', 'surface-container-highest', 'outline', 'error']) {
    assert.match(css, new RegExp(`--md-sys-color-${role}: light-dark\\(#[0-9a-f]{6}, #[0-9a-f]{6}\\);`), role);
  }
});

test('committed tokens.css matches SEED', () => {
  assert.equal(readFileSync(new URL('../src/tokens.css', import.meta.url), 'utf8'), tokensCss(SEED));
});
