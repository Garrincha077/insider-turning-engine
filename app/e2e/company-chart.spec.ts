import { expect, test } from '@playwright/test';
import type { Candidate, DashboardData } from '../lib/dashboard-data';
import type { EconomicEvent, ResearchSnapshot } from '../lib/research-v2';
import { buildCompanyChartOption } from '../components/company-chart';
import fixture from './fixtures/research-v2.json' with { type: 'json' };

const company: Candidate = {
  issuerCik: '0001999001', ticker: 'ACME', company: 'Acme Synthetic Holdings', sector: 'Technology',
  total: null, insider: null, divergence: null, turn: null, cluster: null, marketRs: null, sectorRs: null,
  insiderCost: 999, currentPrice: 11, state: 'UNKNOWN', reasons: [],
};
function snapshot(): DashboardData {
  return { schemaVersion: '1.0.0', scoreVersion: 'scoring.v1', generatedAt: '2026-09-01T14:00:00Z',
    status: 'EXPERIMENTAL', research: structuredClone(fixture) as unknown as ResearchSnapshot,
    marketPulse: null, pulsePercentile: null, pulseHistory: [], candidates: [company], filings: [], backtest: [],
    // Canonical issuer rows, rather than this potentially ambiguous ticker adapter, drive v2 charts.
    companySeries: [{ ticker: 'ACME', date: '2026-08-31', price: 999, cost: 999, mansfield: 999, volume: 999 }],
  };
}
function option(data: DashboardData, period = '90') { return buildCompanyChartOption({ data, company, period }); }
function observed(date: string, price = 10): ResearchSnapshot['companySeries'][number] {
  return { issuerCik: company.issuerCik, date, price, volume: 10000, marketRs: 1, sectorRs: 2 };
}
function event(data: DashboardData, changes: Partial<EconomicEvent>): EconomicEvent {
  return { ...data.research!.economicTransactions[0], ...changes };
}

test('company chart uses inclusive 90D calendar boundaries anchored to the research snapshot', () => {
  const data = snapshot();
  data.research!.companySeries = [observed('2026-06-02'), observed('2026-06-03'), observed('2026-08-20'),
    observed('2026-09-01', 999), { ...observed('2026-08-21', 999), issuerCik: '0001999002' }];
  expect(option(data).xAxis[0].data).toEqual(['2026-06-03', '2026-08-20']);
  expect(option(data, '30').xAxis[0].data).toEqual(['2026-08-20']);
  expect(option(data, '180').xAxis[0].data).toEqual(['2026-06-02', '2026-06-03', '2026-08-20']);
  expect(option(data, '365').xAxis[0].data).toEqual(['2026-06-02', '2026-06-03', '2026-08-20']);
});

test('future rows, future knowledge and a future unresolved correction cannot change the chart', () => {
  const data = snapshot();
  const before = JSON.parse(JSON.stringify(option(data)));
  data.research!.companySeries.unshift(observed('2027-08-31', 9000));
  data.research!.economicTransactions.unshift(
    event(data, { knownAt: '2026-09-01T00:00:00Z', processing: 'UNRESOLVED_AMENDMENT' }),
    event(data, { eventId: 'future-accepted', acceptedAt: '2026-09-01T00:00:00Z' }),
    event(data, { eventId: 'future-transaction', transactionDate: '2026-09-01' }),
  );
  expect(JSON.parse(JSON.stringify(option(data)))).toEqual(before);
});

test('price, volume and RS have independent aligned grids and scales', () => {
  const chart = option(snapshot());
  expect(chart.grid).toHaveLength(3);
  expect(chart.xAxis.map((axis) => axis.gridIndex)).toEqual([0, 1, 2]);
  expect(chart.yAxis.map((axis) => axis.gridIndex)).toEqual([0, 1, 2]);
  expect(chart.series.map((series) => [series.xAxisIndex, series.yAxisIndex])).toEqual([[0, 0], [1, 1], [2, 2], [2, 2]]);
  expect(chart.xAxis[1].data).toEqual(chart.xAxis[0].data);
  expect(chart.xAxis[2].data).toEqual(chart.xAxis[0].data);
  expect(chart.xAxis.map((axis) => axis.axisLabel.show)).toEqual([false, false, true]);
  expect(chart.series[0].connectNulls).toBe(false);
  expect(chart.series[2].connectNulls).toBe(true);
  expect(chart.legend.top).toBe(8);
  expect(chart.grid[0].top).toBeGreaterThanOrEqual(65);
  expect(chart.grid[2].bottom).toBeGreaterThanOrEqual(45);
});

test('economic BUY and SELL markers use dated observed adjusted closes and count events once', () => {
  const data = snapshot();
  const buy = event(data, { eventId: 'buy', price: 500 });
  const sale = event(data, { eventId: 'sale', side: 'SELL', transactionDate: '2026-08-31', price: 600 });
  data.research!.economicTransactions = [buy, { ...buy, owners: [...buy.owners, buy.owners[0]] }, sale,
    { ...buy, eventId: 'another-company', issuerCik: '0001999002' },
    { ...buy, eventId: 'no-observed-close', transactionDate: '2026-08-21' },
    { ...buy, eventId: 'unresolved', aggregateEligible: false, processing: 'UNRESOLVED_AMENDMENT' },
  ];
  const markers = option(data).series[0].markPoint!.data;
  expect(markers.map((marker) => ({ side: marker.side, coord: marker.coord, events: marker.eventIds }))).toEqual([
    { side: 'BUY', coord: ['2026-08-20', 9], events: ['buy'] },
    { side: 'SELL', coord: ['2026-08-31', 11], events: ['sale'] },
  ]);
  expect(markers.map((marker) => marker.symbol)).toEqual(['triangle', 'diamond']);
});

test('coincident distinct economic events share a marker with an explicit count', () => {
  const markers = option(snapshot()).series[0].markPoint!.data;
  expect(markers).toHaveLength(1);
  expect(markers[0].name).toBe('BUY ×2');
  expect(markers[0].eventCount).toBe(2);
  expect(markers[0].eventIds).toHaveLength(2);
  expect(markers[0].coord).toEqual(['2026-08-20', 9]);
});

test('basis is a labeled snapshot reference rather than a historical series', () => {
  const chart = option(snapshot());
  expect(chart.series[0].markLine?.data).toEqual([{ name: 'Snapshot observed 90D purchase basis', yAxis: 10 }]);
  expect(chart.series[0].markLine?.label.formatter).toBe('Observed 90D basis · $10.00');
  expect(chart.series.map((series) => series.name)).toEqual(['Adjusted price', 'Volume', 'Mansfield market RS', 'Mansfield sector RS']);
  expect(chart.series[0].data).toEqual([9, 11]);
});

test('blocked issuer facts, blocked windows and known unresolved corrections suppress basis', () => {
  for (const mutate of [
    (data: DashboardData) => { data.research!.companies[0].insiderStatus = 'SOURCE_QUARANTINE'; },
    (data: DashboardData) => { data.research!.companies[0].insiderStatus = 'UNRESOLVED_AMENDMENT'; },
    (data: DashboardData) => { data.research!.companies[0].identityStatus = 'UNRESOLVED'; },
    (data: DashboardData) => { data.research!.companies[0].basis[0].coverage = 'BLOCKED'; },
    (data: DashboardData) => { data.research!.coverage.unresolvedAmendmentIssuers.push(company.issuerCik); },
    (data: DashboardData) => { data.research!.economicTransactions.push(event(data, { eventId: 'known-correction', aggregateEligible: false, processing: 'UNRESOLVED_AMENDMENT' })); },
  ]) {
    const data = snapshot(); mutate(data);
    expect(option(data).series[0].markLine).toBeUndefined();
  }
});

test('missing price, RS and volume stay missing; a single valid observation remains visible', () => {
  const data = snapshot();
  data.research!.companySeries = [observed('2026-08-20', Number.NaN), { ...observed('2026-08-31', 11), volume: null, marketRs: null, sectorRs: null }];
  data.research!.companySeries[0].volume = null;
  data.research!.companySeries[0].marketRs = null;
  data.research!.companySeries[0].sectorRs = null;
  const chart = option(data);
  expect(chart.series.map((series) => series.data)).toEqual([[null, 11], [null, null], [null, null], [null, null]]);
  expect(chart.series[0].showSymbol).toBe(true);
  expect(chart.series[0].markPoint!.data).toEqual([]);
  data.research!.companySeries[1].price = Number.NaN;
  expect(option(data).series[0].markLine).toBeUndefined();
  data.research!.companySeries = [];
  expect(option(data).series.map((series) => series.data)).toEqual([[], [], [], []]);
});

test('legacy charts use actual dated ticker observations and never export a cost history', () => {
  const data = snapshot(); delete data.research;
  data.companySeries = [
    { ticker: 'ACME', date: '2026-08-01', price: 9, cost: 5, mansfield: null },
    { ticker: 'ACME', date: '2026-09-01', price: 11, cost: 6, mansfield: 0 },
    { ticker: 'ACME', date: '2026-09-02', price: 9000, cost: 7, mansfield: 100 },
    { ticker: 'OTHER', date: '2026-08-31', price: 9000, cost: 8, mansfield: 100 },
  ];
  const chart = option(data);
  expect(chart.series[0].data).toEqual([9, 11]);
  expect(chart.series[2].data).toEqual([null, 0]);
  expect(chart.series[1].data).toEqual([null, null]);
  expect(chart.series[0].markPoint!.data).toEqual([]);
  expect(chart.series[0].markLine?.data[0].name).toBe('Snapshot observed purchase basis (90D target)');
  data.generatedAt = 'unknown';
  expect(option(data).series[0].data).toEqual([]);
  expect(option(data).series[0].markLine).toBeUndefined();
});
