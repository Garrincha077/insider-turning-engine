import { expect, test } from '@playwright/test';

test('dashboard loads without an error overlay and exposes every analysis view', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', (message) => {
    const isExpectedSnapshotMiss = message.location().url.includes('/data/dashboard.json');
    if (message.type() === 'error' && !isExpectedSnapshotMiss) consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => consoleErrors.push(error.message));

  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-hydrated', 'true', { timeout: 20_000 });
  await expect(page).toHaveTitle(/Insider Turning Engine/);
  await expect(page.getByRole('heading', { name: /market is still cautious/i })).toBeVisible();
  await expect(page.getByText('EXPERIMENTAL · scoring.v1')).toBeVisible();
  await expect(page.getByText(/^Live experimental snapshot:/i)).toBeVisible();
  await expect(page.locator('[data-nextjs-dialog], .vite-error-overlay')).toHaveCount(0);
  expect(consoleErrors).toEqual([]);

  await page.getByRole('button', { name: 'Market Pulse' }).first().click();
  await expect(page.getByRole('heading', { name: 'Market Pulse', exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Backtest Lab' }).first().click();
  await expect(page.getByText('Forward excess returns vs SPY')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Validation gate' })).toBeVisible();

  for (const name of ['Turning Stocks', 'Divergence', 'Smart Buys', 'Clusters', 'Cost Basis', 'Live SEC Tape', 'Company Lab', 'System Health', 'Data Coverage', 'Settings']) {
    await page.getByRole('button', { name, exact: true }).first().click();
    await expect(page.getByRole('heading', { name, exact: true }).first()).toBeVisible();
  }
  await expect(page.getByText('Configured', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Open GitHub Environment settings' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Open delivery test workflow' })).toBeVisible();
  await expect(page.getByText(/Configuration alone does not confirm delivery/).first()).toBeVisible();
  await page.getByRole('button', { name: 'Alerts', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Actionable alerts blocked' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Delivery history' })).toBeVisible();

  expect(consoleErrors).toEqual([]);
});

test('unavailable manifest does not fall back to sample data', async ({ page }) => {
  await page.route('**/data/manifest.json', (route) => route.fulfill({ status: 503, body: '' }));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Dashboard snapshot unavailable' })).toBeVisible();
  await expect(page.getByPlaceholder('Ticker or company')).toHaveCount(0);
});

test('corrupted snapshot is rejected before rendering', async ({ page }) => {
  await page.route('**/data/dashboard.json', (route) => route.fulfill({ json: { candidates: [] } }));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Dashboard snapshot unavailable' })).toBeVisible();
  await expect(page.getByText(/integrity mismatch/)).toBeVisible();
});

test('radar search filters candidates', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-hydrated', 'true', { timeout: 20_000 });
  const search = page.getByPlaceholder('Ticker or company');
  const firstTicker = await page.locator('tbody tr').first().locator('td').first().locator('.font-mono').textContent();
  expect(firstTicker).toBeTruthy();
  await search.fill(firstTicker ?? '');
  await expect(page.locator('tbody tr').first()).toContainText(firstTicker ?? '');
  await search.fill('__NO_LIVE_MATCH__');
  await expect(page.locator('tbody tr')).toHaveCount(0);
});
