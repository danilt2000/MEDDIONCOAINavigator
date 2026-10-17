import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { fmtDayTime, fmtTimeOrDayTime, isIsoDay } from '../src/dates.ts';

test('a team note from a later day shows its date, a same-day note only the time', () => {
  const created = '2026-09-03T16:50:00+02:00';
  assert.equal(fmtTimeOrDayTime('2026-09-03T17:05:00+02:00', created), '17:05');
  assert.equal(fmtTimeOrDayTime('2026-09-04T15:30:00+02:00', created), fmtDayTime('2026-09-04T15:30:00+02:00'));
  assert.match(fmtTimeOrDayTime('2026-09-04T15:30:00+02:00', created), /4\. 9\..*15:30/);
  assert.match(fmtTimeOrDayTime('2026-09-04T15:30:00+02:00', ''), /4\. 9\./);
});

test('the day route accepts only real ISO days', () => {
  assert.ok(isIsoDay('2026-09-09'));
  for (const day of ['abc', '2026-9-9', '2026-02-31', '2026-13-01', '']) assert.equal(isIsoDay(day), false, day);
});

test('the desktop-only notice and the layout share one minimum width', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const css = readFileSync(new URL('../src/app.css', import.meta.url), 'utf8');
  const breakpoint = Number(html.match(/@media \(max-width: (\d+)px\)/)![1]);
  const promised = Number(html.match(/alespoň (\d+)/)![1]);
  assert.equal(breakpoint + 1, promised);
  assert.doesNotMatch(css, /body \{[^}]*min-width/);
});
