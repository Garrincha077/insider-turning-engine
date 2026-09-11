import { expect, type Page } from '@playwright/test';

export async function section(page: Page, label: string) {
  const mobile = page.getByRole('combobox', { name: 'Dashboard section' });
  if (await mobile.isVisible()) await mobile.selectOption({ label });
  else await page.getByRole('navigation', { name: 'Dashboard sections' }).getByRole('button', { name: label, exact: true }).click();
  await expect(page.getByRole('heading', { name: label, exact: true }).first()).toBeVisible();
}

export async function ready(page: Page) {
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-hydrated', 'true', { timeout: 20_000 });
}
