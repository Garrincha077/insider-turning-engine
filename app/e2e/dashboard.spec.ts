import { expect, test } from '@playwright/test';
import { ready, section } from './helpers';

test('every view works without errors on desktop and mobile', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  await ready(page);
  await expect(page).toHaveTitle(/Insider Turning Engine/);
  await expect(page.getByText('Experimental score — not historically validated')).toBeVisible();
  for (const label of ['Market Pulse', 'Turning Stocks', 'Divergence', 'Insider Buys', 'Clusters', 'Cost Basis', 'Live SEC Tape', 'Company Lab', 'Methodology & Validation', 'System Health', 'Data Coverage', 'Settings']) {
    await section(page, label);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
  await expect(page.getByRole('link', { name: 'Open GitHub Environment settings' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Open delivery test workflow' })).toBeVisible();
  await page.getByRole('button', { name: 'Alerts', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Informational daily digest' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Actionable alerts blocked' })).toBeVisible();
  expect(errors).toEqual([]);
});

test('unavailable manifest never substitutes samples', async ({ page }) => {
  await page.route('**/data/manifest.json', (route) => route.fulfill({ status: 503, body: '' }));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Dashboard snapshot unavailable' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry snapshot' })).toBeVisible();
  await expect(page.getByLabel('Ticker or company')).toHaveCount(0);
});

test('tampered snapshot is rejected before rendering', async ({ page }) => {
  await page.route('**/data/dashboard.json', (route) => route.fulfill({ json: { candidates: [] } }));
  await page.goto('/');
  await expect(page.getByText(/integrity mismatch/)).toBeVisible();
});

test('watchlist, filters, deep links and Company Lab return work', async ({ page }) => {
  await ready(page);
  const row = page.locator('tbody tr').first();
  const ticker = await row.locator('td').nth(2).locator('.font-mono').textContent();
  expect(ticker).toBeTruthy();
  await row.getByRole('button', { name: /to watchlist/ }).click();
  await page.getByLabel('Watchlist only').check();
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.getByLabel('Ticker or company').fill(ticker!);
  await row.getByRole('button', { name: /in Company Lab/ }).click();
  await expect(page).toHaveURL(/view=company-lab&issuer=\d{10}/);
  const url = page.url();
  expect(url).not.toContain('watch');
  await page.reload();
  await expect(page.getByRole('combobox', { name: 'Select company' })).toHaveValue(ticker!);
  await page.getByRole('button', { name: '1M', exact: true }).click();
  await expect(page.getByRole('button', { name: '1M', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: /Back to Radar/ }).click();
  await expect(page.getByLabel('Ticker or company')).toHaveValue(ticker!);
  await expect(page.getByLabel('Watchlist only')).toBeChecked();
  await page.getByLabel('Ticker or company').fill('__NO_MATCH__');
  await expect(page.getByText('No companies match these filters')).toBeVisible();
  await section(page, 'Settings');
  await page.getByLabel('Display timezone').selectOption('UTC');
  await page.reload();
  await expect(page.getByLabel('Display timezone')).toHaveValue('UTC');
  await page.getByRole('button', { name: 'Reset local preferences and watchlist' }).click();
  await expect(page.getByText('Watchlist: No companies saved')).toBeVisible();
});

test('legacy views do not manufacture clusters, totals or historical cost series', async ({ page }) => {
  await ready(page);
  await section(page, 'Clusters');
  await expect(page.getByText('Member-level evidence not available in this snapshot')).toBeVisible();
  await expect(page.getByText('CEO_CFO_CLUSTER', { exact: true })).toHaveCount(0);
  await section(page, 'Market Pulse');
  await expect(page.getByText(/Dollar totals and independent-insider counts are withheld/)).toBeVisible();
  await section(page, 'Methodology & Validation');
  await expect(page.locator('canvas')).toHaveCount(0);
  await section(page, 'Turning Stocks');
  await expect(page.locator('tbody')).not.toContainText('Falling');
  await section(page, 'Divergence');
  await expect(page.getByLabel('Minimum Insider')).toHaveValue('65');
  await expect(page.getByLabel('Minimum Divergence')).toHaveValue('65');
});

test('SEC row details, source links, filters and CSV respect the visible selection', async ({ page }) => {
  await ready(page);
  await section(page, 'Live SEC Tape');
  const ticker = await page.locator('tbody tr').first().locator('td').first().textContent();
  await page.getByLabel('Filter ticker').fill(ticker!);
  await page.getByLabel('Transaction side').selectOption('BUY');
  await page.getByLabel('Minimum USD value').fill('250000');
  const values = await page.locator('td[data-value]').evaluateAll((cells) => cells.map((cell) => Number(cell.getAttribute('data-value'))));
  expect(values.every((value) => value >= 250000)).toBe(true);
  if (values.length) {
    await page.getByText('Record details', { exact: true }).first().click();
    await expect(page.getByText('Exact grouped amount').first()).toBeVisible();
    const link = page.getByRole('link', { name: 'Open SEC document' }).first();
    if (await link.count()) await expect(link).toHaveAttribute('href', /^https:\/\/(www\.)?sec\.gov\//);
  }
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export filtered CSV' }).click();
  const stream = await (await download).createReadStream();
  let csv = ''; for await (const chunk of stream!) csv += chunk;
  const lines = csv.trim().split('\r\n');
  expect(lines[0]).toContain('Ticker');
  for (const line of lines.slice(1)) { expect(line).toContain(`"${ticker}"`); expect(line).toContain('"BUY"'); }
  await section(page, 'Radar');
  await section(page, 'Live SEC Tape');
  await expect(page.getByLabel('Filter ticker')).toHaveValue(ticker!);
});
