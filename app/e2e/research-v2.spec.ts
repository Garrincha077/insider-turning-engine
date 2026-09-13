import { createHash } from 'node:crypto';
import { expect, test, type Page } from '@playwright/test';
import fixture from './fixtures/research-v2.json' with { type: 'json' };
import { ready, section } from './helpers';
import originalSettings from './public/data/settings-status.json' with { type: 'json' };
import type { SettingsStatus } from '../lib/operations-data';

type Fixture = Omit<typeof fixture, 'economicTransactions'> & { economicTransactions: Array<Omit<typeof fixture.economicTransactions[number], 'shares'> & { shares: number | null }> };

async function v2(page: Page, mutate?: (value: Fixture) => void, digest?: SettingsStatus['digest']) {
  const data: Fixture = structuredClone(fixture); mutate?.(data);
  const bytes = JSON.stringify(data);
  const settingsBytes = JSON.stringify({ ...originalSettings, digest });
  if (digest) await page.route('**/data/settings-status.json', (route) => route.fulfill({ body: settingsBytes, contentType: 'application/json' }));
  await page.route('**/data/research-v2.json', (route) => route.fulfill({ body: bytes, contentType: 'application/json' }));
  await page.route('**/data/manifest.json', async (route) => {
    const response = await route.fetch();
    const manifest = await response.json();
    manifest.runId = fixture.runId; manifest.asOf = fixture.asOf;
    manifest.files.push({ path: 'research-v2.json', size: Buffer.byteLength(bytes), sha256: createHash('sha256').update(bytes).digest('hex') });
    if (digest) manifest.files = manifest.files.map((file: { path: string }) => file.path !== 'settings-status.json' ? file : { path: file.path, size: Buffer.byteLength(settingsBytes), sha256: createHash('sha256').update(settingsBytes).digest('hex') });
    await route.fulfill({ json: manifest });
  });
}

test('v2 facts drive scoreless Radar, real clusters, basis and source-linked tape', async ({ page }) => {
  const chartErrors: string[] = [];
  page.on('console', (message) => { if (/component.*not imported/i.test(message.text())) chartErrors.push(message.text()); });
  await v2(page);
  await ready(page);
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await expect(page.locator('tbody tr')).toContainText('Unknown / not established');
  await section(page, 'Live SEC Tape');
  await expect(page.locator('tbody tr')).toHaveCount(2);
  expect(await page.locator('td[data-value]').evaluateAll((cells) => cells.reduce((sum, cell) => sum + Number(cell.getAttribute('data-value')), 0))).toBe(2000);
  await page.getByText('Record details', { exact: true }).first().click();
  await expect(page.getByText('10b5-1 status').first()).toBeVisible();
  await expect(page.getByText('Shares × reported price').first()).toBeVisible();
  await section(page, 'Clusters');
  await expect(page.getByText('3 reporting owners', { exact: false })).toBeVisible();
  await page.getByText('2 underlying purchases').click();
  await expect(page.getByRole('link', { name: /SEC row/ })).toHaveCount(2);
  await section(page, 'Cost Basis');
  await expect(page.locator('tbody tr')).toContainText('$10.00');
  await expect(page.locator('tbody tr')).toContainText('$2,000.00');
  await expect(page.locator('tbody tr')).toContainText('PARTIAL');
  await page.getByLabel('Basis window').selectOption('30');
  await section(page, 'Market Pulse');
  await expect(page.getByText('$2,000.00', { exact: true })).toBeVisible();
  await expect(page.getByText('Purchases and sales by transaction date')).toBeVisible();
  await section(page, 'Data Coverage');
  await expect(page.getByText('Measured source-to-score coverage')).toBeVisible();
  await section(page, 'Company Lab');
  await expect(page.getByLabel('Select company')).toHaveValue('ACME');
  await expect(page.locator('canvas').first()).toBeVisible();
  await section(page, 'Alert Center');
  await expect(page.getByText('Informational daily digest · draft preview', { exact: true })).toBeVisible();
  await expect(page.getByText(/This preview does not send a message/)).toBeVisible();
  expect(chartErrors).toEqual([]);
});

test('v2 semantic corruption cannot fall back to the legacy snapshot', async ({ page }) => {
  await v2(page, (value) => { value.economicTransactions[0].owners[0].ownerCik = '0000000000'; });
  await page.goto('/');
  await expect(page.getByText('Research v2 broken event reference')).toBeVisible();
  await expect(page.getByLabel('Ticker or company')).toHaveCount(0);
});

test('Market Pulse reserves a top legend band away from transaction dates', async ({ page }) => {
  await v2(page);
  await ready(page);
  await section(page, 'Market Pulse');
  await expect(page.locator('canvas')).toBeVisible();
  const layout = await page.evaluate(async () => {
    const modulePath = '/node_modules/.vite/deps/echarts_core.js';
    const engine = await import(modulePath) as typeof import('echarts/core');
    const chart = engine.getInstanceByDom(document.querySelector<HTMLElement>('[_echarts_instance_]')!);
    const option = chart!.getOption() as { legend: Array<{ top: number; bottom: number | null }>; grid: Array<{ top: number; bottom: number }> };
    return { legend: option.legend[0], grid: option.grid[0] };
  });
  expect(layout.legend.top).toBe(8);
  expect(layout.legend.bottom).toBeNull(); // ECharts normalizes the unused 'auto' edge.
  expect(layout.grid.top).toBeGreaterThanOrEqual(65);
  expect(layout.grid.bottom).toBeGreaterThanOrEqual(45);
});

test('Company Lab reserves a top legend band away from date labels', async ({ page }) => {
  await v2(page);
  await ready(page);
  await section(page, 'Company Lab');
  await expect(page.locator('canvas').first()).toBeVisible();
  const layout = await page.evaluate(async () => {
    const modulePath = '/node_modules/.vite/deps/echarts_core.js';
    const engine = await import(modulePath) as typeof import('echarts/core');
    const chart = [...document.querySelectorAll<HTMLElement>('[_echarts_instance_]')]
      .map((element) => engine.getInstanceByDom(element))
      .find((instance) => (instance?.getOption() as { series?: Array<{ name?: string }> } | undefined)?.series?.some((item) => item.name === 'Adjusted price'));
    const option = chart!.getOption() as { legend: Array<{ top: number; bottom: number | null }>; grid: Array<{ top: number; bottom: number }>; xAxis: Array<{ axisLabel: { hideOverlap: boolean } }> };
    return { legend: option.legend[0], grid: option.grid[0], xAxis: option.xAxis[0] };
  });
  expect(layout.legend.top).toBe(8);
  expect(layout.legend.bottom).toBeNull();
  expect(layout.grid.top).toBeGreaterThanOrEqual(65);
  expect(layout.grid.bottom).toBeGreaterThanOrEqual(45);
  expect(layout.xAxis.axisLabel.hideOverlap).toBe(true);
});

test('v2.1 source amounts with unknown derivative quantity do not enter purchase tape', async ({ page }) => {
  await v2(page, (value) => {
    value.schemaVersion = '2.1.0';
    value.economicTransactions.push({ ...value.economicTransactions[0], eventId: 'event_amount_only',
      table: 'DERIVATIVE', shares: null, value: 35000, price: 0, qualified: false, aggregateEligible: false });
    value.coverage.economicEvents += 1;
    value.coverage.canonicalOwnerRows += 2;
  });
  await ready(page);
  await section(page, 'Live SEC Tape');
  await expect(page.locator('tbody tr')).toHaveCount(2);
  await section(page, 'Market Pulse');
  await expect(page.getByText('$2,000.00', { exact: true })).toBeVisible();
});

test('unknown non-derivative quantity is rejected, not converted into zero', async ({ page }) => {
  await v2(page, (value) => {
    value.schemaVersion = '2.1.0';
    value.economicTransactions[0].shares = null;
  });
  await page.goto('/');
  await expect(page.getByText('Research v2 invalid amount-only event')).toBeVisible();
});

test('v2 missing fields and mixed-run scores fail closed even with matching bytes', async ({ page }) => {
  await v2(page, (value) => { value.researchScores[0].runId = 'run_another_day'; });
  await page.goto('/');
  await expect(page.getByText('Research v2 mixed score lineage')).toBeVisible();
});

test('digest policy and exact suppression are visible independently of predictive alerts', async ({ page }) => {
  const day = [...fixture.coverage.expectedSecDays].sort((a: string, b: string) => a.localeCompare(b)).at(-1) ?? null;
  await v2(page, undefined, { enabled: false, secDay: day, status: 'BLOCKED',
    reasons: ['DIGEST_DISABLED_BY_POLICY', 'LATEST_SEC_DAY_INCOMPLETE'], eventIds: [], excludedIssuers: 0 });
  await ready(page);
  await section(page, 'Settings');
  await expect(page.getByText('Informational digest policy', { exact: true })).toBeVisible();
  await expect(page.getByText(/Telegram digest: OFF/)).toBeVisible();
  await section(page, 'Alert Center');
  await expect(page.getByText(/Server policy: OFF/)).toBeVisible();
  await expect(page.getByText(/Delivery: BLOCKED.*latest sec day incomplete/i)).toBeVisible();
});

test('digest event references from another snapshot fail closed', async ({ page }) => {
  await v2(page, undefined, { enabled: true, secDay: [...fixture.coverage.expectedSecDays].sort((a: string, b: string) => a.localeCompare(b)).at(-1) ?? null,
    status: 'READY', reasons: [], eventIds: ['not-in-this-run'], excludedIssuers: 0 });
  await page.goto('/');
  await expect(page.getByText('Digest status does not match the research publication')).toBeVisible();
});
