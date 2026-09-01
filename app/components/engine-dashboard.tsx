import { useEffect, useState } from 'react';
import {
  Activity,
  BellRing,
  Building2,
  ChevronDown,
  CircleDollarSign,
  DatabaseZap,
  FlaskConical,
  Gauge,
  LineChart,
  Radar,
  Search,
  ShieldCheck,
  ShoppingCart,
  Target,
  TrendingUp,
  Users,
} from 'lucide-react';
import {
  columnFilteringFeature,
  createFilteredRowModel,
  createSortedRowModel,
  createColumnHelper,
  filterFn_includesString,
  globalFilteringFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  tableFeatures,
  type SortingState,
  useTable,
} from '@tanstack/react-table';

import { Badge } from '@/components/ui/badge';
import { EChart } from '@/components/echart';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  type Candidate,
  type DashboardData,
  sampleDashboardData,
} from '@/lib/dashboard-data';

const views = [
  { id: 'radar', label: 'Radar', icon: Radar },
  { id: 'market-pulse', label: 'Market Pulse', icon: Gauge },
  { id: 'turning-stocks', label: 'Turning Stocks', icon: TrendingUp },
  { id: 'divergence', label: 'Divergence', icon: LineChart },
  { id: 'smart-buys', label: 'Smart Buys', icon: ShoppingCart },
  { id: 'clusters', label: 'Clusters', icon: Users },
  { id: 'cost-basis', label: 'Cost Basis', icon: CircleDollarSign },
  { id: 'live-sec-tape', label: 'Live SEC Tape', icon: DatabaseZap },
  { id: 'company-lab', label: 'Company Lab', icon: Building2 },
  { id: 'backtest-lab', label: 'Backtest Lab', icon: FlaskConical },
] as const;

type ViewId = (typeof views)[number]['id'];

const candidateFeatures = tableFeatures({
  columnFilteringFeature,
  globalFilteringFeature,
  filteredRowModel: createFilteredRowModel(),
  filterFns: { includesString: filterFn_includesString },
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { alphanumeric: sortFn_alphanumeric },
});
const candidateColumn = createColumnHelper<typeof candidateFeatures, Candidate>();
const candidateColumns = candidateColumn.columns([
  candidateColumn.accessor((row) => `${row.ticker} ${row.company}`, { id: 'ticker', header: 'Ticker', cell: (info) => <div><div className="font-mono font-semibold text-emerald-200">{info.row.original.ticker}</div><div className="max-w-36 truncate text-[10px] text-muted-foreground">{info.row.original.company}</div></div> }),
  candidateColumn.accessor('total', { header: 'Total', cell: (info) => <Score value={info.getValue()} strong /> }),
  candidateColumn.accessor('insider', { header: 'Insider', cell: (info) => <Score value={info.getValue()} /> }),
  candidateColumn.accessor('divergence', { header: 'Divergence', cell: (info) => <Score value={info.getValue()} /> }),
  candidateColumn.accessor('turn', { header: 'Turn', cell: (info) => <Score value={info.getValue()} /> }),
  candidateColumn.accessor('marketRs', { header: 'MRS Mkt', cell: (info) => <span className={(info.getValue() ?? 0) >= 0 ? 'font-mono text-xs text-emerald-300' : 'font-mono text-xs text-rose-300'}>{signed(info.getValue())}</span> }),
  candidateColumn.accessor((row) => costReturn(row), { id: 'costPl', header: 'Cost P/L', cell: (info) => <span className="font-mono text-xs text-amber-200">{signed(info.getValue())}{info.getValue() === null ? '' : '%'}</span> }),
  candidateColumn.accessor('state', { header: 'State', cell: (info) => <StateBadge state={info.getValue()} /> }),
]);

export function EngineDashboard() {
  const [view, setView] = useState<ViewId>('radar');
  const [data, setData] = useState(sampleDashboardData);
  const [source, setSource] = useState<'snapshot' | 'sample'>('sample');
  const [selectedTicker, setSelectedTicker] = useState('NVDA');

  useEffect(() => {
    document.documentElement.dataset.hydrated = 'true';
    fetch(`${import.meta.env.BASE_URL}data/dashboard.json`, { cache: 'no-store' })
      .then((response) => {
        if (!response.ok) throw new Error('Snapshot unavailable');
        return response.json() as Promise<DashboardData>;
      })
      .then((snapshot) => {
        if (!Array.isArray(snapshot.candidates) || !snapshot.schemaVersion) {
          throw new Error('Invalid dashboard snapshot');
        }
        setData(snapshot);
        setSource('snapshot');
        setSelectedTicker(snapshot.candidates[0]?.ticker ?? '');
      })
      .catch(() => setSource('sample'));
  }, []);

  const selected = data.candidates.find((candidate) => candidate.ticker === selectedTicker) ?? data.candidates[0];
  const title = views.find((item) => item.id === view)?.label ?? 'Radar';
  const validated = source === 'snapshot' && data.status === 'VALIDATED';

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-border/80 bg-background/90 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1600px] items-center justify-between gap-5 px-4 sm:px-7">
          <button onClick={() => setView('radar')} className="flex min-w-0 items-center gap-3 text-left">
            <div className="grid size-9 shrink-0 place-items-center rounded-lg border border-emerald-400/30 bg-emerald-400/10 text-emerald-300"><Radar className="size-5" /></div>
            <div className="min-w-0"><p className="truncate text-sm font-semibold tracking-tight">Insider Turning Engine</p><p className="truncate text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Market intelligence · Daily close</p></div>
          </button>
          <div className="hidden items-center gap-6 text-xs text-muted-foreground md:flex">
            <span className="flex items-center gap-2"><DatabaseZap className="size-3.5 text-sky-300" /> {source === 'snapshot' ? 'Snapshot loaded' : 'Sample dataset'}</span>
            <span className="flex items-center gap-2"><ShieldCheck className={`size-3.5 ${validated ? 'text-emerald-300' : 'text-amber-300'}`} /> {validated ? 'Quality gates passed' : 'Experimental · not validated'}</span>
            <span className="font-mono">{new Date(data.generatedAt).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }).toUpperCase()}</span>
          </div>
          <button onClick={() => setView('live-sec-tape')} className="inline-flex h-9 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-medium transition hover:border-emerald-400/40 hover:bg-accent"><BellRing className="size-3.5 text-amber-300" /> Alerts</button>
        </div>
        <div className="scrollbar-none flex gap-1 overflow-x-auto border-t border-border/50 px-3 py-2 xl:hidden">
          {views.map((item) => <NavButton key={item.id} item={item} active={view === item.id} onClick={() => setView(item.id)} compact />)}
        </div>
      </header>

      <div className="mx-auto grid max-w-[1600px] grid-cols-1 gap-7 px-4 py-6 sm:px-7 xl:grid-cols-[215px_minmax(0,1fr)]">
        <aside className="hidden xl:block">
          <nav aria-label="Dashboard sections" className="sticky top-24 space-y-1">
            {views.map((item) => <NavButton key={item.id} item={item} active={view === item.id} onClick={() => setView(item.id)} />)}
            <div className="mt-6 rounded-lg border border-border bg-card/70 p-3 text-[10px] leading-4 text-muted-foreground">
              <p className="font-semibold uppercase tracking-wider text-slate-300">Research build</p>
              <p className="mt-2">Free-market data carries coverage and survivorship limitations. Signals are not investment advice.</p>
            </div>
          </nav>
        </aside>

        <section className="min-w-0 space-y-6">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
            <div>
              <div className="mb-2 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-emerald-300"><Activity className="size-3.5" /> {title} / {validated ? 'validated close' : 'experimental snapshot'}</div>
              <h1 className="text-2xl font-semibold tracking-[-0.03em] sm:text-3xl">{view === 'radar' ? 'The market is still cautious. Insiders are not.' : title}</h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{view === 'radar' ? 'Qualified open-market buying where price weakness is beginning to meet improving relative strength.' : viewDescription(view)}</p>
            </div>
            <Badge className="h-7 border border-amber-300/25 bg-amber-300/10 px-3 text-amber-200">{data.status} · {data.scoreVersion}</Badge>
          </div>

          {source === 'snapshot' && data.status === 'EXPERIMENTAL' && <div className="rounded-lg border border-amber-300/20 bg-amber-300/8 px-4 py-3 text-xs leading-5 text-amber-100">Live experimental snapshot: official SEC ownership filings with a rolling window and Yahoo adjusted chart data as a temporary market fallback. Scores are research candidates, not validated signals or investment advice.</div>}

          {view === 'radar' && <RadarView data={data} selected={selected} onSelect={setSelectedTicker} onOpenLab={() => setView('company-lab')} />}
          {view === 'market-pulse' && <MarketPulseView data={data} />}
          {view === 'turning-stocks' && <CandidateList data={data} mode="turning" selectedTicker={selectedTicker} onSelect={setSelectedTicker} />}
          {view === 'divergence' && <CandidateList data={data} mode="divergence" selectedTicker={selectedTicker} onSelect={setSelectedTicker} />}
          {view === 'smart-buys' && <SmartBuysView data={data} />}
          {view === 'clusters' && <ClusterView data={data} selectedTicker={selectedTicker} onSelect={setSelectedTicker} />}
          {view === 'cost-basis' && <CostBasisView data={data} />}
          {view === 'live-sec-tape' && <SecTapeView data={data} />}
          {view === 'company-lab' && selected && <CompanyLab data={data} candidate={selected} onTicker={setSelectedTicker} />}
          {view === 'backtest-lab' && <BacktestLab data={data} />}
        </section>
      </div>
    </main>
  );
}

function NavButton({ item, active, onClick, compact = false }: { item: (typeof views)[number]; active: boolean; onClick: () => void; compact?: boolean }) {
  const Icon = item.icon;
  return <button onClick={onClick} className={`flex shrink-0 items-center gap-2 rounded-lg text-xs transition ${compact ? 'px-3 py-2' : 'w-full px-3 py-2.5'} ${active ? 'border border-emerald-400/20 bg-emerald-400/10 font-semibold text-emerald-200' : 'border border-transparent text-muted-foreground hover:bg-card hover:text-foreground'}`}><Icon className="size-3.5" />{item.label}{active && !compact && <span className="ml-auto size-1.5 rounded-full bg-emerald-300 shadow-[0_0_10px_var(--pulse)]" />}</button>;
}

function RadarView({ data, selected, onSelect, onOpenLab }: { data: DashboardData; selected?: Candidate; onSelect: (ticker: string) => void; onOpenLab: () => void }) {
  return <>
    <PulseCards data={data} />
    <div className="grid gap-6 2xl:grid-cols-[minmax(0,1fr)_340px]">
      <CandidateTable candidates={data.candidates.slice(0, 5)} selectedTicker={selected?.ticker} onSelect={onSelect} />
      {selected ? <ReasonPanel candidate={selected} onOpen={onOpenLab} /> : <EmptyState message="No issuer has a complete, point-in-time score for this snapshot." />}
    </div>
  </>;
}

function PulseCards({ data }: { data: DashboardData }) {
  const buys = data.filings.filter((filing) => filing.side === 'BUY');
  const issuerCount = new Set(data.filings.map((filing) => filing.ticker)).size;
  const buyIssuerCount = new Set(buys.map((filing) => filing.ticker)).size;
  const metrics = [
    { label: 'Relevant filings', value: String(data.filings.length), detail: 'P/S in live window' },
    { label: 'Unique insiders', value: String(new Set(data.filings.map((filing) => filing.owner)).size), detail: 'normalized owners' },
    { label: 'Buy value', value: `$${compactMoney(buys.reduce((sum, filing) => sum + filing.value, 0))}`, detail: 'qualified purchases' },
    { label: 'Buy breadth', value: issuerCount ? `${(buyIssuerCount / issuerCount * 100).toFixed(1)}%` : '—', detail: `${buyIssuerCount} of ${issuerCount} issuers` },
  ];
  return <div className="grid gap-4 lg:grid-cols-[1.3fr_repeat(4,1fr)]">
    <div className="relative overflow-hidden rounded-xl border border-emerald-400/20 bg-[linear-gradient(135deg,rgba(20,184,166,.17),rgba(15,23,42,.2))] p-5">
      <div className="absolute -right-10 -top-16 size-40 rounded-full bg-emerald-300/10 blur-3xl" /><p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-200">Market Insider Pulse</p>
      <div className="mt-4 flex items-end gap-3"><span className="font-mono text-5xl font-semibold tracking-[-0.06em]">{formatMetric(data.marketPulse)}</span>{data.marketPulse !== null && <span className="mb-1.5 text-xs font-semibold text-emerald-300">Point-in-time composite</span>}</div>
      <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-slate-950/50"><div className="h-full rounded-full bg-gradient-to-r from-sky-400 via-emerald-400 to-lime-300" style={{ width: `${data.marketPulse ?? 0}%` }} /></div><p className="mt-2 text-xs text-slate-400">{data.pulsePercentile === null ? 'Insufficient prior history' : `${data.pulsePercentile.toFixed(1)}th historical percentile`}</p>
    </div>
    {metrics.map((metric) => <div key={metric.label} className="rounded-xl border border-border bg-card p-4"><p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-muted-foreground">{metric.label}</p><p className="mt-5 font-mono text-2xl font-semibold">{metric.value}</p><p className="mt-2 text-xs text-muted-foreground">{metric.detail}</p></div>)}
  </div>;
}

function CandidateTable({ candidates, selectedTicker, onSelect }: { candidates: Candidate[]; selectedTicker?: string; onSelect: (ticker: string) => void }) {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'total', desc: true }]);
  const [search, setSearch] = useState('');
  const table = useTable({
    data: candidates,
    columns: candidateColumns,
    features: candidateFeatures,
    state: { sorting, globalFilter: search },
    onSortingChange: setSorting,
    onGlobalFilterChange: setSearch,
    globalFilterFn: 'includesString',
  });
  return <section className="overflow-hidden rounded-xl border border-border bg-card">
    <div className="flex flex-col gap-3 border-b border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="text-sm font-semibold">Ranked candidates</h2><p className="mt-1 text-xs text-muted-foreground">Click headers to sort · rows to inspect</p></div><div className="relative"><Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" /><Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Ticker or company" className="h-8 w-full pl-8 text-xs sm:w-48" /></div></div>
    <Table><TableHeader>{table.getHeaderGroups().map((group) => <TableRow key={group.id} className="hover:bg-transparent">{group.headers.map((header, index) => <TableHead key={header.id} className={index === 0 ? 'pl-5' : ''}><button className="flex items-center gap-1" onClick={header.column.getToggleSortingHandler()}>{header.isPlaceholder ? null : <table.FlexRender header={header} />}{header.column.getIsSorted() && <ChevronDown className={`size-3 transition ${header.column.getIsSorted() === 'asc' ? 'rotate-180' : ''}`} />}</button></TableHead>)}</TableRow>)}</TableHeader>
      <TableBody>{table.getRowModel().rows.map((row) => <TableRow key={row.id} data-state={row.original.ticker === selectedTicker ? 'selected' : undefined} onClick={() => onSelect(row.original.ticker)} className="cursor-pointer">{row.getAllCells().map((cell, index) => <TableCell key={cell.id} className={index === 0 ? 'pl-5' : ''}><table.FlexRender cell={cell} /></TableCell>)}</TableRow>)}</TableBody>
    </Table>
  </section>;
}

function ReasonPanel({ candidate, onOpen }: { candidate: Candidate; onOpen: () => void }) {
  const pnl = costReturn(candidate);
  return <aside className="rounded-xl border border-border bg-card p-5"><div className="flex items-center justify-between"><p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">Why ranked #{candidate.total >= 90 ? 1 : '—'}</p><Target className="size-4 text-emerald-300" /></div><div className="mt-3 flex items-end gap-2"><span className="font-mono text-3xl font-semibold text-emerald-200">{candidate.ticker}</span><span className="mb-1 text-xs text-muted-foreground">Total {candidate.total}</span></div><div className="mt-5 space-y-3 text-xs leading-5 text-slate-300">{candidate.reasons.map((reason) => <div key={reason} className="flex gap-2"><span className="mt-2 size-1 shrink-0 rounded-full bg-emerald-300" /><span>{reason}</span></div>)}</div><div className="mt-6 rounded-lg border border-border bg-background/55 p-3"><p className="text-[10px] uppercase tracking-wider text-muted-foreground">90D insider cost</p><div className="mt-2 flex items-end justify-between"><span className="font-mono text-xl font-semibold">{candidate.insiderCost === null ? 'Unavailable' : `$${candidate.insiderCost.toFixed(2)}`}</span><span className="text-xs text-amber-200">{pnl === null ? 'Insufficient data' : `${Math.abs(pnl).toFixed(1)}% ${pnl < 0 ? 'below' : 'above'}`}</span></div></div><button onClick={onOpen} className="mt-4 w-full rounded-lg border border-emerald-400/25 bg-emerald-400/10 px-3 py-2 text-xs font-semibold text-emerald-200 hover:bg-emerald-400/15">Open Company Lab</button></aside>;
}

function MarketPulseView({ data }: { data: DashboardData }) {
  const option = darkChart({ tooltip: { trigger: 'axis' }, legend: { data: ['Market', 'Technology', 'Financials'], textStyle: { color: '#8fa3b7' } }, xAxis: { type: 'category', data: data.pulseHistory.map((point) => point.date) }, yAxis: { type: 'value', min: 0, max: 100 }, series: [{ name: 'Market', type: 'line', smooth: true, data: data.pulseHistory.map((point) => point.market), lineStyle: { color: '#5eead4', width: 3 }, itemStyle: { color: '#5eead4' } }, { name: 'Technology', type: 'line', smooth: true, data: data.pulseHistory.map((point) => point.technology), lineStyle: { color: '#38bdf8' }, itemStyle: { color: '#38bdf8' } }, { name: 'Financials', type: 'line', smooth: true, data: data.pulseHistory.map((point) => point.financials), lineStyle: { color: '#fbbf24' }, itemStyle: { color: '#fbbf24' } }] });
  return <><PulseCards data={data} /><Panel title="Market and sector pulse history" subtitle="Composite percentile, point-in-time"><EChart option={option} style={{ height: 360 }} /></Panel></>;
}

function CandidateList({ data, mode, selectedTicker, onSelect }: { data: DashboardData; mode: 'turning' | 'divergence'; selectedTicker: string; onSelect: (ticker: string) => void }) {
  const sorted = [...data.candidates].sort((a, b) => mode === 'turning' ? b.turn - a.turn : b.divergence - a.divergence);
  const selected = sorted.find((candidate) => candidate.ticker === selectedTicker) ?? sorted[0];
  return <div className="grid gap-6 2xl:grid-cols-[minmax(0,1fr)_340px]"><CandidateTable candidates={sorted} selectedTicker={selectedTicker} onSelect={onSelect} />{selected ? <ReasonPanel candidate={selected} onOpen={() => undefined} /> : <EmptyState message="No complete candidates are available for this view." />}</div>;
}

function SmartBuysView({ data }: { data: DashboardData }) {
  const buys = data.filings.filter((filing) => filing.side === 'BUY');
  return <Panel title="Highest-conviction purchases" subtitle="Qualified open-market buys only">{buys.length === 0 ? <EmptyState message="No qualified open-market purchase is available in this live window." /> : <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{buys.map((filing) => <div key={`${filing.accession}:${filing.owner}`} className="rounded-lg border border-border bg-background/35 p-4"><div className="flex items-center justify-between"><span className="font-mono text-lg font-semibold text-emerald-200">{filing.ticker}</span><Badge className="bg-emerald-400/10 text-emerald-200">BUY</Badge></div><p className="mt-4 text-sm font-medium">{filing.owner}</p><p className="text-xs text-muted-foreground">{filing.role}</p><p className="mt-4 font-mono text-2xl font-semibold">${compactMoney(filing.value)}</p><p className="mt-1 text-[10px] text-muted-foreground">Filed {filing.filedAt} UTC</p></div>)}</div>}</Panel>;
}

function ClusterView({ data, selectedTicker, onSelect }: { data: DashboardData; selectedTicker: string; onSelect: (ticker: string) => void }) {
  return <div className="grid gap-6 lg:grid-cols-2">{[...data.candidates].sort((a, b) => b.cluster - a.cluster).map((candidate) => <button key={candidate.ticker} onClick={() => onSelect(candidate.ticker)} className={`rounded-xl border p-5 text-left transition ${selectedTicker === candidate.ticker ? 'border-emerald-400/35 bg-emerald-400/8' : 'border-border bg-card hover:border-slate-500'}`}><div className="flex items-center justify-between"><span className="font-mono text-xl font-semibold text-emerald-200">{candidate.ticker}</span><Score value={candidate.cluster} strong /></div><p className="mt-1 text-xs text-muted-foreground">{candidate.company}</p><div className="mt-5 flex gap-2"><Badge variant="outline">{candidate.cluster >= 90 ? 'CEO_CFO_CLUSTER' : '3_PLUS_BUYERS'}</Badge>{candidate.reasons.some((item) => item.toLowerCase().includes('sales')) && <Badge variant="outline">NO_SELLS_90D</Badge>}</div></button>)}</div>;
}

function CostBasisView({ data }: { data: DashboardData }) {
  const available = data.candidates.flatMap((candidate) => { const pnl = costReturn(candidate); return pnl === null ? [] : [{ candidate, pnl }]; });
  return <Panel title="Insider weighted cost basis" subtitle="Qualified purchases in the trailing 90 days">{available.length === 0 ? <EmptyState message="No candidate has both a current price and a qualified 90D insider basis." /> : <div className="space-y-3">{available.map(({ candidate, pnl }) => <div key={candidate.ticker} className="grid grid-cols-[70px_1fr_auto_auto] items-center gap-4 rounded-lg border border-border bg-background/35 p-4"><span className="font-mono font-semibold text-emerald-200">{candidate.ticker}</span><div className="h-1.5 overflow-hidden rounded-full bg-slate-800"><div className={`h-full rounded-full ${pnl >= 0 ? 'bg-emerald-400' : 'bg-amber-300'}`} style={{ width: `${Math.min(100, 45 + Math.abs(pnl) * 4)}%` }} /></div><span className="font-mono text-xs">${candidate.insiderCost?.toFixed(2)}</span><span className={`w-16 text-right font-mono text-xs ${pnl >= 0 ? 'text-emerald-300' : 'text-amber-200'}`}>{signed(pnl)}%</span></div>)}</div>}</Panel>;
}

function SecTapeView({ data }: { data: DashboardData }) {
  return <Panel title="Latest relevant Form 4 filings" subtitle="Normalized and deduplicated SEC tape">{data.filings.length === 0 ? <EmptyState message="No normalized P/S filing is available in this snapshot." /> : <Table><TableHeader><TableRow><TableHead>Ticker</TableHead><TableHead>Reporting owner</TableHead><TableHead>Role</TableHead><TableHead>Side</TableHead><TableHead>Value</TableHead><TableHead>Filed UTC</TableHead><TableHead>Accession</TableHead></TableRow></TableHeader><TableBody>{data.filings.map((filing) => <TableRow key={`${filing.accession}:${filing.owner}:${filing.side}`}><TableCell className="font-mono font-semibold text-emerald-200">{filing.ticker}</TableCell><TableCell>{filing.owner}</TableCell><TableCell className="text-muted-foreground">{filing.role}</TableCell><TableCell><Badge className={filing.side === 'BUY' ? 'bg-emerald-400/10 text-emerald-200' : 'bg-rose-400/10 text-rose-200'}>{filing.side}</Badge></TableCell><TableCell className="font-mono">${compactMoney(filing.value)}</TableCell><TableCell className="font-mono text-xs text-muted-foreground">{filing.filedAt}</TableCell><TableCell className="font-mono text-[10px] text-muted-foreground">{filing.accession}</TableCell></TableRow>)}</TableBody></Table>}</Panel>;
}

function CompanyLab({ data, candidate, onTicker }: { data: DashboardData; candidate: Candidate; onTicker: (ticker: string) => void }) {
  const series = data.companySeries.filter((point) => point.ticker === candidate.ticker);
  const option = darkChart({ tooltip: { trigger: 'axis' }, legend: { data: ['Price', 'Insider cost', 'Mansfield RS'], textStyle: { color: '#8fa3b7' } }, xAxis: { type: 'category', data: series.map((point) => point.date) }, yAxis: [{ type: 'value', position: 'left' }, { type: 'value', position: 'right' }], series: [{ name: 'Price', type: 'line', smooth: true, data: series.map((point) => point.price), lineStyle: { color: '#5eead4', width: 3 }, itemStyle: { color: '#5eead4' } }, { name: 'Insider cost', type: 'line', data: series.map((point) => point.cost), lineStyle: { color: '#fbbf24', type: 'dashed' }, itemStyle: { color: '#fbbf24' } }, { name: 'Mansfield RS', type: 'bar', yAxisIndex: 1, data: series.map((point) => point.mansfield), itemStyle: { color: '#38bdf855' } }] });
  return <><div className="flex flex-wrap gap-2">{data.candidates.map((item) => <button key={item.ticker} onClick={() => onTicker(item.ticker)} className={`rounded-lg border px-3 py-2 font-mono text-xs ${candidate.ticker === item.ticker ? 'border-emerald-400/35 bg-emerald-400/10 text-emerald-200' : 'border-border bg-card text-muted-foreground'}`}>{item.ticker}</button>)}</div><div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_330px]"><Panel title={`${candidate.ticker} · price, cost basis, and relative strength`} subtitle={candidate.company}>{series.length === 0 ? <EmptyState message="No market series is available for this issuer." /> : <EChart option={option} style={{ height: 420 }} />}</Panel><ReasonPanel candidate={candidate} onOpen={() => undefined} /></div></>;
}

function BacktestLab({ data }: { data: DashboardData }) {
  const option = darkChart({ tooltip: { trigger: 'axis' }, legend: { data: ['Full engine', 'Cluster buys', 'Simple ratio'], textStyle: { color: '#8fa3b7' } }, xAxis: { type: 'category', data: data.backtest.map((item) => item.horizon) }, yAxis: { type: 'value', name: 'Median excess %' }, series: [{ name: 'Full engine', type: 'bar', data: data.backtest.map((item) => item.fullEngine), itemStyle: { color: '#5eead4' } }, { name: 'Cluster buys', type: 'bar', data: data.backtest.map((item) => item.clusterBuy), itemStyle: { color: '#38bdf8' } }, { name: 'Simple ratio', type: 'bar', data: data.backtest.map((item) => item.simpleRatio), itemStyle: { color: '#64748b' } }] });
  return <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_330px]"><Panel title="Forward excess returns vs SPY" subtitle="No synthetic results are shown">{data.backtest.length === 0 ? <EmptyState message="The sealed OOS backtest has not been run. Live scores remain experimental." /> : <EChart option={option} style={{ height: 410 }} />}</Panel><Panel title="Validation gate" subtitle="Sealed OOS: 2023–latest"><div className="space-y-4 text-xs text-slate-300"><Metric label="OOS events" value="— / 200" /><Metric label="Primary horizon" value="6M" /><Metric label="Current outcome" value="NOT RUN" accent /><p className="rounded-lg border border-amber-300/20 bg-amber-300/8 p-3 leading-5 text-amber-100">Telegram remains off until the point-in-time backtest meets the formal PASS criteria.</p></div></Panel></div>;
}

function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) { return <section className="overflow-hidden rounded-xl border border-border bg-card"><div className="border-b border-border px-5 py-4"><h2 className="text-sm font-semibold">{title}</h2><p className="mt-1 text-xs text-muted-foreground">{subtitle}</p></div><div className="p-5">{children}</div></section>; }
function EmptyState({ message }: { message: string }) { return <div className="grid min-h-36 place-items-center rounded-xl border border-dashed border-border bg-card/50 p-6 text-center text-xs leading-5 text-muted-foreground">{message}</div>; }
function Metric({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) { return <div className="flex items-center justify-between border-b border-border pb-3"><span className="text-muted-foreground">{label}</span><span className={`font-mono font-semibold ${accent ? 'text-amber-200' : 'text-slate-100'}`}>{value}</span></div>; }
function Score({ value, strong = false }: { value: number; strong?: boolean }) { return <span className={`font-mono text-sm font-semibold ${strong ? 'text-emerald-200' : value >= 85 ? 'text-sky-200' : 'text-slate-200'}`}>{value}</span>; }
function StateBadge({ state }: { state: Candidate['state'] }) { return <span className="rounded-md border border-sky-300/20 bg-sky-300/10 px-2 py-1 text-[9px] font-semibold tracking-wide text-sky-200">{state.replaceAll('_', ' ')}</span>; }
function signed(value: number | null) { return value === null ? '—' : `${value >= 0 ? '+' : ''}${value.toFixed(1)}`; }
function formatMetric(value: number | null) { return value === null ? '—' : value.toFixed(1); }
function costReturn(candidate: Candidate) { return candidate.currentPrice === null || candidate.insiderCost === null || candidate.insiderCost <= 0 ? null : (candidate.currentPrice / candidate.insiderCost - 1) * 100; }
function compactMoney(value: number) { return value >= 1_000_000 ? `${(value / 1_000_000).toFixed(1)}M` : `${Math.round(value / 1_000)}K`; }
function viewDescription(view: ViewId) { const descriptions: Record<ViewId, string> = { radar: '', 'market-pulse': 'Market-wide and sector-wide insider activity, normalized against point-in-time history.', 'turning-stocks': 'Candidates advancing through the price/volume state machine.', divergence: 'The strongest gaps between weak price action and qualified insider accumulation.', 'smart-buys': 'Individual purchases with the highest estimated information content.', clusters: 'Independent insiders buying the same issuer inside a compact window.', 'cost-basis': 'Where current price sits relative to qualified insider purchase costs.', 'live-sec-tape': 'The newest normalized filings that survived classification and quality checks.', 'company-lab': 'A single-issuer view of price, insider cost basis, RS, scores, and reasons.', 'backtest-lab': 'Forward-return evidence, simple benchmarks, and the sealed validation gate.' }; return descriptions[view]; }
function darkChart(option: Record<string, unknown>) { return { backgroundColor: 'transparent', textStyle: { color: '#cbd5e1', fontFamily: 'var(--font-geist-mono)' }, grid: { left: 45, right: 35, top: 48, bottom: 32 }, xAxis: { axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { color: '#8093a7' }, splitLine: { show: false } }, yAxis: { axisLine: { show: false }, axisLabel: { color: '#8093a7' }, splitLine: { lineStyle: { color: '#263446' } } }, ...option }; }
