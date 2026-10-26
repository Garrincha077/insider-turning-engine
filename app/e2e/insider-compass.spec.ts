import { expect, test } from '@playwright/test';
import fixture from './fixtures/research-v2.json' with { type: 'json' };
import { buildInsiderBarometer, type RatioPoint } from '../lib/insider-barometer';
import { compassContext, COMPASS_MIN_PRIOR_MONTHS } from '../lib/insider-compass';
import type { EconomicEvent, ResearchSnapshot } from '../lib/research-v2';

function point(label: string, ratio: number | null, partial = false): RatioPoint {
  return { label, start: `${label}-01`, end: `${label}-28`, ratio, partial,
    buys: 1, sales: 1, mean3m: null, spy: null, spyDate: null,
    buyDollars: 100, saleDollars: 100, dollarRatio: 1,
    buyingCompanies: 1, sellingCompanies: 1, activeCompanies: 1 };
}

function history() {
  return Array.from({ length: 24 }, (_, index) => {
    const day = new Date(Date.UTC(2024, index, 1));
    return point(day.toISOString().slice(0, 7), index / 10);
  });
}

test('Compass uses prior-only midrank, not future data, dollar ratios or pooled counts', () => {
  const prior = history(), current = point('2026-01', 1.1);
  const before = compassContext(prior, current);
  expect(before).toMatchObject({ status: 'AVAILABLE', priorMonths: 24 });
  expect(before.percentile).toBeCloseTo(100 * 11.5 / 24);
  expect(before.priorMean).toBeCloseTo(1.15);
  expect(compassContext([...prior, current, point('2026-02', 10000)], current)).toEqual(before);
  for (const row of prior) { row.buys = 1000; row.sales = 100000; row.dollarRatio = 100; }
  expect(compassContext(prior, current)).toEqual(before);
});

test('Compass requires consecutive complete prior months and excludes the comparison month', () => {
  expect(COMPASS_MIN_PRIOR_MONTHS).toBe(24);
  const prior = history(), current = point('2026-01', 0.4);
  expect(compassContext(prior.slice(1), current)).toMatchObject({
    status: 'INSUFFICIENT_HISTORY', priorMonths: 23, percentile: null, priorMean: null });
  prior[22].partial = true;
  expect(compassContext(prior, current)).toMatchObject({ priorMonths: 1, percentile: null });
  prior[22].partial = false; prior[23].ratio = null;
  expect(compassContext(prior, current)).toMatchObject({ priorMonths: 0, percentile: null });
  expect(compassContext(history(), point('2026-01', 100, true))).toMatchObject({
    status: 'PARTIAL_MONTH', percentile: null });
  expect(compassContext(history(), point('2026-01', null))).toMatchObject({
    status: 'NO_SALE_DENOMINATOR', percentile: null });
});

test('Compass labels activity extremes without predicting a market top or bottom', () => {
  expect(compassContext(history(), point('2026-01', 10)).reading).toBe('Unusually high buying activity');
  expect(compassContext(history(), point('2026-01', 2)).reading).toBe('Elevated buying activity');
  const low = compassContext(history(), point('2026-01', 0));
  expect(low.reading).toBe('Relatively sale-heavy activity');
  expect(low.explanation).toContain('low buying does not establish a top');
});

function snapshot(): ResearchSnapshot {
  const value = structuredClone(fixture) as unknown as ResearchSnapshot;
  value.asOf = '2026-09-01T12:00:00Z'; value.schemaVersion = '2.3.0';
  value.coverage.expectedSecDays = [];
  for (const day = new Date('2026-05-01T00:00:00Z'); day <= new Date('2026-08-31T00:00:00Z'); day.setUTCDate(day.getUTCDate() + 1)) {
    value.coverage.expectedSecDays.push(day.toISOString().slice(0, 10));
  }
  value.coverage.days = value.coverage.expectedSecDays.map((day) => ({ day,
    discoveredFilings: 1, storedFilings: 1, parseRows: 1, quarantinedRows: 0, failures: 0, complete: true }));
  value.economicTransactions = []; value.benchmarkSeries = [];
  return value;
}

function event(id: string, cik: string, side: 'BUY' | 'SELL', amount: number | null): EconomicEvent {
  return { ...structuredClone(fixture.economicTransactions[0]) as EconomicEvent,
    eventId: id, issuerCik: cik, side, code: side === 'BUY' ? 'P' : 'S', value: amount,
    transactionDate: '2026-08-20', secDay: '2026-08-20',
    acceptedAt: '2026-08-20T20:00:00Z', knownAt: '2026-08-20T20:00:00Z' };
}

test('monthly count, dollars and breadth use economic grain and include seller-only issuers', () => {
  const data = snapshot(), first = data.companies[0];
  data.companies = [first, { ...first, issuerCik: '0009999998' }, { ...first, issuerCik: '0009999999' }];
  data.economicTransactions = [event('a', first.issuerCik, 'BUY', 900),
    event('b', first.issuerCik, 'BUY', 100), event('c', first.issuerCik, 'SELL', 100),
    event('d', '0009999998', 'SELL', 100), event('e', '0009999999', 'BUY', 200)];
  const row = buildInsiderBarometer(data).monthly.at(-1);
  expect(row).toMatchObject({ buys: 3, sales: 2, ratio: 1.5, buyDollars: 1200,
    saleDollars: 200, dollarRatio: 6, buyingCompanies: 2, sellingCompanies: 2, activeCompanies: 3 });
  data.economicTransactions.push(structuredClone(data.economicTransactions[0]));
  expect(buildInsiderBarometer(data).monthly.at(-1)).toEqual(row);
  data.economicTransactions[0].value = null;
  expect(buildInsiderBarometer(data).monthly.at(-1)).toMatchObject({ ratio: 1.5,
    buyDollars: null, saleDollars: 200, dollarRatio: null, buyingCompanies: 2 });
});

test('all-history uses exported months without manufacturing absent history or trusting a false complete flag', () => {
  const data = snapshot();
  expect(buildInsiderBarometer(data, 'All sectors', 'ALL').monthly.map((row) => row.label))
    .toEqual(['2026-05', '2026-06', '2026-07', '2026-08']);
  data.coverage.days.find((row) => row.day === '2026-07-01')!.quarantinedRows = 1;
  expect(buildInsiderBarometer(data).monthly.find((row) => row.label === '2026-07')!.partial).toBe(true);
});

test('future records cannot change monthly dollars, breadth or historical context', () => {
  const data = snapshot(), cik = data.companies[0].issuerCik;
  data.economicTransactions = [event('a', cik, 'BUY', 100), event('b', cik, 'SELL', 200)];
  const before = buildInsiderBarometer(data, 'All sectors', 'ALL');
  data.economicTransactions.unshift({ ...event('a', cik, 'BUY', 1e12), knownAt: '2026-09-02T20:00:00Z' });
  data.economicTransactions.push({ ...event('future', cik, 'BUY', 1e12), acceptedAt: '2026-09-02T20:00:00Z' });
  expect(buildInsiderBarometer(data, 'All sectors', 'ALL')).toEqual(before);
});
