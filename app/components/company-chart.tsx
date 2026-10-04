import { useId, useMemo } from 'react';
import type { Candidate, DashboardData } from '../lib/dashboard-data';
import type { EconomicEvent } from '../lib/research-v2';
import { EChart } from './echart';

type CompanyChartProps = { data: DashboardData; company: Candidate; period: string };
type Observation = { date: string; price: number | null; volume: number | null; marketRs: number | null; sectorRs: number | null };
type TransactionMarker = {
  name: string; coord: [string, number]; transactionDate: string; side: 'BUY' | 'SELL';
  eventIds: string[]; eventCount: number; symbol: string; symbolSize: number;
  itemStyle: { color: string; borderColor: string; borderWidth: number };
};
type ChartModel = {
  rows: Observation[]; start: string | null; end: string | null; days: number;
  markers: TransactionMarker[]; unmarkedEvents: number; buys: number; sales: number;
  basis: number | null; basisLabel: string; basisDetail: string;
};

const dayMs = 86_400_000;
const colors = { price: '#5eead4', volume: '#477f94', market: '#38bdf8', sector: '#c4b5fd', buy: '#5eead4', sell: '#fb7185', basis: '#fbbf24', muted: '#a8b6c5' };
const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
const compactUsd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 1 });
const compactShares = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 });
const shares = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const rs = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });

function finite(value: unknown): value is number { return typeof value === 'number' && Number.isFinite(value); }
function dateOnly(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value))
    && new Date(value).toISOString().slice(0, 10) === value;
}
function availableAt(event: EconomicEvent, at: number, end: string): boolean {
  const known = Date.parse(event.knownAt);
  const accepted = Date.parse(event.acceptedAt);
  return Number.isFinite(known) && Number.isFinite(accepted) && known <= at && accepted <= at
    && dateOnly(event.transactionDate) && event.transactionDate <= end;
}

function buildModel({ data, company, period }: CompanyChartProps): ChartModel {
  const days = ['30', '90', '180', '365'].includes(period) ? Number(period) : 180;
  const at = Date.parse(data.research?.asOf ?? data.generatedAt);
  const end = Number.isFinite(at) ? new Date(at).toISOString().slice(0, 10) : null;
  const start = end ? new Date(Date.parse(end) - (days - 1) * dayMs).toISOString().slice(0, 10) : null;
  const rowsByDate = new Map<string, Observation>();
  const sourceRows = data.research
    ? data.research.companySeries.filter((row) => company.issuerCik && row.issuerCik === company.issuerCik)
    : data.companySeries.filter((row) => row.ticker === company.ticker).map((row) => ({ ...row, marketRs: row.mansfield, sectorRs: row.sectorMansfield }));
  for (const row of sourceRows) {
    if (!start || !end || !dateOnly(row.date) || row.date < start || row.date > end || rowsByDate.has(row.date)) continue;
    rowsByDate.set(row.date, {
      date: row.date, price: finite(row.price) && row.price > 0 ? row.price : null,
      volume: finite(row.volume) && row.volume >= 0 ? row.volume : null,
      marketRs: finite(row.marketRs) ? row.marketRs : null, sectorRs: finite(row.sectorRs) ? row.sectorRs : null,
    });
  }
  const rows = [...rowsByDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  const markersByDay = new Map<string, TransactionMarker>();
  const seenEvents = new Set<string>();
  let unmarkedEvents = 0;
  let buys = 0;
  let sales = 0;
  let unresolved = false;
  for (const event of data.research?.economicTransactions ?? []) {
    if (!end || !start || event.issuerCik !== company.issuerCik || !availableAt(event, at, end)) continue;
    if (event.processing === 'UNRESOLVED_AMENDMENT') unresolved = true;
    if (!event.eventId || seenEvents.has(event.eventId)) continue;
    seenEvents.add(event.eventId);
    if (!event.aggregateEligible || event.processing !== 'EFFECTIVE' || !['BUY', 'SELL'].includes(event.side)
      || event.transactionDate < start) continue;
    const price = rowsByDate.get(event.transactionDate)?.price;
    if (price == null) { unmarkedEvents += 1; continue; }
    const side = event.side as 'BUY' | 'SELL';
    if (side === 'BUY') buys += 1; else sales += 1;
    // A joint-owner row is one event. Coincident events share a dated marker with an explicit count.
    const key = `${event.transactionDate}:${side}`;
    const existing = markersByDay.get(key);
    if (existing) {
      existing.eventIds.push(event.eventId); existing.eventCount += 1;
      existing.name = `${side} ×${existing.eventCount}`;
    } else markersByDay.set(key, {
      name: side, coord: [event.transactionDate, price], transactionDate: event.transactionDate, side,
      eventIds: [event.eventId], eventCount: 1, symbol: side === 'BUY' ? 'triangle' : 'diamond', symbolSize: 11,
      itemStyle: { color: side === 'BUY' ? colors.buy : colors.sell, borderColor: '#0b1420', borderWidth: 1 },
    });
  }
  const issuer = data.research?.companies.find((row) => row.issuerCik === company.issuerCik);
  const window = issuer?.basis.find((row) => row.days === 90);
  const blocked = Boolean(data.research && (!issuer || issuer.identityStatus !== 'RESOLVED' || issuer.insiderStatus !== 'AVAILABLE'
    || issuer.basis.some((row) => row.coverage === 'BLOCKED') || unresolved
    || data.research.coverage.unresolvedAmendmentIssuers.includes(company.issuerCik)));
  const basisValue = data.research ? window?.weightedBasis : company.insiderCost;
  const windowDated = !data.research || Boolean(end && window && dateOnly(window.start) && dateOnly(window.end)
    && window.start <= window.end && window.end <= end);
  const basis = end && !blocked && windowDated && finite(basisValue) && basisValue > 0 ? basisValue : null;
  const basisLabel = data.research ? 'Snapshot observed 90D purchase basis' : 'Snapshot observed purchase basis (90D target)';
  const basisDetail = blocked ? 'Observed purchase basis withheld: issuer facts or the exported insider window are blocked.'
    : basis == null ? 'Observed purchase basis unavailable in this snapshot.'
    : `${basisLabel}: ${usd.format(basis)} (${data.research ? window?.coverage === 'PARTIAL' ? 'partial SEC window' : 'observed complete SEC window' : 'window completeness unknown in v1'}). One reference at snapshot time, not a historical basis series.`;
  return { rows, start, end, days, markers: [...markersByDay.values()].sort((a, b) => a.transactionDate.localeCompare(b.transactionDate) || a.side.localeCompare(b.side)), unmarkedEvents, buys, sales, basis, basisLabel, basisDetail };
}

function chartOption(model: ChartModel) {
  const dates = model.rows.map((row) => row.date);
  const axisStyle = { color: colors.muted, fontSize: 10, hideOverlap: true };
  const grid = [
    { left: 65, right: 18, top: 76, bottom: '53%' },
    { left: 65, right: 18, top: '57%', bottom: '30%' },
    { left: 65, right: 18, top: '77%', bottom: 45 },
  ];
  return {
    animation: false,
    backgroundColor: 'transparent', textStyle: { color: '#cbd5e1', fontFamily: 'Segoe UI, sans-serif' },
    tooltip: { trigger: 'axis', confine: true, backgroundColor: '#111d2b', borderColor: '#334155', textStyle: { color: '#e2e8f0' }, axisPointer: { type: 'line', label: { show: false } } },
    axisPointer: { link: [{ xAxisIndex: 'all' }], label: { show: false } },
    legend: { top: 8, bottom: 'auto', left: 'center', type: 'scroll', itemWidth: 16, itemHeight: 8, itemGap: 14, textStyle: { color: colors.muted, fontSize: 11 }, data: ['Observed close', 'Volume', 'Mansfield market RS', 'Mansfield sector RS'] },
    grid,
    xAxis: [0, 1, 2].map((gridIndex) => ({
      type: 'category', gridIndex, data: dates, boundaryGap: true,
      axisLabel: { ...axisStyle, show: gridIndex === 2, formatter: (date: string) => `${date.slice(5, 7)}/${date.slice(8, 10)}`, margin: 12 },
      axisTick: { show: gridIndex === 2, alignWithLabel: true }, axisLine: { lineStyle: { color: '#334155' } },
      axisPointer: { label: { show: false } },
    })),
    yAxis: [
      { type: 'value', gridIndex: 0, name: 'USD', scale: true, nameGap: 12, nameTextStyle: { ...axisStyle, align: 'left' }, axisLabel: { ...axisStyle, formatter: (value: number) => compactUsd.format(value) }, splitLine: { lineStyle: { color: '#263446' } } },
      { type: 'value', gridIndex: 1, name: 'Shares', min: 0, splitNumber: 2, nameGap: 12, nameTextStyle: { ...axisStyle, align: 'left' }, axisLabel: { ...axisStyle, formatter: (value: number) => compactShares.format(value) }, splitLine: { lineStyle: { color: '#263446' } } },
      { type: 'value', gridIndex: 2, name: 'Mansfield RS', scale: true, splitNumber: 3, nameGap: 12, nameTextStyle: { ...axisStyle, align: 'left' }, axisLabel: { ...axisStyle, formatter: (value: number) => rs.format(value) }, splitLine: { lineStyle: { color: '#263446' } } },
    ],
    series: [
      {
        name: 'Observed close', type: 'line', xAxisIndex: 0, yAxisIndex: 0, showSymbol: model.rows.filter((row) => row.price != null).length === 1,
        symbolSize: 6, connectNulls: false, data: model.rows.map((row) => row.price), itemStyle: { color: colors.price }, lineStyle: { width: 2 },
        tooltip: { valueFormatter: (value: unknown) => finite(value) ? usd.format(value) : 'Unavailable' },
        markPoint: { label: { show: false }, data: model.markers, tooltip: { formatter: (params: { data: TransactionMarker }) => `${params.data.name} · ${params.data.transactionDate}<br/>Observed close: ${usd.format(params.data.coord[1])}<br/>${params.data.eventCount} eligible economic event${params.data.eventCount === 1 ? '' : 's'}` } },
        markLine: model.basis == null || !model.rows.some((row) => row.price != null) ? undefined : {
          symbol: 'none', silent: true,
          label: { show: true, formatter: `Observed 90D basis · ${usd.format(model.basis)}`, position: 'insideEndTop', color: colors.basis, fontSize: 10, backgroundColor: '#111d2be6', padding: [3, 4] },
          lineStyle: { color: colors.basis, type: 'dashed', width: 1 }, data: [{ name: model.basisLabel, yAxis: model.basis }],
        },
      },
      { name: 'Volume', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, barMaxWidth: 12, data: model.rows.map((row) => row.volume), itemStyle: { color: colors.volume }, tooltip: { valueFormatter: (value: unknown) => finite(value) ? `${shares.format(value)} shares` : 'Unavailable' } },
      { name: 'Mansfield market RS', type: 'line', xAxisIndex: 2, yAxisIndex: 2, showSymbol: true, symbol: 'circle', symbolSize: 4, connectNulls: true, data: model.rows.map((row) => row.marketRs), itemStyle: { color: colors.market }, lineStyle: { width: 1.5 }, tooltip: { valueFormatter: (value: unknown) => finite(value) ? rs.format(value) : 'Unavailable' } },
      { name: 'Mansfield sector RS', type: 'line', xAxisIndex: 2, yAxisIndex: 2, showSymbol: true, symbol: 'circle', symbolSize: 4, connectNulls: true, data: model.rows.map((row) => row.sectorRs), itemStyle: { color: colors.sector }, lineStyle: { width: 1.5, type: 'dashed' }, tooltip: { valueFormatter: (value: unknown) => finite(value) ? rs.format(value) : 'Unavailable' } },
    ],
    media: [{ query: { maxWidth: 600 }, option: {
      legend: { top: 8, bottom: 'auto', itemGap: 10, textStyle: { fontSize: 10 } },
      grid: grid.map((row) => ({ ...row, left: 56, right: 12 })),
    } }],
  };
}

/** Only observed rows and events available by the snapshot enter this option. */
export function buildCompanyChartOption(props: CompanyChartProps) { return chartOption(buildModel(props)); }

export function CompanyChart({ data, company, period }: CompanyChartProps) {
  const descriptionId = useId();
  const model = useMemo(() => buildModel({ data, company, period }), [data, company, period]);
  const option = useMemo(() => chartOption(model), [model]);
  const prices = model.rows.filter((row) => row.price != null);
  const volumeCount = model.rows.filter((row) => row.volume != null).length;
  const marketCount = model.rows.filter((row) => row.marketRs != null).length;
  const sectorCount = model.rows.filter((row) => row.sectorRs != null).length;
  const latest = prices.at(-1);
  const hasObservations = prices.length > 0 || volumeCount > 0 || marketCount > 0 || sectorCount > 0;
  return <figure className="min-w-0" data-testid="company-chart" aria-label={`${company.ticker} observed price, volume and relative strength`} aria-describedby={descriptionId}>
    <figcaption id={descriptionId} className="space-y-2 text-xs leading-5 text-muted-foreground">
      <p data-testid="company-chart-window">{model.start && model.end ? `${model.days} calendar days · ${model.start}–${model.end} · snapshot UTC` : 'Snapshot time unavailable; chart observations cannot be established.'}</p>
      <div className="grid gap-2 sm:grid-cols-3">
        <p><span className="block font-medium text-foreground">Observed close · USD</span>{latest ? `${usd.format(latest.price!)} on ${latest.date} · ${prices.length} observed closes` : 'Price series unavailable for this period.'}</p>
        <p><span className="block font-medium text-foreground">Trading volume · shares</span>{volumeCount ? `${volumeCount} observed volumes` : 'Volume unavailable for this period.'}</p>
        <p><span className="block font-medium text-foreground">Mansfield relative strength</span>Market: {marketCount ? `${marketCount} observations` : 'unavailable'} · Sector: {sectorCount ? `${sectorCount} observations` : 'unavailable'}</p>
      </div>
    </figcaption>
    {hasObservations ? <div aria-hidden="true" className="mt-2"><EChart option={option} style={{ height: 'clamp(440px, 65vw, 540px)', width: '100%' }} /></div>
      : <output className="my-4 block rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">No dated price, volume or relative-strength observations are exported for this company in the selected period.</output>}
    <div className="mt-3 space-y-2 text-xs leading-5 text-muted-foreground">
      <p data-testid="company-chart-markers">{data.research ? `▲ BUY: ${model.buys} · ◆ SELL: ${model.sales} eligible economic events marked at the observed close on the transaction date, not the execution price. Coincident events share a marker with a count; reporting owners do not multiply events.${model.unmarkedEvents ? ` ${model.unmarkedEvents} eligible event${model.unmarkedEvents === 1 ? '' : 's'} in this period lack an observed close and have no marker.` : ''}` : 'Precise economic transaction markers are unavailable in v1.'}</p>
      <p>Price is the exported provider close (adjusted where supplied); this company-series contract does not prove uniform split/dividend adjustment.</p>
      <p>RS lines connect available weekly observations; missing values are not zero or forward filled. Price, volume and RS use separate scales. Dates share the bottom axis.</p>
      <p data-testid="company-chart-basis" className={model.basis == null ? '' : 'text-amber-200'}>{model.basisDetail}</p>
    </div>
  </figure>;
}
