import { useMemo } from 'react';
import type { ResearchSnapshot } from '@/lib/research-v2';
import { buildInsiderBarometer, type RatioPoint } from '@/lib/insider-barometer';
import { controlClass, metric, money } from '@/lib/research';
import { isBoolean, isString, usePreference } from '@/lib/local-preferences';
import { EChart } from './echart';

const RESEARCH_URL = 'https://www.gurufocus.com/news/99283/guru-insider-research-ii-can-aggregated-insider-trading-activities-predict-the-market';
const REFERENCE_URL = 'https://www.gurufocus.com/economic_indicators/4359/insider-buysell-ratio-usa-overall-market';
const SEC_CODES_URL = 'https://www.sec.gov/files/form4.pdf';
const times = (value: number | null) => value == null ? '—' : `${metric(value, 2)}×`;
const ratioTicks = new Intl.NumberFormat('en-US', { maximumSignificantDigits: 3 });

export function buildBarometerChartOption(points: RatioPoint[], monthly: boolean, reference: boolean) {
  const hasSpy = points.some((row) => row.spy != null);
  const hasMean = points.some((row) => row.mean3m != null);
  return {
    textStyle: { color: '#cbd5e1' },
    legend: { top: 0, type: 'scroll', textStyle: { color: '#cbd5e1' }, data: ['Buy / sell event ratio', ...(hasMean ? ['3-month mean ratio'] : []), ...(hasSpy ? ['SPY close'] : [])] },
    tooltip: { trigger: 'axis', confine: true, backgroundColor: '#111d2b', borderColor: '#334155', textStyle: { color: '#e2e8f0' }, formatter: (params: unknown) => {
      const list = Array.isArray(params) ? params : [params];
      const index = Number((list[0] as { dataIndex?: number } | undefined)?.dataIndex ?? -1);
      const row = points[index];
      if (!row) return '';
      return `${row.start} – ${row.end}${row.partial ? ' · partial SEC window' : ''}<br/>Buy events: ${row.buys.toLocaleString('en-US')}<br/>Sale events: ${row.sales.toLocaleString('en-US')}<br/>Buy / sell: ${row.ratio == null ? '— (no sale denominator)' : times(row.ratio)}<br/>3-month mean: ${times(row.mean3m)}<br/>SPY: ${money(row.spy)}${row.spyDate ? ` · ${row.spyDate}` : ''}`;
    } },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: hasSpy ? [{ left: 58, right: 20, top: 58, height: '42%' }, { left: 58, right: 20, top: '68%', bottom: 52 }]
      : [{ left: 58, right: 20, top: 46, bottom: 52 }],
    xAxis: (hasSpy ? [0, 1] : [0]).map((index) => ({ type: 'category', gridIndex: index,
      data: points.map((row) => `${row.label}${row.partial ? ' *' : ''}`),
      axisLabel: { show: !hasSpy || index === 1, hideOverlap: true, color: '#94a3b8', formatter: (label: string) => monthly ? label : label.slice(5) } })),
    yAxis: [{ type: 'value', min: 0, gridIndex: 0, name: 'Buy / sell',
      axisLabel: { color: '#94a3b8', formatter: (value: number) => `${ratioTicks.format(value)}×` },
      splitLine: { lineStyle: { color: '#263446' } } }, ...(hasSpy ? [
    { type: 'value', scale: true, gridIndex: 1, name: 'SPY · USD',
      axisLabel: { color: '#94a3b8', formatter: (value: number) => metric(value, 0) },
      splitLine: { lineStyle: { color: '#263446' } } }] : [])],
    series: [{ type: monthly ? 'bar' : 'line', name: 'Buy / sell event ratio', xAxisIndex: 0, yAxisIndex: 0,
      data: points.map((row) => row.ratio), connectNulls: false, showSymbol: true, smooth: false,
      itemStyle: { color: '#34d399' }, lineStyle: { color: '#34d399', width: 2 },
      markLine: reference ? { silent: true, symbol: 'none', label: { show: false }, data: [{ yAxis: 0.39,
        lineStyle: { color: '#a78bfa', type: 'dashed' } }] } : undefined },
    { type: 'line', name: '3-month mean ratio', xAxisIndex: 0, yAxisIndex: 0,
      data: points.map((row) => row.mean3m), connectNulls: false, showSymbol: true,
      itemStyle: { color: '#fbbf24' }, lineStyle: { color: '#fbbf24', type: 'dashed' } }, ...(hasSpy ? [
    { type: 'line', name: 'SPY close', xAxisIndex: 1, yAxisIndex: 1,
      data: points.map((row) => row.spy), connectNulls: false, showSymbol: true, smooth: false,
      itemStyle: { color: '#60a5fa' }, lineStyle: { color: '#60a5fa', width: 2 } }] : [])],
  };
}

export function InsiderRatioV2({ data }: { data: ResearchSnapshot }) {
  const [sector, setSector] = usePreference('insider-ratio.sector', 'All sectors', isString);
  const [savedMode, setMode] = usePreference('insider-ratio.mode', 'monthly', isString);
  const [reference, setReference] = usePreference('insider-ratio.reference', false, isBoolean);
  const result = useMemo(() => buildInsiderBarometer(data, sector), [data, sector]);
  const monthly = savedMode !== 'rolling';
  const points = monthly ? result.monthly : result.rolling;
  const showReference = reference && monthly && sector === 'All sectors';
  const option = useMemo(() => buildBarometerChartOption(points, monthly, showReference), [points, monthly, showReference]);
  const current = result.current;
  const activity = current?.ratio == null ? 'No sale denominator'
    : current.buys > current.sales ? 'More purchase events' : current.buys < current.sales ? 'More sale events' : 'Equal event counts';
  return <div className="space-y-5">
    {result.latestExpectedDay && result.latestExpectedDay !== result.latestDay && <output className="block rounded-lg border border-amber-300/20 p-3 text-xs text-amber-200">Newest inventoried SEC day {result.latestExpectedDay} is incomplete. The barometer is held at {result.latestDay ?? 'no complete day'}; newer partial data is not substituted.</output>}
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[
      ['Current rolling 30D ratio', times(current?.ratio ?? null), activity, 'insider-ratio-current'],
      ['Observed events · 30D', current ? `${current.buys.toLocaleString('en-US')} buys / ${current.sales.toLocaleString('en-US')} sales` : '—', current?.partial ? 'Partial SEC window' : 'SEC window covered; late filings may revise it', undefined],
      ['Latest complete SEC day', result.latestDay ?? 'Unavailable', 'Daily refreshed · no artificial delay · not intraday', undefined],
      ['SPY price change · observed window', result.spyChangePct == null ? '—' : `${result.spyChangePct > 0 ? '+' : ''}${metric(result.spyChangePct, 1)}%`, result.spyStart && result.spyEnd ? `${result.spyStart} – ${result.spyEnd}` : 'Actual benchmark observations required', undefined],
    ].map(([label, value, detail, testId]) => <article key={label} className="rounded-xl border border-border bg-card p-4"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-3 font-mono text-lg" data-testid={testId}>{value}</p><p className="mt-2 text-xs text-muted-foreground">{detail}</p></article>)}</div>
    <section className="rounded-xl border border-border bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-base font-semibold">Insider activity & SPY</h2><p className="mt-1 text-xs text-muted-foreground">Purchase events ÷ sale events · independent ratio and price scales</p></div><div className="flex flex-wrap gap-2"><select aria-label="Ratio sector" className={controlClass} value={sector} onChange={(event) => setSector(event.target.value)}><option>All sectors</option>{result.sectors.map((value) => <option key={value}>{value}</option>)}</select><button aria-pressed={!monthly} className={controlClass} onClick={() => setMode('rolling')}>Daily rolling 30D</button><button aria-pressed={monthly} className={controlClass} onClick={() => setMode('monthly')}>Calendar months</button></div></div>
      <p className="my-3 text-xs leading-6 text-muted-foreground">{monthly ? 'Calendar months intersecting the last 90 days, using full-month transaction dates where available and filings known at this snapshot. * marks partial coverage or an unfinished month. The 3-month mean needs three fully covered calendar months.' : 'Each point uses the preceding 30 calendar days. Earlier points use knowledge available by that New York SEC day; the latest point includes later imports known at this snapshot. * marks a partial SEC window.'}</p>
      {monthly && sector === 'All sectors' && <label className="mb-3 flex items-center gap-2 text-xs text-violet-200"><input type="checkbox" checked={reference} onChange={(event) => setReference(event.target.checked)} />Show GuruFocus published mean: 0.39× — external reference, different population</label>}
      {!points.length ? <p className="py-8 text-sm text-muted-foreground">No complete SEC-day history is available for this selection.</p> : <div aria-label="Insider event ratio and same-period SPY chart"><EChart style={{ height: points.some((row) => row.spy != null) ? 440 : 300 }} option={option} /></div>}
      {result.spyReason ? <p className="mt-3 text-xs text-amber-200" data-testid="barometer-spy-status">{result.spyReason} The insider ratio remains available.</p> : <p className="mt-3 text-xs text-muted-foreground" data-testid="barometer-spy-status">SPY: {result.spyProviders.join(', ')} · {result.spyBasis}. Each point shows the last available close inside the same window; no extrapolation or total-return claim.</p>}
      <p className="mt-3 text-xs text-muted-foreground" data-testid="insider-ratio-zone">Historical percentile / z-score unavailable: comparable long-history data is not established. No calibrated market-top or market-bottom signal.</p>
    </section>
    <details className="rounded-xl border border-border bg-card p-5 text-sm leading-6 text-muted-foreground"><summary className="cursor-pointer font-semibold text-foreground">Research context & calculation</summary>
      <p className="mt-3">Each economic event is counted once, including joint reporting owners. Effective qualified non-derivative P/S events enter only for resolved eligible companies. Unresolved amendments are excluded. A missing sale denominator is <strong className="text-foreground">—</strong>, not zero or infinity.</p>
      <p className="mt-3" data-testid="insider-ratio-transaction-scope"><a href={SEC_CODES_URL} target="_blank" rel="noreferrer" className="text-emerald-200 underline">SEC Form 4 transaction codes</a> P and S can include exchange trades or private transactions. The code alone does not prove execution at a market price; this export does not separately verify that distinction. GuruFocus’s study excluded private placements at non-market prices, another reason its thresholds are not directly transferable.</p>
      <p className="mt-3">Historical SEC-day availability ends at midnight in America/New_York, including US-evening filings recorded after UTC midnight. The current reading and calendar months include imports known at the snapshot as-of instant, even if ingestion occurred after the latest complete SEC day. Earlier rolling readings never use that later knowledge.</p>
      <p className="mt-3">GuruFocus’s <a href={RESEARCH_URL} target="_blank" rel="noreferrer" className="text-emerald-200 underline">2010 public study</a> examined monthly open-market transaction counts from 2004, principally CEO examples. Buying increased during the 2008–09 decline. This supports viewing insider activity alongside prices, but does not establish a universal threshold or prove that a low ratio predicts a top. Our chart includes all reporting-owner roles and our observed eligible population.</p>
      <p className="mt-3">Its <a href={REFERENCE_URL} target="_blank" rel="noreferrer" className="text-emerald-200 underline">public overall-market indicator</a> listed a long-term mean of 0.39× when reviewed on 4 October 2026. This is a documented external reference, not our historical mean or a trading threshold. Cohort, security filtering and history are not demonstrated identical, so we do not copy buy/sell cutoffs or derive a z-score from that mean.</p>
      <p className="mt-3">{data.coverage.scope}. {result.missingLineage ? `${result.missingLineage.toLocaleString('en-US')} otherwise eligible events lack SEC-day lineage and are excluded from history. ` : ''}Calendar-month history can change with late filings or repairs; rolling history is reconstructed from availability, not an archived real-time market census.</p>
    </details>
  </div>;
}
