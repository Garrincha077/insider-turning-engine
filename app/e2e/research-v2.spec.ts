import { createHash } from 'node:crypto';
import { gzipSync } from 'node:zlib';
import { expect, test, type Page } from '@playwright/test';
import fixture from './fixtures/research-v2.json' with { type: 'json' };
import { ready, section } from './helpers';
import originalSettings from './public/data/settings-status.json' with { type: 'json' };
import type { SettingsStatus } from '../lib/operations-data';
import type { ResearchSnapshot } from '../lib/research-v2';
import { createWatchlistBaseline } from '../lib/watchlist-changes';

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

test('company and basis tables page the full sorted selection without truncating CSV', async ({ page }) => {
  await v2(page, (value) => {
    const research = value as unknown as ResearchSnapshot;
    const company = research.companies[0];
    for (let index = 1; index < 65; index++) research.companies.push({ ...company,
      issuerCik: String(8000000 + index).padStart(10, '0'),
      ticker: `PAGE${String(index).padStart(3, '0')}`, name: `Page company ${index}` });
  });
  await ready(page);
  for (const view of ['Radar', 'Cost Basis']) {
    await section(page, view);
    await expect(page.locator('tbody tr')).toHaveCount(25);
    const nav = page.getByRole('navigation', { name: view === 'Radar' ? 'Company pages (top)' : 'Basis pages (top)' });
    await nav.getByRole('button', { name: 'Last', exact: true }).click();
    await expect(page.locator('tbody tr')).toHaveCount(15);
    await expect(nav.getByRole('status')).toHaveText('Showing 51–65 of 65 · page 3 of 3');
    await expect(nav.getByRole('button', { name: 'Next', exact: true })).toBeDisabled();
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export filtered CSV' }).click();
    const stream = await (await download).createReadStream();
    let csv = ''; for await (const chunk of stream!) csv += chunk;
    expect(csv.trim().split('\r\n')).toHaveLength(66);
    await page.getByLabel('Sort by').selectOption('ticker');
    await expect(nav.getByRole('status')).toHaveText('Showing 1–25 of 65 · page 1 of 3');
    await expect(page.locator('tbody tr').first()).toContainText('PAGE064');
    await nav.getByRole('button', { name: 'Next', exact: true }).click();
    await page.getByLabel(view === 'Radar' ? 'Ticker or company' : 'Filter basis company').fill('PAGE001');
    await expect(page.locator('tbody tr')).toHaveCount(1);
    await expect(nav.getByRole('status')).toHaveText('Showing 1–1 of 1 · page 1 of 1');
    await page.getByLabel(view === 'Radar' ? 'Ticker or company' : 'Filter basis company').fill('');
    await page.getByLabel(view === 'Radar' ? 'Company rows per page (top)' : 'Basis rows per page (top)').selectOption('50');
    await expect(page.locator('tbody tr')).toHaveCount(50);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('candidate evidence stays factual through Radar, Company Lab and watchlist', async ({ page }) => {
  await v2(page);
  await ready(page);
  const row = page.locator('tbody tr').first();
  await expect(row).toContainText('2 observed purchases');
  await expect(row).toContainText('1 verified cluster in 30D');
  await row.getByText('Evidence & limitations').click();
  await expect(row).toContainText('reported by 3 distinct reporting owners');
  await expect(row).toContainText('Partial observed SEC window');
  await page.getByRole('button', { name: 'Add ACME to watchlist' }).click();
  await page.getByRole('button', { name: 'Open ACME in Company Lab' }).click();
  await expect(page.getByTestId('company-factual-summary')).toContainText('2 observed qualified purchases totaling $2K');
  await expect(page.getByText('Investment idea · evidence to review', { exact: true })).toBeVisible();
  await expect(page.getByText('Price above observed 50-close average', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Remove ACME from watchlist' })).toBeVisible();
  await page.getByRole('button', { name: '3M', exact: true }).click();
  await expect(page.getByTestId('company-chart-window')).toContainText('2026-06-03–2026-08-31');
  await page.getByRole('button', { name: '← Back to Radar' }).click();
  await page.getByRole('checkbox', { name: 'Watchlist only' }).check();
  await expect(page.locator('tbody tr')).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('Radar factual shortlist works without scores, excludes missing prices and exports only its selection', async ({ page }) => {
  await v2(page, (value) => {
    const research = value as unknown as ResearchSnapshot;
    const original = research.companies[0];
    research.companies.push({ ...original, issuerCik: '0001999002', ticker: 'SMALL', name: 'Small purchase' },
      { ...original, issuerCik: '0001999003', ticker: 'NOPRICE', name: 'Missing prices' });
    research.clusters = [];
    const event = research.economicTransactions[0];
    event.shares = 30000; event.value = 300000;
    research.economicTransactions.push({ ...event, eventId: 'small_purchase', issuerCik: '0001999002', shares: 100, value: 1000 },
      { ...event, eventId: 'missing_price_purchase', issuerCik: '0001999003' });
    research.companySeries = [
      { issuerCik: original.issuerCik, date: '2026-08-20', price: 10, volume: null, marketRs: null, sectorRs: null },
      { issuerCik: original.issuerCik, date: '2026-08-31', price: 6, volume: null, marketRs: null, sectorRs: null },
      { issuerCik: '0001999002', date: '2026-08-20', price: 10, volume: null, marketRs: null, sectorRs: null },
      { issuerCik: '0001999002', date: '2026-08-31', price: 6, volume: null, marketRs: null, sectorRs: null },
    ];
  });
  await ready(page);
  await expect(page.locator('tbody tr')).toHaveCount(3);
  await page.getByRole('checkbox', { name: 'Significant buying + weak price' }).check();
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await expect(page.locator('tbody tr')).toContainText('ACME');
  await expect(page.locator('tbody tr')).toContainText('-40%');
  await expect(page.getByText(/this screen does not change scores/)).toBeVisible();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export filtered CSV' }).click();
  const stream = await (await download).createReadStream();
  let csv = ''; for await (const chunk of stream!) csv += chunk;
  expect(csv.trim().split('\r\n')).toHaveLength(2);
  expect(csv).toContain('ACME'); expect(csv).not.toContain('NOPRICE');
  await page.reload();
  await expect(page.getByRole('checkbox', { name: 'Significant buying + weak price' })).toBeChecked();
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.getByRole('checkbox', { name: 'Significant buying + weak price' }).uncheck();
  await expect(page.locator('tbody tr')).toHaveCount(3);
});

test('turning phases expose met and missing evidence without inventing transitions', async ({ page }) => {
  await v2(page, (value) => {
    const research = value as unknown as ResearchSnapshot;
    research.researchScores = [{ issuerCik: research.companies[0].issuerCik,
      total: 75, insider: 80, divergence: 70, turn: 65, cluster: 70, marketRs: -2, sectorRs: null,
      state: 'BASE_FORMING', stateChangedAt: '2026-08-28T21:00:00Z',
      reasons: ['TOP_CONTRIBUTION_CLUSTER'], scoreVersion: research.scoreVersion,
      methodologyHash: null, configHash: null, runId: research.runId, asOf: research.asOf }];
  });
  await ready(page);
  await section(page, 'Turning Stocks');
  const row = page.locator('tbody tr');
  await expect(row).toContainText('A base is recorded');
  await row.getByText('Evidence & limitations').click();
  await expect(row).toContainText('Needs confirmation · Market relative strength');
  await expect(row).toContainText('Unavailable · Sector relative strength');
  await page.getByRole('button', { name: /Early turn \(0\)/i }).click();
  await expect(page.getByText('No companies match these filters')).toBeVisible();
  await section(page, 'Divergence');
  await expect(page.locator('tbody tr')).toContainText('2 observed purchases');
  await page.getByLabel('Minimum Divergence').fill('75');
  await expect(page.getByText('No companies match these filters')).toBeVisible();
});

test('watchlist updates survive reload and never label first-visit backlog as new', async ({ page }) => {
  const prior = structuredClone(fixture) as unknown as ResearchSnapshot;
  prior.runId = 'prior_verified_run'; prior.asOf = '2026-08-30T21:00:00Z';
  prior.researchScores.forEach((row) => { row.runId = prior.runId; row.asOf = prior.asOf; row.state = 'BASE_FORMING'; });
  const cik = prior.companies[0].issuerCik;
  await page.addInitScript(({ cik, baseline }) => {
    if (localStorage.getItem('test.seeded-watchlist')) return;
    localStorage.setItem('test.seeded-watchlist', 'true');
    localStorage.setItem('ite.daily.v1.watchlist', JSON.stringify([cik]));
    localStorage.setItem('ite.daily.v1.watchlist.tracking', JSON.stringify({ version: 1, current: baseline, previous: null }));
  }, { cik, baseline: createWatchlistBaseline(prior, [cik]) });
  await v2(page, (value) => {
    const current = value as unknown as ResearchSnapshot;
    const event = { ...current.economicTransactions[0], eventId: 'new_watch_purchase',
      accession: '0001234567-26-000003', transactionDate: '2026-08-31',
      acceptedAt: '2026-08-31T20:00:00Z', knownAt: '2026-08-31T20:00:00Z', value: 100_000, shares: 10_000 };
    current.economicTransactions.push(event);
    current.clusters[0].eventIds.push(event.eventId);
    current.clusters[0].purchaseValue += event.value;
    current.clusters[0].end = event.transactionDate;
    current.researchScores[0].state = 'EARLY_TURN';
    current.researchScores[0].stateChangedAt = '2026-08-31T20:00:00Z';
    current.companies[0].basis.forEach((window) => { window.purchaseValue = 102_000; window.purchaseCount = 3; });
  });
  await ready(page);
  const updates = page.getByTestId('watchlist-updates');
  await expect(updates).toContainText('3 observed changes');
  await expect(updates).toContainText('New purchase · $100K');
  await expect(updates).toContainText('New cluster evidence');
  await expect(updates).toContainText('Base forming → Early turn');
  await page.reload();
  await expect(updates).toContainText('3 observed changes');
  await expect(updates.getByRole('link', { name: 'SEC', exact: true })).toHaveCount(1);
  await page.evaluate(() => localStorage.removeItem('ite.daily.v1.watchlist.tracking'));
  await page.reload();
  await updates.locator('summary').click();
  await expect(updates).toContainText('A local baseline is saved');
  await expect(updates).not.toContainText('New purchase');
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
  await expect(page.getByTestId('insider-ratio-zone')).toContainText('Historical percentile / z-score unavailable');
  await expect(page.getByTestId('barometer-spy-status')).toContainText('SPY observations are unavailable');
  await expect(page.getByRole('button', { name: 'Calendar months' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Daily rolling 30D' }).click();
  await expect(page.getByRole('button', { name: 'Daily rolling 30D' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByText('Research context & calculation', { exact: true }).click();
  await expect(page.getByText(/Each economic event is counted once/)).toBeVisible();
});

test('twenty overlapping rolling observations do not manufacture calibrated market signals', async ({ page }) => {
  await v2(page, (value) => {
    const research = value as unknown as ResearchSnapshot;
    const days: string[] = [];
    for (const cursor = new Date('2026-08-03T00:00:00Z'); cursor <= new Date('2026-08-31T00:00:00Z'); cursor.setUTCDate(cursor.getUTCDate() + 1)) {
      if (![0, 6].includes(cursor.getUTCDay())) days.push(cursor.toISOString().slice(0, 10));
    }
    research.coverage.expectedSecDays = days;
    research.coverage.days = days.map((day) => ({ day, discoveredFilings: 1,
      storedFilings: 1, parseRows: 1, quarantinedRows: 0, failures: 0, complete: true }));
    research.economicTransactions.forEach((row) => {
      row.transactionDate = '2026-08-03'; row.secDay = '2026-08-03';
      row.acceptedAt = '2026-08-03T20:00:00Z'; row.knownAt = '2026-08-03T20:00:00Z';
    });
    const template = research.economicTransactions[0];
    const add = (id: string, side: 'BUY' | 'SELL', day: string) => research.economicTransactions.push({ ...template,
      eventId: `evt_ratio_${id}`, accession: `0001234567-26-${id.padStart(6, '0')}`,
      transactionDate: day, secDay: day, acceptedAt: `${day}T20:00:00Z`, knownAt: `${day}T20:00:00Z`,
      code: side === 'BUY' ? 'P' : 'S', side, owners: [template.owners[0]] });
    add('10', 'SELL', '2026-08-03');
    add('11', 'SELL', '2026-08-12'); add('12', 'SELL', '2026-08-12');
    for (const id of ['20', '21', '22', '23']) add(id, 'BUY', '2026-08-24');
    research.coverage.economicEvents = research.economicTransactions.length;
    research.coverage.canonicalOwnerRows += 7;
  });
  await ready(page);
  await section(page, 'Insider Ratio');
  await expect(page.getByTestId('insider-ratio-current')).toHaveText('2×');
  await expect(page.getByTestId('insider-ratio-zone')).toContainText('comparable long-history data is not established');
  await expect(page.getByText(/Historical BUY zone|Historical SELL zone/)).toHaveCount(0);
  await expect(page.locator('canvas').first()).toBeVisible();
});

test('v2.3 SPY chart uses actual prices and source metadata with working sector/reference controls', async ({ page }) => {
  await v2(page, (value) => {
    const research = value as unknown as ResearchSnapshot;
    research.schemaVersion = '2.3.0';
    research.coverage.expectedSecDays = ['2026-08-28', '2026-08-31'];
    research.coverage.days = research.coverage.expectedSecDays.map((day) => ({ day,
      discoveredFilings: 1, storedFilings: 1, parseRows: 1, quarantinedRows: 0, failures: 0, complete: true }));
    research.economicTransactions.forEach((row) => { row.secDay = '2026-08-28'; });
    research.benchmarkSeries = [{ symbol: 'SPY', date: '2026-08-31', price: 600,
      provider: 'fixture-adjusted', isAdjusted: true, adjustmentBasis: 'split-and-dividend', availableAt: '2026-08-31T20:00:00Z' }];
  });
  await ready(page);
  await section(page, 'Insider Ratio');
  await expect(page.getByTestId('barometer-spy-status')).toContainText('fixture-adjusted · split-and-dividend');
  const observed = await page.evaluate(async () => {
    const modulePath = '/node_modules/.vite/deps/echarts_core.js';
    const engine = await import(modulePath) as typeof import('echarts/core');
    const chart = engine.getInstanceByDom(document.querySelector<HTMLElement>('[_echarts_instance_]')!);
    const option = chart!.getOption() as { series: Array<{ name: string; data: Array<number | null> }>; grid: Array<{ top: string | number }> };
    return { spy: option.series.find((row) => row.name === 'SPY close')?.data, grids: option.grid.length };
  });
  expect(observed.spy?.at(-1)).toBe(600);
  expect(observed.grids).toBe(2);
  const reference = page.getByRole('checkbox', { name: /Show GuruFocus published mean/ });
  await reference.check();
  await page.getByLabel('Ratio sector').selectOption('Technology');
  await expect(reference).toHaveCount(0);
  await page.getByLabel('Ratio sector').selectOption('All sectors');
  await expect(reference).toBeChecked();
  await page.getByRole('button', { name: 'Daily rolling 30D' }).click();
  await expect(reference).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('detailed snapshot loading never presents a conflicting legacy company phase', async ({ page }) => {
  await v2(page);
  let release!: () => void;
  const delayed = new Promise<void>((resolve) => { release = resolve; });
  await page.route('**/data/research-v2.json', async (route) => { await delayed; await route.fallback(); });
  await page.goto('/');
  await expect(page.getByText(/Detailed facts and phases appear only after validation/)).toBeVisible();
  await expect(page.getByRole('table')).toHaveCount(0);
  release();
  await expect(page.getByLabel('Ticker or company')).toBeVisible();
});

for (const corrupt of ['future', 'duplicate'] as const) test(`v2.3 rejects ${corrupt} benchmark observations`, async ({ page }) => {
  await v2(page, (value) => {
    const research = value as unknown as ResearchSnapshot;
    research.schemaVersion = '2.3.0';
    const point = { symbol: 'SPY' as const, date: '2026-08-31', price: 600,
      provider: 'fixture', isAdjusted: true, adjustmentBasis: 'split-and-dividend', availableAt: '2026-08-31T20:00:00Z' };
    research.benchmarkSeries = corrupt === 'duplicate' ? [point, point]
      : [{ ...point, availableAt: '2026-09-01T20:00:00Z' }];
  });
  await page.goto('/');
  await expect(page.getByText(`Research v2 ${corrupt} benchmark`)).toBeVisible();
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

test('a future SEC day cannot pass the client semantic guard', async ({ page }) => {
  await v2(page, (value) => { (value as unknown as ResearchSnapshot).economicTransactions[0].secDay = '2026-09-02'; });
  await page.goto('/');
  await expect(page.getByText('Research v2 future event')).toBeVisible();
});

test('series date validation uses the UTC snapshot day, not its offset-local date', async ({ page }) => {
  await v2(page, (value) => {
    value.asOf = '2026-09-01T07:00:00+10:00'; // Same instant as the manifest, but next local date.
    value.companySeries[0].date = '2026-09-01';
  });
  await page.goto('/');
  await expect(page.getByText('Research v2 invalid company series')).toBeVisible();
});

test('Insider Buys excludes held aggregate events while SEC Tape keeps them inspectable', async ({ page }) => {
  await v2(page, (value) => {
    value.economicTransactions[0].aggregateEligible = false;
    value.economicTransactions[0].processing = 'UNRESOLVED_AMENDMENT';
    value.clusters = [];
  });
  await ready(page);
  await section(page, 'Insider Buys');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await section(page, 'Live SEC Tape');
  await expect(page.locator('tbody tr')).toHaveCount(2);
});

test('new incomplete SEC day is disclosed instead of looking like a fully current barometer', async ({ page }) => {
  await v2(page, (value) => {
    const research = value as unknown as ResearchSnapshot;
    research.coverage.expectedSecDays = ['2026-08-28', '2026-08-31'];
    research.coverage.days = [
      { day: '2026-08-28', discoveredFilings: 1, storedFilings: 1, parseRows: 1, quarantinedRows: 0, failures: 0, complete: true },
      { day: '2026-08-31', discoveredFilings: 1, storedFilings: 0, parseRows: 0, quarantinedRows: 0, failures: 1, complete: false },
    ];
    research.economicTransactions.forEach((row) => { row.secDay = '2026-08-28'; });
  });
  await ready(page);
  await section(page, 'Insider Ratio');
  await expect(page.getByText(/Newest inventoried SEC day 2026-08-31 is incomplete/)).toBeVisible();
  await expect(page.getByText(/barometer is held at 2026-08-28/)).toBeVisible();
});

test('daily-use coverage accepts 85% without pretending the predictive 90% gate passed', async ({ page }) => {
  await page.route('**/data/manifest.json', async (route) => {
    const response = await route.fetch();
    const manifest = await response.json();
    manifest.quality.marketCoverage = { numerator: 85, denominator: 100, rate: 0.85, threshold: 0.9, result: 'FAIL' };
    await route.fulfill({ json: manifest });
  });
  await ready(page);
  await section(page, 'System Health');
  await expect(page.getByText('Daily-use market coverage', { exact: true })).toBeVisible();
  await expect(page.getByText(/85\.00%.*daily-use target ≥80%.*Target met.*15 selected issuers missing prices/)).toBeVisible();
  await page.getByText('Separate predictive validation gates', { exact: true }).click();
  await expect(page.getByText(/Predictive market-coverage gate: 90% \(FAIL\)/)).toBeVisible();
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
  await expect(page.getByTestId('pulse-value-ratio')).toHaveText('—');
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
      .find((instance) => (instance?.getOption() as { series?: Array<{ name?: string }> } | undefined)?.series?.some((item) => item.name === 'Observed close'));
    const option = chart!.getOption() as { legend: Array<{ top: number; bottom: number | null }>; grid: Array<{ top: number; bottom: number }>; xAxis: Array<{ axisLabel: { hideOverlap: boolean } }> };
    return { legend: option.legend[0], grid: { top: option.grid[0].top, bottom: option.grid.at(-1)!.bottom }, xAxis: option.xAxis.at(-1)! };
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

test('v2.2 missing derivative code remains a factual non-signal event', async ({ page }) => {
  await v2(page, (value) => {
    const research = value as unknown as ResearchSnapshot;
    research.schemaVersion = '2.2.0';
    research.economicTransactions.push({ ...research.economicTransactions[0],
      eventId: 'event_missing_derivative_code', table: 'DERIVATIVE', code: null,
      side: 'OTHER', qualified: false, aggregateEligible: false });
    research.coverage.economicEvents += 1;
    research.coverage.canonicalOwnerRows += 2;
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

for (const policy of [
  { minimumPurchaseUsd: 100000, maximumItems: 10 },
  { minimumPurchaseUsd: 250000, maximumItems: 5 },
]) test(`digest preview and Settings describe the published ${policy.maximumItems}-item policy`, async ({ page }) => {
  await v2(page, undefined, { enabled: true,
    secDay: [...fixture.coverage.expectedSecDays].sort((a: string, b: string) => a.localeCompare(b)).at(-1) ?? null,
    status: 'BLOCKED', reasons: ['LATEST_SEC_DAY_INCOMPLETE'], eventIds: [],
    excludedIssuers: 0, ...policy });
  await ready(page);
  const summary = `Up to ${policy.maximumItems} purchases ≥ $${policy.minimumPurchaseUsd.toLocaleString('en-US')}.`;
  for (const view of ['Alert Center', 'Settings']) {
    await section(page, view);
    await expect(page.getByText(summary, { exact: false })).toBeVisible();
  }
});

test('older snapshots do not invent digest thresholds or a local selection', async ({ page }) => {
  await v2(page);
  await ready(page);
  await section(page, 'Alert Center');
  await expect(page.getByText('The server-generated digest preview is unavailable in this snapshot.')).toBeVisible();
  for (const view of ['Alert Center', 'Settings']) {
    await section(page, view);
    await expect(page.getByText('Selection thresholds are unavailable in this snapshot.', { exact: false })).toBeVisible();
    await expect(page.getByText(/Up to (five|ten|5|10).*purchases/)).toHaveCount(0);
  }
});

test('digest event references from another snapshot fail closed', async ({ page }) => {
  await v2(page, undefined, { enabled: true, secDay: [...fixture.coverage.expectedSecDays].sort((a: string, b: string) => a.localeCompare(b)).at(-1) ?? null,
    status: 'READY', reasons: [], eventIds: ['not-in-this-run'], excludedIssuers: 0 });
  await page.goto('/');
  await expect(page.getByText('Digest status does not match the research publication')).toBeVisible();
});
