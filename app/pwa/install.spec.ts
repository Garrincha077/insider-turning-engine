import { expect, test } from '@playwright/test';

const part = (process.env.PAGES_BASE_PATH ?? '').replace(/^\/+|\/+$/g, '');
const base = part ? '/' + part + '/' : '/';
const url = 'http://127.0.0.1:4174' + base;

test('Android PWA has a valid, scoped install manifest and opaque PNG icons', async ({ request }) => {
  const response = await request.get(url + 'manifest.webmanifest');
  expect(response.ok()).toBe(true);
  const manifest = await response.json();
  expect(manifest).toMatchObject({
    name: 'Insider Turning Engine',
    id: base,
    start_url: base,
    scope: base,
    display: 'standalone',
  });
  expect(manifest.icons.map((item: { sizes: string }) => item.sizes)).toEqual([
    '192x192', '512x512',
  ]);
  for (const [size, icon] of [[192, manifest.icons[0]], [512, manifest.icons[1]]] as const) {
    const image = await request.get('http://127.0.0.1:4174' + icon.src);
    expect(image.ok()).toBe(true);
    const bytes = await image.body();
    expect(bytes.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
    expect(bytes.readUInt32BE(16)).toBe(size);
    expect(bytes.readUInt32BE(20)).toBe(size);
  }
  const shell = await request.get(url);
  expect(shell.ok()).toBe(true);
  const html = await shell.text();
  expect(html).toContain('rel="manifest"');
  expect(html).toContain(base + 'manifest.webmanifest');
});

test('installed shell survives offline reload, but never caches financial data', async ({ page, context }) => {
  await page.goto(url + '#view=backtest-lab');
  await expect(page.getByRole('heading', { name: 'Methodology & Validation' }))
    .toBeVisible({ timeout: 45_000 });
  await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller), null,
    { timeout: 30_000 });
  const cacheProof = await page.evaluate(async () => {
    const names = await caches.keys();
    const appCaches = names.filter((name) => name.startsWith('ite-pwa-shell-'));
    const keys: string[] = [];
    for (const name of appCaches) {
      const cache = await caches.open(name);
      keys.push(...(await cache.keys()).map((request) => new URL(request.url).pathname));
    }
    return { appCaches, keys };
  });
  expect(cacheProof.appCaches).toHaveLength(1);
  expect(cacheProof.keys.some((item) => item.includes('/assets/'))).toBe(true);
  expect(cacheProof.keys.some((item) => item.includes('/data/'))).toBe(false);
  await context.setOffline(true);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('alert')).toContainText('You are offline', { timeout: 30_000 });
  // Chromium may report navigator.onLine=true while network requests fail.
  await expect(page.getByRole('button', { name: 'Retry snapshot' })).toBeVisible();
  await context.setOffline(false);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Methodology & Validation' }))
    .toBeVisible({ timeout: 45_000 });
});
