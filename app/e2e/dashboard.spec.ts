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

  expect(consoleErrors).toEqual([]);
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
