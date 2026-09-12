import { createHash } from 'node:crypto';
import { expect, test, type Page } from '@playwright/test';
import fixture from './fixtures/research-v2.json' with { type: 'json' };
import { ready, section } from './helpers';

async function v2(page: Page, mutate?: (value: typeof fixture) => void) {
  const data = structuredClone(fixture); mutate?.(data);
  const bytes = JSON.stringify(data);
  await page.route('**/data/research-v2.json', (route) => route.fulfill({ body: bytes, contentType: 'application/json' }));
  await page.route('**/data/manifest.json', async (route) => {
    const response = await route.fetch();
    const manifest = await response.json();
    manifest.runId = fixture.runId; manifest.asOf = fixture.asOf;
    manifest.files.push({ path: 'research-v2.json', size: Buffer.byteLength(bytes), sha256: createHash('sha256').update(bytes).digest('hex') });
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

test('v2 missing fields and mixed-run scores fail closed even with matching bytes', async ({ page }) => {
  await v2(page, (value) => { value.researchScores[0].runId = 'run_another_day'; });
  await page.goto('/');
  await expect(page.getByText('Research v2 mixed score lineage')).toBeVisible();
});
