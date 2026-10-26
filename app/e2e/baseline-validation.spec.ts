import { expect, test } from '@playwright/test';
import { ready, section } from './helpers';

test('Methodology shows real development costs without claiming a full-engine or sealed test', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await ready(page);
  await section(page, 'Methodology & Validation');
  await expect(page.getByTestId('baseline-observations')).toContainText('5,965 observed / 6,094');
  await expect(page.getByTestId('baseline-observations')).toContainText('129 outcomes remain missing');
  const table = page.getByRole('table',{name:'Six-month cost sensitivity'});
  await expect(table.locator('tbody tr')).toHaveCount(4);
  await expect(table.getByRole('row',{name:/25 bps/})).toContainText('2.52%');
  await expect(table.getByRole('row',{name:/25 bps/})).toContainText('-3.87%');
  await expect(page.getByTestId('baseline-conclusion')).toContainText('median event underperformed');
  await expect(page.getByRole('link',{name:'Original source run'})).toHaveAttribute('href',
    'https://github.com/Garrincha077/insider-turning-engine/actions/runs/35277369958');
  await expect(page.getByText(/whole 2023\+ calendar cannot be assumed untouched/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});
