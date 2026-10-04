import { expect, test } from '@playwright/test';
import fixture from './fixtures/research-v2.json' with { type: 'json' };
import { buildInsiderBarometer, secDayEnd } from '../lib/insider-barometer';
import { buildBarometerChartOption } from '../components/insider-barometer-view';
import type { EconomicEvent, ResearchSnapshot } from '../lib/research-v2';

function data(): ResearchSnapshot {
  const result = structuredClone(fixture) as unknown as ResearchSnapshot;
  result.schemaVersion = '2.3.0';
  result.economicTransactions = [];
  result.coverage.expectedSecDays = [];
  for (const day = new Date('2026-05-01T00:00:00Z'); day <= new Date('2026-08-31T00:00:00Z'); day.setUTCDate(day.getUTCDate() + 1)) {
    if (![0, 6].includes(day.getUTCDay())) result.coverage.expectedSecDays.push(day.toISOString().slice(0, 10));
  }
  result.coverage.days = result.coverage.expectedSecDays.map((day) => ({ day,
    discoveredFilings: 1, storedFilings: 1, parseRows: 1, quarantinedRows: 0, failures: 0, complete: true }));
  result.benchmarkSeries = [];
  return result;
}

function event(id: string, side: 'BUY' | 'SELL', day = '2026-08-20', extra: Partial<EconomicEvent> = {}): EconomicEvent {
  return { ...structuredClone(fixture.economicTransactions[0]) as EconomicEvent,
    eventId: id, side, code: side === 'BUY' ? 'P' : 'S', transactionDate: day,
    acceptedAt: `${day}T20:00:00Z`, knownAt: `${day}T20:00:00Z`, secDay: day, ...extra };
}

test('barometer counts economic events once, independent of amounts and joint-owner count', () => {
  const snapshot = data();
  snapshot.economicTransactions = [event('a', 'BUY', undefined, { value: 1e9 }), event('b', 'BUY'), event('s', 'SELL', undefined, { value: 0 })];
  const before = buildInsiderBarometer(snapshot);
  expect(before.current).toMatchObject({ buys: 2, sales: 1, ratio: 2, partial: false });
  snapshot.economicTransactions.push(structuredClone(snapshot.economicTransactions[0]));
  expect(buildInsiderBarometer(snapshot)).toEqual(before);
});

test('no sale denominator is null, while observed zero buys with sales is a real zero', () => {
  const snapshot = data();
  snapshot.economicTransactions = [event('b', 'BUY')];
  expect(buildInsiderBarometer(snapshot).current?.ratio).toBeNull();
  snapshot.economicTransactions = [event('s', 'SELL')];
  expect(buildInsiderBarometer(snapshot).current?.ratio).toBe(0);
});

test('late acceptance/knowledge cannot change earlier rolling observations', () => {
  const snapshot = data();
  snapshot.economicTransactions = [event('s', 'SELL', '2026-08-03')];
  const before = buildInsiderBarometer(snapshot).rolling.find((row) => row.label === '2026-08-20');
  snapshot.economicTransactions.push(event('late', 'BUY', '2026-08-03', {
    secDay: '2026-08-25', acceptedAt: '2026-08-25T20:00:00Z', knownAt: '2026-08-25T20:00:00Z' }));
  expect(buildInsiderBarometer(snapshot).rolling.find((row) => row.label === '2026-08-20')).toEqual(before);
  expect(buildInsiderBarometer(snapshot).current?.ratio).toBe(1);
});

test('SEC day uses New York midnight with the correct summer, winter and DST-transition offsets', () => {
  expect(new Date(secDayEnd('2026-08-20')).toISOString()).toBe('2026-08-21T03:59:59.999Z');
  expect(new Date(secDayEnd('2026-01-20')).toISOString()).toBe('2026-01-21T04:59:59.999Z');
  expect(new Date(secDayEnd('2026-03-08')).toISOString()).toBe('2026-03-09T03:59:59.999Z');
  expect(new Date(secDayEnd('2026-11-01')).toISOString()).toBe('2026-11-02T04:59:59.999Z');
});

test('late US-evening filing enters its SEC-day reading, but knowledge from the next US day does not', () => {
  const snapshot = data();
  snapshot.economicTransactions = [event('sale', 'SELL', '2026-08-20'),
    event('late-us-evening', 'BUY', '2026-08-20', {
      acceptedAt: '2026-08-21T01:35:07Z', knownAt: '2026-08-21T01:35:07Z' })];
  const earlier = buildInsiderBarometer(snapshot).rolling.find((row) => row.label === '2026-08-20');
  expect(earlier).toMatchObject({ buys: 1, sales: 1, ratio: 1 });
  snapshot.economicTransactions.push(event('next-us-day', 'BUY', '2026-08-20', {
    acceptedAt: '2026-08-21T04:00:00Z', knownAt: '2026-08-21T04:00:00Z' }));
  expect(buildInsiderBarometer(snapshot).rolling.find((row) => row.label === '2026-08-20')).toEqual(earlier);
  expect(buildInsiderBarometer(snapshot).rolling.find((row) => row.label === '2026-08-21')?.buys).toBe(2);
});

test('latest reading and monthly totals include a completed-day import known by the current snapshot only', () => {
  const snapshot = data();
  snapshot.asOf = '2026-09-01T12:00:00Z';
  snapshot.economicTransactions = [event('sale', 'SELL', '2026-08-20')];
  const previous = buildInsiderBarometer(snapshot).rolling.find((row) => row.label === '2026-08-28');
  snapshot.economicTransactions.push(event('imported-after-sec-day', 'BUY', '2026-08-20', {
    acceptedAt: '2026-08-31T20:00:00Z', secDay: '2026-08-31', knownAt: '2026-09-01T11:00:00Z' }));
  const result = buildInsiderBarometer(snapshot);
  expect(result.current).toMatchObject({ buys: 1, sales: 1, ratio: 1 });
  expect(result.monthly.find((row) => row.label === '2026-08')).toMatchObject({ buys: 1, sales: 1, ratio: 1 });
  expect(result.rolling.find((row) => row.label === '2026-08-28')).toEqual(previous);
  snapshot.economicTransactions.push(event('not-known-yet', 'BUY', '2026-08-20', {
    acceptedAt: '2026-08-31T20:00:00Z', secDay: '2026-08-31', knownAt: '2026-09-01T12:00:01Z' }));
  expect(buildInsiderBarometer(snapshot)).toEqual(result);
});

test('future and ineligible observations cannot change current or earlier ratios', () => {
  const snapshot = data();
  snapshot.economicTransactions = [event('b', 'BUY'), event('s', 'SELL')];
  const before = buildInsiderBarometer(snapshot);
  snapshot.economicTransactions.unshift(event('b', 'BUY', undefined, { knownAt: '2026-09-01T20:00:00Z' }));
  snapshot.economicTransactions.push(event('future-day', 'BUY', '2026-09-01'),
    event('future-known', 'BUY', undefined, { knownAt: '2026-08-31T21:00:01Z' }),
    event('future-accepted', 'BUY', undefined, { acceptedAt: '2026-09-01T20:00:00Z' }),
    event('derivative', 'BUY', undefined, { table: 'DERIVATIVE' }),
    event('not-open-market', 'BUY', undefined, { code: 'A' }),
    event('unqualified', 'BUY', undefined, { qualified: false }),
    event('unresolved', 'BUY', undefined, { processing: 'UNRESOLVED_AMENDMENT' }),
    event('old', 'BUY', '2018-03-12'));
  expect(buildInsiderBarometer(snapshot)).toEqual(before);
});

test('issuer exclusions and sector filter preserve the denominator population', () => {
  const snapshot = data();
  snapshot.economicTransactions = [event('b', 'BUY'), event('s', 'SELL')];
  expect(buildInsiderBarometer(snapshot, 'Not represented').current).toMatchObject({ buys: 0, sales: 0, ratio: null });
  snapshot.companies[0].insiderStatus = 'UNRESOLVED_AMENDMENT';
  expect(buildInsiderBarometer(snapshot).current?.ratio).toBeNull();
});

test('monthly mean uses three complete calendar-month ratios, not rolling days or partial months', () => {
  const snapshot = data();
  snapshot.economicTransactions = [event('jun1', 'BUY', '2026-06-01'), event('jun2', 'BUY', '2026-06-01'), event('junS', 'SELL', '2026-06-01'),
    event('jul1', 'BUY', '2026-07-01'), event('julS1', 'SELL', '2026-07-01'), event('julS2', 'SELL', '2026-07-01'),
    event('aug1', 'BUY', '2026-08-03'), event('aug2', 'BUY', '2026-08-03'), event('aug3', 'BUY', '2026-08-03'), event('augS', 'SELL', '2026-08-03')];
  expect(buildInsiderBarometer(snapshot).monthly.at(-1)?.mean3m).toBeCloseTo((2 + 0.5 + 3) / 3);
  snapshot.coverage.days = snapshot.coverage.days.filter((row) => row.day !== '2026-07-10');
  const partial = buildInsiderBarometer(snapshot);
  expect(partial.monthly.find((row) => row.label === '2026-07')?.partial).toBe(true);
  expect(partial.monthly.at(-1)?.mean3m).toBeNull();
});

test('old missing SEC-window history is marked partial rather than fully covered', () => {
  const snapshot = data();
  snapshot.coverage.expectedSecDays = snapshot.coverage.expectedSecDays.filter((day) => day >= '2026-08-03');
  snapshot.coverage.days = snapshot.coverage.days.filter((row) => row.day >= '2026-08-03');
  const result = buildInsiderBarometer(snapshot);
  expect(result.rolling[0].partial).toBe(true);
  expect(result.monthly.at(-1)?.partial).toBe(true);
  expect(result.monthly.at(-1)?.mean3m).toBeNull();
});

test('SPY shares the ratio windows, preserves observation dates and never fills a missing month', () => {
  const snapshot = data();
  const point = { symbol: 'SPY' as const, provider: 'fixture', isAdjusted: true, adjustmentBasis: 'split-and-dividend' };
  snapshot.benchmarkSeries = [
    { ...point, date: '2026-06-01', price: 100 }, { ...point, date: '2026-06-30', price: 110 },
    { ...point, date: '2026-08-31', price: 150 }, { ...point, date: '2026-09-01', price: 10000 },
  ];
  const result = buildInsiderBarometer(snapshot);
  expect(result.monthly.map((row) => [row.label, row.spy, row.spyDate])).toEqual([
    ['2026-06', 110, '2026-06-30'], ['2026-07', null, null], ['2026-08', 150, '2026-08-31']]);
  expect(result.spyChangePct).toBe(50);
  expect(result.spyEnd).toBe('2026-08-31');
});

test('future benchmark knowledge and mixed adjustment bases cannot fabricate a SPY comparison', () => {
  const snapshot = data();
  snapshot.benchmarkSeries = [{ symbol: 'SPY', date: '2026-08-20', price: 100,
    provider: 'fixture', isAdjusted: false, adjustmentBasis: 'unadjusted', availableAt: '2026-09-01T20:00:00Z' }];
  expect(buildInsiderBarometer(snapshot).spyReason).toContain('unavailable');
  snapshot.benchmarkSeries[0].availableAt = null;
  snapshot.benchmarkSeries.push({ ...snapshot.benchmarkSeries[0], date: '2026-08-31', price: 110, isAdjusted: true });
  expect(buildInsiderBarometer(snapshot).spyReason).toContain('adjustment basis changes');
  expect(buildInsiderBarometer(snapshot).monthly.every((row) => row.spy == null)).toBe(true);
});

test('chart separates units, shares dates, retains nulls and does not manufacture buy/sell zones', () => {
  const result = buildInsiderBarometer(data());
  const option = buildBarometerChartOption(result.monthly.map((row) => ({ ...row, spy: 600 })), true, false);
  expect(option.xAxis[0].data).toEqual(option.xAxis[1].data);
  expect(option.yAxis[0].min).toBe(0);
  expect(option.yAxis[1].scale).toBe(true);
  expect(option.series[2]).toMatchObject({ name: 'SPY close', xAxisIndex: 1, yAxisIndex: 1 });
  const missing = buildBarometerChartOption(result.monthly, true, false);
  expect(missing.series.some((row) => row.name === 'SPY close')).toBe(false);
  expect(missing.grid).toHaveLength(1);
  expect(JSON.stringify(option)).not.toMatch(/BUY zone|SELL zone|markArea/);
  expect(buildBarometerChartOption(result.monthly, true, true).series[0].markLine?.data[0].yAxis).toBe(0.39);
});

test('small ratio axis ticks remain distinct rather than rounding different levels to 0.1x', () => {
  const format = buildBarometerChartOption([], true, false).yAxis[0].axisLabel.formatter;
  expect([0, 0.04, 0.08, 0.12, 0.16, 0.2].map(format)).toEqual([
    '0×', '0.04×', '0.08×', '0.12×', '0.16×', '0.2×']);
  expect([0.0004, 0.0008, 0.0012].map(format)).toEqual(['0.0004×', '0.0008×', '0.0012×']);
});
