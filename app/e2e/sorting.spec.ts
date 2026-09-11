import { expect, test } from '@playwright/test';
import { sortRows } from '../components/sort-controls';
import { companyCatalog, csvText, metric, money, secUrl } from '../lib/research';
import { sampleDashboardData } from '../lib/dashboard-data';
import { ready, section } from './helpers';

test('numeric sorting is stable, null-last and non-mutating', () => {
  const rows = [null, 9500, -8, 1000000, 0, 9500, Number.NaN].map((value, id) => ({ value, id }));
  const field = { id: 'value', label: 'Value', value: (row: typeof rows[number]) => row.value };
  expect(sortRows(rows, field, true).map((row) => row.id)).toEqual([3, 1, 5, 4, 2, 0, 6]);
  expect(sortRows(rows, field, false).map((row) => row.id)).toEqual([2, 4, 1, 5, 3, 0, 6]);
  expect(rows.map((row) => row.id)).toEqual([0, 1, 2, 3, 4, 5, 6]);
});

test('legacy catalogue exposes scoreless companies without invented identity or state', () => {
  const data = { ...sampleDashboardData, filings: [...sampleDashboardData.filings, { ...sampleDashboardData.filings[0], ticker: 'MISSING' }] };
  const row = companyCatalog(data).find((item) => item.ticker === 'MISSING');
  expect(row).toMatchObject({ issuerCik: '', state: 'UNKNOWN', total: null, insiderCost: null });
  expect(metric(null)).toBe('—'); expect(metric(0)).toBe('0'); expect(money(250)).toBe('$250.00');
  expect(csvText(['Owner'], [['=HYPERLINK("evil")']])).toContain("'=HYPERLINK");
  expect(secUrl({ ...data.filings[0], sourceReferences: { url: 'javascript:alert(1)' } })).toBeUndefined();
});

test('tape sorting, dates, pagination and descending defaults', async ({ page }) => {
  await ready(page);
  await section(page, 'Live SEC Tape');
  const values = () => page.locator('td[data-value]').evaluateAll((cells) => cells.map((cell) => Number(cell.getAttribute('data-value'))));
  const initial = await values(); expect(initial.length).toBeGreaterThan(1);
  expect(initial).toEqual([...initial].sort((a, b) => b - a));
  await page.getByRole('columnheader', { name: /Value/ }).getByRole('button').click();
  const ascending = await values(); expect(ascending).toEqual([...ascending].sort((a, b) => a - b));
  await page.getByRole('combobox', { name: 'Sort by' }).selectOption('filedAt');
  const dates = await page.locator('td[data-timestamp]').evaluateAll((cells) => cells.map((cell) => Number(cell.getAttribute('data-timestamp'))));
  expect(dates).toEqual([...dates].sort((a, b) => b - a));
  await expect(page.getByRole('columnheader', { name: /Accepted/ })).toHaveAttribute('aria-sort', 'descending');
  const next = page.getByRole('button', { name: 'Next', exact: true });
  if (await next.isEnabled()) { await next.click(); await expect(page.getByText(/page 2 of/)).toBeVisible(); }
  for (const [label, field] of [['Radar', 'total'], ['Turning Stocks', 'turn'], ['Divergence', 'divergence'], ['Insider Buys', 'value'], ['Cost Basis', 'costPl']]) {
    await section(page, label);
    await expect(page.getByRole('combobox', { name: 'Sort by' })).toHaveValue(field);
    await page.getByRole('button', { name: 'Largest first; switch to smallest first' }).click();
    await expect(page.getByRole('button', { name: 'Smallest first; switch to largest first' })).toBeVisible();
  }
});
