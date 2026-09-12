import { useState } from 'react';
import { Star, ExternalLink } from 'lucide-react';
import type { Candidate, DashboardData, Filing } from '@/lib/dashboard-data';
import type { PublicationManifest } from '@/lib/operations-data';
import { controlClass, costReturn, downloadCsv, instant, metric, money, observedContext, reasonText, secUrl, timestamp } from '@/lib/research';
import { isBoolean, isString, usePreference } from '@/lib/local-preferences';
import { SortControls, useRowSort, type SortField } from './sort-controls';
import { EChart } from './echart';
import { ClustersV2 } from './v2-views';

type ResearchProps = {
  data: DashboardData; catalog: Candidate[]; watchlist: string[]; timezone: string;
  toggleWatch: (cik: string) => void; openCompany: (ticker: string) => void;
};
const candidateFields: SortField<Candidate>[] = [
  ...(['total', 'insider', 'divergence', 'turn', 'cluster', 'marketRs'] as const).map((id) => ({ id, label: { total: 'Total', insider: 'Insider', divergence: 'Divergence', turn: 'Turn', cluster: 'Cluster', marketRs: 'Market RS' }[id], value: (row: Candidate) => row[id] })),
  { id: 'costPl', label: 'Price vs observed basis', value: costReturn },
  { id: 'ticker', label: 'Ticker', value: (row) => row.ticker },
  { id: 'state', label: 'State', value: (row) => row.state },
];
const filingFields: SortField<Filing>[] = [
  { id: 'value', label: 'Value', value: (row) => row.value },
  { id: 'filedAt', label: 'Accepted', value: (row) => timestamp(row.filedAt) },
  ...(['ticker', 'owner', 'role', 'side', 'accession'] as const).map((id) => ({ id, label: { ticker: 'Ticker', owner: 'Reporting owner', role: 'Role', side: 'Side', accession: 'Accession' }[id], value: (row: Filing) => row[id] })),
];
const turningStates = ['INSIDER_ACCUMULATION', 'BASE_FORMING', 'EARLY_TURN', 'CONFIRMED_TURN'];

export function CompanyTable({ data, catalog, watchlist, toggleWatch, openCompany, mode }: ResearchProps & { mode: 'radar' | 'turning' | 'divergence' }) {
  const [search, setSearch] = usePreference(`${mode}.search`, '', isString);
  const [sector, setSector] = usePreference(`${mode}.sector`, '', isString);
  const [availability, setAvailability] = usePreference(`${mode}.availability`, '', isString);
  const [watched, setWatched] = usePreference(`${mode}.watchOnly`, false, isBoolean);
  const [insiderMin, setInsiderMin] = usePreference(`${mode}.insiderMin`, '65', isString);
  const [divergenceMin, setDivergenceMin] = usePreference(`${mode}.divergenceMin`, '65', isString);
  const [phase, setPhase] = usePreference(`${mode}.phase`, '', isString);
  const rows = catalog.filter((row) => {
    if (!`${row.ticker} ${row.company} ${row.issuerCik}`.toLowerCase().includes(search.toLowerCase())) return false;
    if (sector && row.sector !== sector || watched && !watchlist.includes(row.issuerCik)) return false;
    if (availability === 'complete' && row.total == null || availability === 'missing' && row.total != null) return false;
    if (mode === 'turning' && (!turningStates.includes(row.state) || phase && row.state !== phase)) return false;
    return mode !== 'divergence' || row.insider != null && row.divergence != null && row.insider >= Number(insiderMin) && row.divergence >= Number(divergenceMin);
  });
  const sort = useRowSort(rows, candidateFields, mode === 'radar' ? 'total' : mode === 'turning' ? 'turn' : 'divergence', mode);
  const rank = new Map(catalog.filter((row) => row.total != null).map((row, index) => [row.ticker, index + 1]));
  return <Panel title={mode === 'turning' ? 'Recorded turning phases' : mode === 'divergence' ? 'Divergence screen' : 'Company explorer'} subtitle={`${rows.length} of ${catalog.length} exported companies · ranking uses the unchanged snapshot score`}>
    <div className="mb-4 flex flex-wrap gap-3">
      <input aria-label="Ticker or company" placeholder="Ticker, company or CIK" className={`${controlClass} min-w-0 flex-1`} value={search} onChange={(event) => setSearch(event.target.value)} />
      <select aria-label="Sector" className={controlClass} value={sector} onChange={(event) => setSector(event.target.value)}><option value="">All sectors</option>{[...new Set(catalog.map((row) => row.sector))].sort().map((name) => <option key={name}>{name}</option>)}</select>
      <select aria-label="Data availability" className={controlClass} value={availability} onChange={(event) => setAvailability(event.target.value)}><option value="">All data availability</option><option value="complete">Complete score</option><option value="missing">Score unavailable</option></select>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={watched} onChange={(event) => setWatched(event.target.checked)} />Watchlist only</label>
    </div>
    {mode === 'divergence' && <div className="mb-4 flex flex-wrap gap-4">{[['Minimum Insider', insiderMin, setInsiderMin], ['Minimum Divergence', divergenceMin, setDivergenceMin]].map(([label, value, setter]) => <label key={String(label)} className="text-xs">{String(label)}<input aria-label={String(label)} className={`${controlClass} ml-2 w-20`} type="number" min="0" max="100" value={String(value)} onChange={(event) => (setter as (v: string) => void)(event.target.value)} /></label>)}</div>}
    {mode === 'turning' && <div className="mb-4 flex flex-wrap gap-2"><button className={controlClass} onClick={() => setPhase('')}>All phases</button>{turningStates.map((state) => <button key={state} className={`${controlClass} ${phase === state ? 'text-emerald-200' : ''}`} onClick={() => setPhase(state)}>{reasonText(state)} ({catalog.filter((row) => row.state === state).length})</button>)}</div>}
    <div className="flex flex-wrap items-start justify-between gap-2"><SortControls fields={candidateFields} fieldId={sort.fieldId} descending={sort.descending} onField={sort.choose} onReverse={sort.reverse} /><button className={controlClass} onClick={() => downloadCsv(`${mode}.csv`, ['Rank', 'CIK', 'Ticker', 'Company', 'Sector', 'Total', 'Insider', 'Divergence', 'Turn', 'State', 'Score snapshot'], sort.rows.map((row) => [rank.get(row.ticker), row.issuerCik, row.ticker, row.company, row.sector, row.total, row.insider, row.divergence, row.turn, row.state, data.generatedAt]))}>Export filtered CSV</button></div>
    {sort.rows.length === 0 ? <EmptyState title="No companies match these filters" detail="Broaden the filters or turn off Watchlist only. Missing data is not a zero score." /> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-3">Watch</th><th className="p-3">Rank</th>{['ticker', 'total', 'insider', 'divergence', 'turn', 'state'].map((id) => <SortHeader key={id} field={candidateFields.find((field) => field.id === id)!} sort={sort} />)}<th className="p-3">Context</th></tr></thead><tbody>{sort.rows.map((row) => <tr key={row.issuerCik || row.ticker} className="border-t border-border hover:bg-accent/40">
      <td className="p-3"><WatchButton row={row} watched={watchlist.includes(row.issuerCik)} toggle={toggleWatch} /></td><td className="p-3 font-mono">{rank.get(row.ticker) ?? '—'}</td>
      <td className="p-3"><button aria-label={`Open ${row.ticker} in Company Lab`} onClick={() => openCompany(row.ticker)} className="text-left"><span className="font-mono font-semibold text-emerald-200">{row.ticker}</span><span className="block max-w-48 truncate text-xs text-muted-foreground" title={row.company}>{row.company}</span></button></td>
      {[row.total, row.insider, row.divergence, row.turn].map((value, index) => <td key={index} className="p-3 font-mono" title={value == null ? 'Required component data is unavailable' : String(value)}>{metric(value)}</td>)}
      <td className="p-3 text-xs"><State state={row.state} />{mode === 'turning' && <p className="mt-2 text-muted-foreground">Changed: {row.stateChangedAt ?? 'not recorded'}</p>}</td>
      <td className="min-w-48 max-w-64 p-3 text-xs leading-5 text-muted-foreground">{reasonText(row.reasons[0] ?? 'No explanation exported')}{mode === 'divergence' && <p>{observedContext(data, row)}</p>}</td>
    </tr>)}</tbody></table></div>}
  </Panel>;
}

export function TapeView({ data, openCompany, timezone, buysOnly = false, ticker }: { data: DashboardData; openCompany: (ticker: string) => void; timezone: string; buysOnly?: boolean; ticker?: string }) {
  const key = ticker ? `company.${ticker}.tape` : buysOnly ? 'buys' : 'tape';
  const [query, setQuery] = usePreference(`${key}.query`, '', isString);
  const [owner, setOwner] = usePreference(`${key}.owner`, '', isString);
  const [side, setSide] = usePreference(`${key}.side`, '', isString);
  const [minimum, setMinimum] = usePreference(`${key}.minimum`, '', isString);
  const [windowDays, setWindowDays] = usePreference(`${key}.days`, 'all', isString);
  const [page, setPage] = useState(0);
  const cutoff = windowDays === 'all' ? -Infinity : timestamp(data.generatedAt) - Number(windowDays) * 86400000;
  const filtered = data.filings.filter((row) => (!ticker || ticker === row.ticker) && (!buysOnly || row.side === 'BUY' && row.qualified !== false) && (!side || row.side === side) && row.ticker.toLowerCase().includes(query.toLowerCase()) && row.owner.toLowerCase().includes(owner.toLowerCase()) && (!minimum || row.value != null && row.value >= Number(minimum)) && timestamp(row.filedAt) >= cutoff);
  const sort = useRowSort(filtered, filingFields, 'value', key);
  const pages = Math.max(1, Math.ceil(sort.rows.length / 25));
  const currentPage = Math.min(page, pages - 1);
  function resetPage(setter: (v: string) => void, value: string) { setter(value); setPage(0); }
  return <Panel title={buysOnly ? 'Qualified insider purchases' : 'SEC activity records'} subtitle={data.research ? 'One economic event per SEC table row, with all reporting owners retained. Unresolved corrections are marked and excluded from issuer aggregates.' : 'Legacy v1 groups rows by filing, reporting owner and side. Values are not independent-event totals; joint-owner duplicates may exist.'}>
    <div className="mb-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <input aria-label="Filter ticker" placeholder="Ticker" className={controlClass} value={query} onChange={(event) => resetPage(setQuery, event.target.value)} />
      <input aria-label="Filter reporting owner" placeholder="Reporting owner" className={controlClass} value={owner} onChange={(event) => resetPage(setOwner, event.target.value)} />
      {!buysOnly && <select aria-label="Transaction side" className={controlClass} value={side} onChange={(event) => resetPage(setSide, event.target.value)}><option value="">BUY and SELL</option><option>BUY</option><option>SELL</option></select>}
      <input aria-label="Minimum USD value" placeholder="Min USD value" type="number" min="0" className={controlClass} value={minimum} onChange={(event) => resetPage(setMinimum, event.target.value)} />
      <select aria-label="Acceptance date window" className={controlClass} value={windowDays} onChange={(event) => resetPage(setWindowDays, event.target.value)}><option value="all">All exported dates</option>{[7, 30, 90].map((days) => <option key={days} value={days}>Last {days} days</option>)}</select>
    </div>
    <p className="mb-4 text-xs text-muted-foreground">Date filter uses filing acceptance relative to the snapshot, not transaction date; it does not recalculate scores. Times: {timezone}.</p>
    <div className="flex flex-wrap justify-between gap-2"><SortControls fields={filingFields} fieldId={sort.fieldId} descending={sort.descending} onField={(id) => { sort.choose(id); setPage(0); }} onReverse={sort.reverse} /><button className={controlClass} onClick={() => downloadCsv(buysOnly ? 'insider-buys.csv' : 'sec-tape.csv', ['Ticker', data.research ? 'Value USD' : 'Value USD (grouped)', 'Side', 'Reporting owner', 'Role', 'Accepted', 'Accession', 'SEC URL', 'Transaction date', 'Shares', 'Price', '10b5-1', 'Processing'], sort.rows.map((row) => [row.ticker, row.value, row.side, row.owner, row.role, row.filedAt, row.accession, secUrl(row), row.transactionDate, row.shares, row.price, row.rule10b51, row.processing]))}>Export filtered CSV</button></div>
    {sort.rows.length === 0 ? <EmptyState title="No records match these filters" detail="This is not evidence that no transactions occurred outside the exported SEC window." /> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{['ticker', 'value', 'side', 'owner', 'role', 'filedAt'].map((id) => <SortHeader key={id} field={filingFields.find((field) => field.id === id)!} sort={sort} />)}<th className="p-3">Source & details</th></tr></thead><tbody>{sort.rows.slice(currentPage * 25, (currentPage + 1) * 25).map((row, index) => <tr key={`${row.accession}:${row.owner}:${row.side}:${index}`} className="border-t border-border">
      <td className="p-3"><button onClick={() => openCompany(row.ticker)} className="font-mono font-semibold text-emerald-200">{row.ticker}</button></td>
      <td className="whitespace-nowrap p-3 font-mono" data-value={row.value} title={money(row.value)}>{money(row.value, true)}</td><td className={`p-3 text-xs ${row.side === 'BUY' ? 'text-emerald-300' : 'text-rose-300'}`}>{row.side}</td><td className="min-w-44 p-3">{row.owner}</td><td className="p-3 text-xs text-muted-foreground">{row.role || 'Unknown'}</td>
      <td className="whitespace-nowrap p-3 text-xs" data-timestamp={timestamp(row.filedAt)}>{instant(row.filedAt, timezone)}</td><td className="min-w-60 p-3 text-xs"><SecLink row={row} />{row.processing === 'UNRESOLVED_AMENDMENT' && <p className="mt-2 text-amber-200">Unresolved amendment — excluded from aggregates</p>}<details className="mt-2"><summary>Record details</summary><dl className="mt-2 space-y-2 text-muted-foreground"><dt>Accession</dt><dd className="font-mono">{row.accession}</dd><dt>{data.research ? 'Exact economic amount' : 'Exact grouped amount'}</dt><dd>{money(row.value)}</dd>{data.research ? <><dt>Transaction date</dt><dd>{row.transactionDate}</dd><dt>Shares × reported price</dt><dd>{metric(row.shares, 6)} × {money(row.price)}</dd><dt>10b5-1 status</dt><dd>{row.rule10b51 ?? 'unknown'}</dd><dt>Processing</dt><dd>{row.processing}</dd></> : <><dt>Transaction date, shares, price, 10b5-1 and amendment processing</dt><dd>Not exported in v1. Inspect the linked SEC document; unknown is not false.</dd></>}</dl></details></td>
    </tr>)}</tbody></table></div>}
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground"><span>{filtered.length} matching records · page {currentPage + 1} of {pages}</span><div className="flex gap-2"><button className={controlClass} disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button><button className={controlClass} disabled={currentPage + 1 >= pages} onClick={() => setPage(currentPage + 1)}>Next</button></div></div>
  </Panel>;
}

export function PulseView({ data }: { data: DashboardData }) {
  const days = new Map<string, { buys: number; sales: number; filings: Set<string> }>();
  for (const row of data.filings) {
    const day = new Date(timestamp(row.filedAt)).toISOString().slice(0, 10);
    const current = days.get(day) ?? { buys: 0, sales: 0, filings: new Set<string>() };
    current[row.side === 'BUY' ? 'buys' : 'sales']++; current.filings.add(row.accession); days.set(day, current);
  }
  return <>
    <Panel title="Observed SEC activity" subtitle="Legacy export is selected from purchase-active issuers; it cannot measure market-wide buying versus selling.">
      <div className="mb-5 grid gap-3 sm:grid-cols-3"><Fact label="Distinct accessions" value={String(new Set(data.filings.map((row) => row.accession)).size)} /><Fact label="Companies in exported tape" value={String(new Set(data.filings.map((row) => row.ticker)).size)} /><Fact label="Owner CIK coverage" value="Not exported in v1" /></div>
      <p className="mb-4 text-sm leading-6 text-muted-foreground">Dollar totals and independent-insider counts are withheld until economic-event IDs and owner links are available. Grouped owner records can repeat the same purchase.</p>
      {days.size === 0 ? <EmptyState title="No activity records exported" detail="Source coverage is unavailable; this is not a zero-activity market." /> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{['Acceptance day (UTC)', 'BUY owner records', 'SELL owner records', 'Distinct accessions'].map((label) => <th className="p-3" key={label}>{label}</th>)}</tr></thead><tbody>{[...days].sort(([a], [b]) => b.localeCompare(a)).map(([day, row]) => <tr key={day} className="border-t border-border"><td className="p-3">{day}</td><td className="p-3">{row.buys}</td><td className="p-3">{row.sales}</td><td className="p-3">{row.filings.size}</td></tr>)}</tbody></table></div>}
    </Panel>
    <Panel title="Research Pulse" subtitle="Secondary point-in-time composite; limited to the supplied population.">{data.marketPulse == null ? <EmptyState title="Insufficient prior history" detail="No percentile is shown. A missing composite is not neutral or zero." /> : <div className="grid gap-3 sm:grid-cols-2"><Fact label="Composite" value={metric(data.marketPulse)} /><Fact label="Historical percentile" value={metric(data.pulsePercentile)} /></div>}</Panel>
  </>;
}

export function ClusterView() {
  return <Panel title="Verified cluster membership" subtitle="At least two distinct reporting-owner CIKs and independent purchases within 30 days are required."><EmptyState title="Member-level evidence not available in this snapshot" detail="The v1 export contains a cluster score but no owner CIKs or economic-event links. No CEO/CFO or independent-buyer labels are inferred from that score. Joint filers of a single purchase do not establish a cluster." /></Panel>;
}

export function CostBasisView({ catalog, openCompany }: { catalog: Candidate[]; openCompany: (ticker: string) => void }) {
  const fields = [...candidateFields.filter((field) => ['costPl', 'ticker'].includes(field.id)), { id: 'insiderCost', label: 'Observed purchase basis', value: (row: Candidate) => row.insiderCost }, { id: 'currentPrice', label: 'Current price', value: (row: Candidate) => row.currentPrice }];
  const sort = useRowSort(catalog, fields, 'costPl', 'basis');
  return <Panel title="Observed weighted purchase basis" subtitle="Legacy basis targets 90 days, but its covered dates, purchase count and window completeness were not exported. Do not treat it as complete 90D holdings.">
    <div className="flex flex-wrap justify-between gap-2"><SortControls fields={fields} fieldId={sort.fieldId} descending={sort.descending} onField={sort.choose} onReverse={sort.reverse} /><button className={controlClass} onClick={() => downloadCsv('observed-basis.csv', ['Ticker', 'Observed basis', 'Current price', 'Price vs basis %', 'Completeness'], sort.rows.map((row) => [row.ticker, row.insiderCost, row.currentPrice, costReturn(row), 'Not verified in v1']))}>Export filtered CSV</button></div>
    <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{['Ticker', '30D basis', 'Observed basis (90D target)', 'Current price', 'Price vs basis', 'Window'].map((label) => <th key={label} className="p-3">{label}</th>)}</tr></thead><tbody>{sort.rows.map((row) => <tr key={row.ticker} className="border-t border-border"><td className="p-3"><button className="font-mono text-emerald-200" onClick={() => openCompany(row.ticker)}>{row.ticker}</button></td><td className="p-3" title="Not exported in v1">—</td><td className="p-3 font-mono">{money(row.insiderCost)}</td><td className="p-3 font-mono">{money(row.currentPrice)}</td><td className="p-3 font-mono">{costReturn(row) == null ? '—' : `${metric(costReturn(row))}%`}</td><td className="p-3 text-xs text-amber-200">Completeness unknown</td></tr>)}</tbody></table></div>
  </Panel>;
}

export function CompanyLab({ data, catalog, company, watchlist, toggleWatch, openCompany, timezone }: ResearchProps & { company: Candidate }) {
  const [query, setQuery] = useState('');
  const [period, setPeriod] = usePreference('lab.period', '180', isString);
  const allSeries = data.companySeries.filter((row) => row.ticker === company.ticker && Number.isFinite(timestamp(row.date)));
  const latest = allSeries.length ? Math.max(...allSeries.map((row) => timestamp(row.date))) : 0;
  const series = allSeries.filter((row) => timestamp(row.date) >= latest - Number(period) * 86400000).sort((a, b) => timestamp(a.date) - timestamp(b.date));
  const rank = catalog.filter((row) => row.total != null).findIndex((row) => row.ticker === company.ticker) + 1;
  const choices = catalog.filter((row) => `${row.ticker} ${row.company}`.toLowerCase().includes(query.toLowerCase()));
  const pricesByDate = new Map(series.map((row) => [row.date, row.price]));
  const markers = (data.research?.economicTransactions ?? []).filter((row) => row.issuerCik === company.issuerCik && row.aggregateEligible && pricesByDate.has(row.transactionDate)).map((row) => ({ name: row.side === 'BUY' ? 'Purchase' : 'Sale', value: money(row.value, true), coord: [row.transactionDate, pricesByDate.get(row.transactionDate)], symbol: row.side === 'BUY' ? 'triangle' : 'diamond', symbolSize: 10, itemStyle: { color: row.side === 'BUY' ? '#5eead4' : '#fb7185' } }));
  const option = {
    backgroundColor: 'transparent', textStyle: { color: '#cbd5e1', fontFamily: 'Segoe UI, sans-serif' },
    tooltip: { trigger: 'axis' }, legend: { textStyle: { color: '#a8b6c5' }, data: ['Adjusted price', 'Mansfield market RS', ...(data.research ? ['Mansfield sector RS'] : [])] },
    grid: { left: 60, right: 55, top: 50, bottom: 45 },
    xAxis: { type: 'category', data: series.map((row) => row.date), axisLabel: { color: '#a8b6c5' } },
    yAxis: [{ type: 'value', scale: true, name: 'USD', splitLine: { lineStyle: { color: '#263446' } } }, { type: 'value', name: 'RS', splitLine: { show: false } }],
    series: [{ name: 'Adjusted price', type: 'line', showSymbol: false, data: series.map((row) => row.price), itemStyle: { color: '#5eead4' },
      markPoint: { label: { show: false }, data: markers },
      markLine: company.insiderCost == null ? undefined : { symbol: 'none', label: { formatter: 'Current observed basis', position: 'insideEndTop' }, lineStyle: { color: '#fbbf24', type: 'dashed' }, data: [{ yAxis: company.insiderCost }] } },
    { name: 'Mansfield market RS', type: 'line', yAxisIndex: 1, showSymbol: false, connectNulls: true, data: series.map((row) => row.mansfield), itemStyle: { color: '#38bdf8' } },
    ...(data.research ? [{ name: 'Mansfield sector RS', type: 'line', yAxisIndex: 1, showSymbol: false, connectNulls: true, data: series.map((row) => row.sectorMansfield ?? null), itemStyle: { color: '#c4b5fd' } }] : [])],
  };
  return <>
    <div className="flex flex-wrap gap-3"><input aria-label="Search companies" className={controlClass} placeholder="Search companies" value={query} onChange={(event) => setQuery(event.target.value)} /><select aria-label="Select company" className={`${controlClass} min-w-0 max-w-full flex-1`} value={choices.some((row) => row.ticker === company.ticker) ? company.ticker : ''} onChange={(event) => openCompany(event.target.value)}><option value="" disabled>{choices.length ? 'Choose company' : 'No matching companies'}</option>{choices.map((row) => <option key={row.ticker} value={row.ticker}>{row.ticker} · {row.company}</option>)}</select><WatchButton row={company} watched={watchlist.includes(company.issuerCik)} toggle={toggleWatch} /></div>
    <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_320px]">
      <Panel title={`${company.ticker} · price and relative strength`} subtitle={`${company.company} · ${company.sector} · ${company.issuerCik ? `CIK ${company.issuerCik}` : 'Identity not exported'}`}>
        <div className="mb-4 flex flex-wrap gap-2">{[['30', '1M'], ['90', '3M'], ['180', '6M'], ['365', '1Y']].map(([days, label]) => <button aria-pressed={period === days} key={days} className={`${controlClass} ${period === days ? 'text-emerald-200' : ''}`} onClick={() => setPeriod(days)}>{label}</button>)}</div>
        {data.research && <p className="mb-4 text-xs leading-5 text-muted-foreground">Triangles = purchases; diamonds = sales, placed at the adjusted close on the reported transaction date (not trade execution price or filing availability). Only dates with an observed price receive a marker. RS lines join available weekly observations.</p>}
        {series.length < 2 ? <EmptyState title="Price series unavailable" detail="Insufficient exported observations for this period. SEC records remain available below." /> : <><EChart option={option} style={{ height: 350 }} /><p className="text-xs leading-5 text-muted-foreground">{series.length} exported observations · {series[0].date} to {series.at(-1)?.date}. The dashed line is today’s observed purchase basis, not a historical basis series. {!data.research && 'Volume, sector RS history and precise transaction markers are not exported in v1.'}</p>{series.some((row) => row.volume != null) && <EChart style={{ height: 180 }} option={{ textStyle: { color: '#cbd5e1' }, grid: { left: 70, right: 25, bottom: 30 }, tooltip: { trigger: 'axis' }, xAxis: { type: 'category', data: series.map((row) => row.date) }, yAxis: { type: 'value', name: 'Volume' }, series: [{ type: 'bar', data: series.map((row) => row.volume ?? null), itemStyle: { color: '#38bdf866' } }] }} />}</>}
      </Panel>
      <Panel title={rank ? `Score explanation · rank #${rank}` : 'Score unavailable'} subtitle="Rank within this snapshot; no predictive performance claim."><div className="grid grid-cols-2 gap-2">{[['Total', company.total], ['Insider', company.insider], ['Divergence', company.divergence], ['Turn', company.turn]].map(([label, value]) => <Fact key={String(label)} label={String(label)} value={metric(value as number | null)} />)}</div><p className="my-4"><State state={company.state} /></p><ul className="list-disc space-y-2 pl-4 text-xs leading-5 text-muted-foreground">{company.reasons.map((reason) => <li key={reason}>{reasonText(reason)}</li>)}</ul><p className="mt-4 text-xs">Market RS: {metric(company.marketRs)} · Sector RS: {metric(company.sectorRs)}</p></Panel>
    </div>
    <TapeView key={company.ticker} data={data} ticker={company.ticker} openCompany={openCompany} timezone={timezone} />
    {data.research ? <ClustersV2 data={data.research} issuer={company.issuerCik} openCompany={openCompany} /> : <ClusterView />}
  </>;
}

export function MethodologyView({ data, manifest }: { data: DashboardData; manifest: PublicationManifest }) {
  return <>
    <Panel title="Research model status" subtitle="Factual SEC exploration does not require a profitable backtest."><div className="grid gap-3 sm:grid-cols-3"><Fact label="Score version" value={data.scoreVersion} /><Fact label="Methodology lock" value={manifest.quality.methodologyComplete ? 'Complete per published evidence' : 'Candidate / incomplete'} /><Fact label="Historical validation" value={data.status === 'VALIDATED' ? 'Validated per published gate' : 'Not established'} /></div><p className="mt-4 text-sm leading-6 text-muted-foreground">Scores describe observed insider activity and price structure. They have not demonstrated predictive returns. Predictive alerts remain gated; an informational daily digest has a separate completeness and delivery policy.</p></Panel>
    <Panel title="Score components" subtitle="View filters change the screen, never the formulas or score date."><div className="space-y-4 text-sm leading-6">
      <p><strong>Company Insider:</strong> conviction 45%, cluster 25%, opportunistic activity 20%, net buying 10%.</p>
      <p><strong>Divergence:</strong> price weakness 35%, insider-activity percentile 35%, acceleration/cluster 20%, absence of relevant sales 10%.</p>
      <p><strong>Turn:</strong> base structure 35%, ordinary RS turn 25%, Mansfield market 15%, Mansfield sector 10%, volume accumulation 10%, cost-basis reclaim 5%.</p>
      <p><strong>Missing inputs:</strong> incomplete required components are unavailable, not zero. Fundamentals are outside this release. Limited history reduces confidence; a short observed window is not a complete 90-day record.</p>
    </div><a className="mt-4 inline-block text-sm text-emerald-200 underline" href="https://github.com/Garrincha077/insider-turning-engine/tree/main/config" target="_blank" rel="noreferrer">Inspect versioned methodology and weights</a></Panel>
    <Panel title="Validation protocol — a separate future goal" subtitle="No empty graph or invented performance results."><p className="text-sm leading-6 text-muted-foreground">Development: 2016–2020. Validation: 2021–2022. Sealed OOS starts in 2023 only after methodology freeze. A PASS requires at least 200 observed six-month comparable outcomes and a positive bootstrap 95% interval against the best simple benchmark. This daily-use release does not claim that gate is complete.</p></Panel>
  </>;
}

function WatchButton({ row, watched, toggle }: { row: Candidate; watched: boolean; toggle: (cik: string) => void }) {
  return <button className="rounded-lg border border-border p-2" disabled={!row.issuerCik} aria-label={`${watched ? 'Remove' : 'Add'} ${row.ticker} ${watched ? 'from' : 'to'} watchlist`} aria-pressed={watched} title={row.issuerCik ? 'Browser-only watchlist, keyed by CIK' : 'A resolved CIK is required for a stable watchlist entry'} onClick={() => toggle(row.issuerCik)}><Star className={`size-4 ${watched ? 'fill-amber-300 text-amber-300' : 'text-muted-foreground'}`} /></button>;
}
function SecLink({ row }: { row: Filing }) { const url = secUrl(row); return url ? <a className="inline-flex items-center gap-1 text-emerald-200 underline" href={url} target="_blank" rel="noreferrer">Open SEC document <ExternalLink className="size-3" /></a> : <span className="text-muted-foreground">SEC URL not exported</span>; }
function State({ state }: { state: Candidate['state'] }) { return <span className="inline-block rounded-md border border-border px-2 py-1 text-xs">{state === 'UNKNOWN' ? 'Unknown / not established' : reasonText(state)}</span>; }
function SortHeader<T>({ field, sort }: { field: SortField<T>; sort: { fieldId: string; descending: boolean; toggle: (id: string) => void } }) { return <th className="p-3" aria-sort={sort.fieldId === field.id ? sort.descending ? 'descending' : 'ascending' : 'none'}><button className="whitespace-nowrap" onClick={() => sort.toggle(field.id)}>{field.label} <span aria-hidden="true">{sort.fieldId === field.id ? sort.descending ? '↓' : '↑' : '↕'}</span></button></th>; }
function Fact({ label, value }: { label: string; value: string }) { return <div className="rounded-lg border border-border bg-background/40 p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-2 font-mono text-sm">{value}</p></div>; }
export function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) { return <section className="min-w-0 overflow-hidden rounded-xl border border-border bg-card"><div className="border-b border-border px-5 py-4"><h2 className="text-base font-semibold">{title}</h2><p className="mt-1 text-xs leading-5 text-muted-foreground">{subtitle}</p></div><div className="p-4 sm:p-5">{children}</div></section>; }
export function EmptyState({ title, detail }: { title: string; detail: string }) { return <output className="block rounded-lg border border-dashed border-border p-6"><span className="block text-sm font-medium">{title}</span><span className="mt-2 block max-w-3xl text-sm leading-6 text-muted-foreground">{detail}</span></output>; }
