import { expect, test } from '@playwright/test';
import { snapshotAgeLabel } from '../lib/operations-data';
import { ready, section } from './helpers';

test('snapshot age handles boundaries, timezone offsets and missing clocks', () => {
  const asOf = '2026-09-01T14:00:00Z';
  const at = Date.parse(asOf);
  expect(snapshotAgeLabel(asOf, at)).toBe('0m');
  expect(snapshotAgeLabel(asOf, at + 59 * 60_000)).toBe('59m');
  expect(snapshotAgeLabel(asOf, at + 60 * 60_000)).toBe('1h');
  expect(snapshotAgeLabel(asOf, at + 47 * 3_600_000)).toBe('47h');
  expect(snapshotAgeLabel(asOf, at + 49 * 3_600_000)).toBe('2d 1h');
  expect(snapshotAgeLabel('2026-09-01T16:00:00+02:00', at)).toBe('0m');
  expect(snapshotAgeLabel(asOf, at - 1)).toBe('Snapshot is ahead of this device clock');
  expect(snapshotAgeLabel('invalid', at)).toBe('Unavailable');
  expect(snapshotAgeLabel(asOf, Number.NaN)).toBe('Unavailable');
});

test('elapsed snapshot age advances without changing source dates or declaring session freshness', async ({ page }, testInfo) => {
  await page.clock.install({ time: new Date('2026-10-01T12:00:00Z') });
  await ready(page);
  const manifest = await page.request.get('/data/manifest.json').then((response) => response.json());
  const age = page.getByTitle('Elapsed wall-clock time since the data snapshot; not a market-session freshness check.');
  await expect(age).toHaveText(`Snapshot age: ${snapshotAgeLabel(manifest.asOf, Date.parse('2026-10-01T12:00:00Z'))}`);
  const dateText = await page.getByText(/^Score snapshot:/).textContent();
  await page.clock.fastForward('01:00:00');
  await expect(age).toHaveText(`Snapshot age: ${snapshotAgeLabel(manifest.asOf, Date.parse('2026-10-01T13:00:00Z'))}`);
  await expect(page.getByText(/^Score snapshot:/)).toHaveText(dateText!);
  await section(page, 'System Health');
  await expect(age).toHaveCount(2);
  await expect(page.getByText('Fresh through latest session', { exact: true })).toHaveCount(0);
  await expect(page.getByText(/at snapshot calculation/, { exact: false })).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('snapshot-age.png'), fullPage: true });
});
