import { defineConfig, devices } from '@playwright/test';

// Live public URL only: distinct from local fixtures and built-artifact PWA.
export default defineConfig({
  testDir: './pwa-live',
  workers: 1,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  timeout: 180_000,
  reporter: process.env.CI ? 'github' : 'line',
  use: {
    ...devices['Pixel 7'],
    serviceWorkers: 'allow',
    trace: 'retain-on-failure',
  },
});
