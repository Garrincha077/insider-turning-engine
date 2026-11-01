import { expect, test } from '@playwright/test';

const site = process.env.PWA_SITE_URL;
if (!site) throw new Error('PWA_SITE_URL must be defined');

test('published mobile PWA loads verified data, reopens offline and reconnects', async ({ page, context }) => {
  await page.goto(site, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('html')).toHaveAttribute('data-hydrated', 'true', {
    timeout: 120_000,
  });
  await expect(page.getByRole('heading', { name: 'Radar', exact: true })).toBeVisible();
  await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller), null, {
    timeout: 40_000,
  });
  const cacheState = await page.evaluate(async () => {
    const names = (await caches.keys()).filter((n) => n.startsWith('ite-pwa-shell-'));
    const paths: string[] = [];
    for (const name of names) {
      const cache = await caches.open(name);
      paths.push(...(await cache.keys()).map((request) => new URL(request.url).pathname));
    }
    return { names, paths };
  });
  expect(cacheState.names).toHaveLength(1);
  expect(cacheState.paths.some((path) => path.includes('/assets/'))).toBe(true);
  expect(cacheState.paths.some((path) => path.includes('/data/'))).toBe(false);

  await context.setOffline(true);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('alert')).toContainText('You are offline', { timeout: 30_000 });
  await expect(page.getByRole('button', { name: 'Retry snapshot' })).toBeVisible();
  await context.setOffline(false);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.locator('html')).toHaveAttribute('data-hydrated', 'true', {
    timeout: 120_000,
  });
  await expect(page.getByRole('heading', { name: 'Radar', exact: true })).toBeVisible();
});
