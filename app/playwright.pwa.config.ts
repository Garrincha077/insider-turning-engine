import { defineConfig, devices } from '@playwright/test';

const part = (process.env.PAGES_BASE_PATH ?? '').replace(/^\/+|\/+$/g, '');
const base = part ? '/' + part + '/' : '/';

export default defineConfig({
  testDir: './pwa',
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'line',
  use: {
    ...devices['Pixel 7'],
    baseURL: 'http://127.0.0.1:4174' + base,
    serviceWorkers: 'allow',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4174 --strictPort',
    url: 'http://127.0.0.1:4174' + base,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
