import { createHash } from 'node:crypto';
import { gzipSync } from 'node:zlib';
import { expect, test, type Page } from '@playwright/test';
import fixture from './fixtures/research-v2.json' with { type: 'json' };
import { ready, section } from './helpers';
import originalSettings from './public/data/settings-status.json' with { type: 'json' };
import type { SettingsStatus } from '../lib/operations-data';
import type { ResearchSnapshot } from '../lib/research-v2';

type Fixture = Omit<typeof fixture, 'economicTransactions'> & { economicTransactions: Array<Omit<typeof fixture.economicTransactions[number], 'shares'> & { shares: number | null }> };

async function v2(page: Page, mutate?: (value: Fixture) => void, digest?: SettingsStatus['digest'], compressed = false) {
  const data: Fixture = structuredClone(fixture); mutate?.(data);
  const bytes = JSON.stringify(data);
  const gzipBytes = gzipSync(bytes);
  const settingsBytes = JSON.stringify({ ...originalSettings, digest });
  if (digest) await page.route('**/data/settings-status.json', (route) => route.fulfill({ body: settingsBytes, contentType: 'application/json' }));
  if (!compressed) await page.route('**/data/research-v2.json', (route) => route.fulfill({ body: bytes, contentType: 'application/json' }));
  if (compressed) await page.route('**/data/research-v2.json.gz', (route) => route.fulfill({ body: gzipBytes, contentType: 'application/gzip' }));
  await page.route('**/data/manifest.json', async (route) => {
    const response = await route.fetch();
    const manifest = await response.json();
    manifest.runId = fixture.runId; manifest.asOf = fixture.asOf;
    manifest.files.push({ path: 'research-v2.json', size: Buffer.byteLength(bytes), sha256: createHash('sha256').update(bytes).digest('hex') });
    if (compressed) manifest.files.push({ path: 'research-v2.json.gz', size: gzipBytes.byteLength, sha256: createHash('sha256').update(gzipBytes).digest('hex') });
    if (digest) manifest.files = manifest.files.map((file: { path: string }) => file.path !== 'settings-status.json' ? file : { path: file.path, size: Buffer.byteLength(settingsBytes), sha256: createHash('sha256').update(settingsBytes).digest('hex') });
    await route.fulfill({ json: manifest });
  });
}

test('verified compressed research loads without requesting the large JSON source', async ({ page }) => {
  let jsonRequests = 0;
  await page.route('**/data/research-v2.json', (route) => {
    jsonRequests += 1;
    return route.continue();
  });
  await v2(page, undefined, undefined, true);
  await ready(page);
  await expect(page.locator('tbody tr')).toHaveCount(1);
  expect(jsonRequests).toBe(0);
});

test('compressed research must also match the canonical JSON manifest entry', async ({ page }) => {
  await v2(page, undefined, undefined, true);
  await page.route('**/data/manifest.json', async (route) => {
    const response = await route.fetch();
    const manifest = await response.json();
    manifest.runId = fixture.runId; manifest.asOf = fixture.asOf;
    const bytes = JSON.stringify(fixture);
    const gzipBytes = gzipSync(bytes);
    manifest.files.push({ path: 'research-v2.json', size: Buffer.byteLength(bytes), sha256: '0'.repeat(64) });
    manifest.files.push({ path: 'research-v2.json.gz', size: gzipBytes.byteLength, sha256: createHash('sha256').update(gzipBytes).digest('hex') });
    await route.fulfill({ json: manifest });
  });
  await page.goto('/');
  await expect(page.getByText(/Detailed research snapshot unavailable|integrity mismatch/)).toBeVisible();
});

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
  await expect(page.getByText('Observed buy/sell ratio history · monthly')).toBeVisible();
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

test('Insider Ratio counts economic events once and exposes live and monthly views', async ({ page }) => {
  await v2(page, (value) => {
    const research = value as unknown as ResearchSnapshot;
    research.coverage.expectedSecDays = ['2026-08-28', '2026-08-31'];
    research.coverage.days = research.coverage.expectedSecDays.map((day) => ({ day,
      discoveredFilings: 1, storedFilings: 1, parseRows: 1, quarantinedRows: 0,
      failures: 0, complete: true }));
    research.economicTransactions.forEach((row) => { row.secDay = '2026-08-28'; });
    research.economicTransactions.push({ ...research.economicTransactions[0],
      eventId: 'evt_ratio_sale', accession: '0001234567-26-000003', code: 'S', side: 'SELL',
      value: 500, secDay: '2026-08-31', owners: [research.economicTransactions[0].owners[0]] });
    research.coverage.economicEvents += 1;
    research.coverage.canonicalOwnerRows += 1;
  });
  await ready(page);
  await section(page, 'Insider Ratio');
  await expect(page.getByText('Latest complete SEC day', { exact: true })).toBeVisible();
  await expect(page.getByTestId('insider-ratio-current')).toHaveText('2×');
  await expect(page.getByRole('button', { name: 'Daily rolling 30D' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Calendar months' }).click();
  await expect(page.getByRole('button', { name: 'Calendar months' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText(/Each economic event is counted once/)).toBeVisible();
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
  await expect(page.locator('canvas').first()).toBeVisible();
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

test('Market Pulse separates 30D and 90D event ratios from value ratios and shows signed sector net', async ({ page }) => {
  await v2(page, (value) => {
    value.economicTransactions.push({ ...value.economicTransactions[0],
      eventId: 'evt_sale_for_pulse', accession: '0001234567-26-000003', code: 'S', side: 'SELL',
      shares: 50, price: 10, value: 500, owners: [value.economicTransactions[0].owners[0]] });
    value.coverage.economicEvents += 1;
    value.coverage.canonicalOwnerRows += 1;
  });
  await ready(page);
  await section(page, 'Market Pulse');
  await expect(page.getByTestId('pulse-value-ratio')).toHaveText('4×');
  await expect(page.getByTestId('pulse-inverse-value-ratio')).toHaveText('0.25×');
  await expect(page.getByTestId('pulse-count-ratio-30')).toHaveText('2×');
  await expect(page.getByTestId('pulse-count-ratio-90')).toHaveText('2×');
  await expect(page.getByText(/Value ratio.*purchase USD \/ sale USD/)).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Net USD' })).toBeVisible();
  await expect(page.getByTestId('sector-net')).toHaveAttribute('title', '+$1,500.00');
  await expect(page.getByTestId('sector-net')).toHaveText('+$1.5K');
});

test('Market Pulse excludes a clearly flagged reported-price anomaly without hiding the SEC event', async ({ page }) => {
  await v2(page, (value) => {
    value.economicTransactions.push({ ...value.economicTransactions[0],
      eventId: 'evt_price_anomaly', accession: '0001234567-26-000004', shares: 131387,
      price: 180000, value: 23649660000, owners: [value.economicTransactions[0].owners[0]] });
    value.coverage.economicEvents += 1;
    value.coverage.canonicalOwnerRows += 1;
  });
  await ready(page);
  await section(page, 'Market Pulse');
  await expect(page.getByText('$2,000.00', { exact: true })).toBeVisible();
  await expect(page.getByTestId('pulse-value-ratio')).toHaveText('∞');
  await expect(page.getByText('1 SEC-reported price anomaly is excluded from Pulse totals')).toBeVisible();
  await section(page, 'Live SEC Tape');
  await expect(page.locator('tbody tr')).toHaveCount(3);
});

test('Market Pulse keeps late-filed older transactions in the tape but outside its 90-day chart', async ({ page }) => {
  await v2(page, (value) => {
    value.economicTransactions.push({ ...value.economicTransactions[0],
      eventId: 'evt_late_filed_old_transaction', accession: '0001234567-26-000005',
      transactionDate: '2024-01-02', shares: 500, price: 10, value: 5000,
      owners: [value.economicTransactions[0].owners[0]] });
    value.coverage.economicEvents += 1;
    value.coverage.canonicalOwnerRows += 1;
  });
  await ready(page);
  await section(page, 'Market Pulse');
  await expect(page.getByText('$2,000.00', { exact: true })).toBeVisible();
  await expect(page.getByText(/1 older transactions discovered in later filings/)).toBeVisible();
  await section(page, 'Live SEC Tape');
  await expect(page.locator('tbody tr')).toHaveCount(3);
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
