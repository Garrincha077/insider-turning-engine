import { expect, test } from '@playwright/test';
import { sortRows } from '../components/sort-controls';

test('numeric sorting keeps missing values last, ties stable and input unchanged', () => {
  const rows = [null, 9500, -8, 1000000, 0, 9500, Number.NaN].map((value, id) => ({ value, id }));
  const field = { id: 'value', label: 'Value', value: (row: typeof rows[number]) => row.value };
  expect(sortRows(rows, field, true).map((row) => row.id)).toEqual([3, 1, 5, 4, 2, 0, 6]);
  expect(sortRows(rows, field, false).map((row) => row.id)).toEqual([2, 4, 1, 5, 3, 0, 6]);
  expect(rows.map((row) => row.id)).toEqual([0, 1, 2, 3, 4, 5, 6]);
});

test('SEC tape starts largest first and supports headers, direction and dates', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Live SEC Tape', exact: true }).first().click();
  const values = () => page.locator('td[data-value]').evaluateAll((cells) => cells.map((cell) => Number(cell.getAttribute('data-value'))));
  const initial = await values();
  expect(initial.length).toBeGreaterThan(1);
  expect(initial).toEqual([...initial].sort((a, b) => b - a));
  await expect(page.getByRole('columnheader', { name: 'Value' })).toHaveAttribute('aria-sort', 'descending');
  await page.getByRole('button', { name: 'Value', exact: true }).click();
  expect(await values()).toEqual([...initial].sort((a, b) => a - b));
  await expect(page.getByRole('columnheader', { name: 'Value' })).toHaveAttribute('aria-sort', 'ascending');
  await page.getByRole('combobox', { name: 'Sort by' }).selectOption('filedAt');
  await expect(page.getByRole('columnheader', { name: 'Filed UTC' })).toHaveAttribute('aria-sort', 'descending');
  const dates = await page.locator('tbody tr').evaluateAll((rows) => rows.map((row) => row.children[5].textContent ?? ''));
  expect(dates).toEqual([...dates].sort().reverse());
  await page.getByRole('button', { name: 'Largest first; switch to smallest first' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('columnheader', { name: 'Filed UTC' })).toHaveAttribute('aria-sort', 'ascending');
  expect(await values()).toHaveLength(initial.length);
});

test('candidate and card views expose descending defaults and reverse controls', async ({ page }) => {
  await page.goto('/');
  for (const [view, field] of [
    ['Radar', 'total'], ['Turning Stocks', 'turn'], ['Divergence', 'divergence'],
    ['Smart Buys', 'value'], ['Clusters', 'cluster'], ['Cost Basis', 'costPl'],
  ]) {
    await page.getByRole('button', { name: view, exact: true }).first().click();
    await expect(page.getByRole('combobox', { name: 'Sort by' })).toHaveValue(field);
    await page.getByRole('button', { name: 'Largest first; switch to smallest first' }).click();
    await expect(page.getByRole('button', { name: 'Smallest first; switch to largest first' })).toBeVisible();
    await page.getByRole('combobox', { name: 'Sort by' }).selectOption('ticker');
    await expect(page.getByRole('button', { name: 'Largest first; switch to smallest first' })).toBeVisible();
  }
});
