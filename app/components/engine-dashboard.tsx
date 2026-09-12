import { useEffect, useMemo, useState } from 'react';
import { Activity, BellRing, Radar, ShieldAlert } from 'lucide-react';
import type { DashboardData } from '@/lib/dashboard-data';
import type { PublicationManifest, SettingsStatus } from '@/lib/operations-data';
import { loadPublication } from '@/lib/load-publication';
import { companyCatalog, instant, scoreLabel, controlClass } from '@/lib/research';
import { isCikList, isTimezone, resetPreferences, usePreference } from '@/lib/local-preferences';
import { AlertCenterView, DataCoverageView, SettingsView, SystemHealthView } from './operations-views';
import { CompanyLab, CompanyTable, CostBasisView, ClusterView, MethodologyView, PulseView, TapeView, Panel, EmptyState } from './research-views';
import { ActivityV2, BasisV2, ClustersV2, CoverageV2 } from './v2-views';

const groups = [
  { label: 'Overview', views: [['radar', 'Radar'], ['market-pulse', 'Market Pulse'], ['live-sec-tape', 'Live SEC Tape']] },
  { label: 'Research', views: [['turning-stocks', 'Turning Stocks'], ['divergence', 'Divergence'], ['smart-buys', 'Insider Buys'], ['clusters', 'Clusters'], ['cost-basis', 'Cost Basis'], ['company-lab', 'Company Lab'], ['backtest-lab', 'Methodology & Validation']] },
  { label: 'Operations', views: [['system-health', 'System Health'], ['data-coverage', 'Data Coverage'], ['alert-center', 'Alert Center'], ['settings', 'Settings']] },
];
const views = groups.flatMap((group) => group.views);
const descriptions: Record<string, string> = {
  radar: 'Explore the companies in this snapshot. Missing scores do not hide SEC activity.',
  'market-pulse': 'Observed activity in the exported population — not a census of the US market.',
  'live-sec-tape': 'Source-linked SEC records, including companies without complete research scores.',
  'turning-stocks': 'Recorded accumulation, base and turn states. These are research classifications, not trade recommendations.',
  divergence: 'Adjust the visible screening thresholds without changing the score methodology.',
  'smart-buys': 'Observed open-market purchases, largest first. This is not a recommendation list.',
  clusters: 'Independent reporting-owner evidence is required; a high cluster score alone is not proof.',
  'cost-basis': 'Observed purchase prices, not insiders’ complete holdings or a price target.',
  'company-lab': 'Explore one company and open the underlying SEC records.',
  'backtest-lab': 'What the scores measure, what is missing, and what has actually been validated.',
  'system-health': 'Publication integrity, source coverage, delivery and research readiness are separate.',
  'data-coverage': 'Actual denominators and source dates. Selected-universe coverage is not market coverage.',
  'alert-center': 'Factual daily summaries are separate from predictive alerts.',
  settings: 'Local display preferences and secure, read-only delivery configuration.',
};

function readRoute() {
  const params = new URLSearchParams(window.location.hash.slice(1));
  return { view: views.some(([id]) => id === params.get('view')) ? params.get('view')! : 'radar', issuer: params.get('issuer') ?? '', ticker: params.get('ticker') ?? '' };
}

export function EngineDashboard() {
  const [route, setRoute] = useState(readRoute);
  const [publication, setPublication] = useState<{ data: DashboardData; manifest: PublicationManifest; settings: SettingsStatus } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [watchlist, setWatchlist] = usePreference('watchlist', [], isCikList);
  const [timezone, setTimezone] = usePreference('timezone', 'Europe/Zagreb', isTimezone);
  const [previousView, setPreviousView] = useState('radar');
  const [selected, setSelected] = useState('');
  const catalog = useMemo(() => publication ? companyCatalog(publication.data) : [], [publication]);

  useEffect(() => {
    const listener = () => setRoute(readRoute());
    window.addEventListener('hashchange', listener);
    return () => window.removeEventListener('hashchange', listener);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    loadPublication(controller.signal).then((value) => {
      setPublication(value); document.documentElement.dataset.hydrated = 'true';
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Snapshot unavailable');
    });
    return () => controller.abort();
  }, []);

  function navigate(view: string, ticker?: string) {
    const company = catalog.find((item) => item.ticker === ticker);
    const params = new URLSearchParams({ view });
    if (company?.issuerCik) params.set('issuer', company.issuerCik);
    else if (ticker) params.set('ticker', ticker);
    // Watchlist and local filters deliberately never enter a shared URL.
    window.location.hash = params.toString();
    setRoute({ view, issuer: company?.issuerCik ?? '', ticker: company?.issuerCik ? '' : ticker ?? '' });
  }
  function openCompany(ticker: string) {
    if (route.view !== 'company-lab') setPreviousView(route.view);
    setSelected(ticker); navigate('company-lab', ticker);
  }
  function toggleWatch(cik: string) {
    if (/^\d{10}$/.test(cik)) setWatchlist((previous) => previous.includes(cik) ? previous.filter((id) => id !== cik) : [...previous, cik]);
  }

  if (error) return <main className="grid min-h-screen place-items-center p-6"><Panel title="Dashboard snapshot unavailable" subtitle="No sample data is substituted."><ShieldAlert className="text-rose-300" /><p className="my-4 text-sm" role="alert">{error}</p><button className={controlClass} onClick={() => window.location.reload()}>Retry snapshot</button></Panel></main>;
  if (!publication) return <main className="grid min-h-screen place-items-center p-6"><output>Checking snapshot schema and integrity…</output></main>;
  const { data, manifest, settings } = publication;
  const view = route.view;
  const company = catalog.find((item) => route.issuer ? item.issuerCik === route.issuer : item.ticker === (route.ticker || selected)) ?? (!route.issuer && !route.ticker ? catalog[0] : undefined);
  const title = views.find(([id]) => id === view)?.[1] ?? 'Radar';
  const tableProps = { data, catalog, watchlist, toggleWatch, openCompany, timezone };

  return <main className="min-h-screen text-foreground">
    <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-[1680px] items-center justify-between gap-4 px-4 sm:px-7">
        <button onClick={() => navigate('radar')} className="flex items-center gap-3 text-left"><Radar className="size-7 text-emerald-300" /><span><span className="block text-sm font-semibold">Insider Turning Engine</span><span className="hidden text-xs text-muted-foreground sm:block">SEC research · daily close</span></span></button>
        <div className="hidden text-xs text-muted-foreground lg:block">SEC through {instant(manifest.watermarks.secAcceptedThrough, timezone)} · {timezone}</div>
        <button className={controlClass} onClick={() => navigate('alert-center')}><BellRing className="mr-2 inline size-4" />Alerts</button>
      </div>
      <label className="flex items-center gap-3 border-t border-border px-4 py-2 text-xs xl:hidden">Section
        <select aria-label="Dashboard section" className={`${controlClass} min-w-0 flex-1`} value={view} onChange={(event) => navigate(event.target.value)}>
          {groups.map((group) => <optgroup key={group.label} label={group.label}>{group.views.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</optgroup>)}
        </select>
      </label>
    </header>
    <div className="mx-auto grid max-w-[1680px] gap-7 px-4 py-6 sm:px-7 xl:grid-cols-[220px_minmax(0,1fr)]">
      <aside className="hidden xl:block"><nav aria-label="Dashboard sections" className="sticky top-24 space-y-5">
        {groups.map((group) => <div key={group.label}><p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">{group.label}</p>{group.views.map(([id, label]) => <button key={id} aria-current={view === id ? 'page' : undefined} onClick={() => navigate(id)} className={`mb-1 w-full rounded-lg px-3 py-2.5 text-left text-sm ${view === id ? 'bg-emerald-400/10 font-semibold text-emerald-200' : 'text-muted-foreground hover:bg-card'}`}>{label}</button>)}</div>)}
      </nav></aside>
      <section className="min-w-0 space-y-6">
        <div><p className="mb-2 flex items-center gap-2 text-xs text-emerald-300"><Activity className="size-4" />Daily research workspace</p><h1 className="text-3xl font-semibold tracking-tight">{title}</h1><p className="mt-2 max-w-4xl text-sm leading-6 text-muted-foreground">{descriptions[view]}</p></div>
        <div className="flex flex-wrap gap-x-5 gap-y-2 border-y border-border py-3 text-xs text-muted-foreground">
          <span className="text-amber-200">{scoreLabel}</span><span>{data.scoreVersion}</span><span>Score snapshot: {instant(manifest.asOf, timezone)}</span><span>Market through: {manifest.watermarks.marketSessionThrough ?? 'unavailable'}</span>
          {data.status === 'STALE' && <output className="text-rose-300">Source reports stale data. Check System Health.</output>}
        </div>
        {view === 'radar' && <CompanyTable {...tableProps} mode="radar" />}
        {view === 'turning-stocks' && <CompanyTable key="turning" {...tableProps} mode="turning" />}
        {view === 'divergence' && <CompanyTable key="divergence" {...tableProps} mode="divergence" />}
        {view === 'market-pulse' && (data.research ? <ActivityV2 data={data.research} /> : <PulseView data={data} />)}
        {view === 'smart-buys' && <TapeView key="buys" data={data} openCompany={openCompany} timezone={timezone} buysOnly />}
        {view === 'live-sec-tape' && <TapeView key="tape" data={data} openCompany={openCompany} timezone={timezone} />}
        {view === 'clusters' && (data.research ? <ClustersV2 data={data.research} openCompany={openCompany} /> : <ClusterView />)}
        {view === 'cost-basis' && (data.research ? <BasisV2 data={data.research} openCompany={openCompany} /> : <CostBasisView catalog={catalog} openCompany={openCompany} />)}
        {view === 'company-lab' && <><button className={controlClass} onClick={() => navigate(previousView)}>← Back to {views.find(([id]) => id === previousView)?.[1]}</button>{company ? <CompanyLab {...tableProps} company={company} /> : <EmptyState title="Company not in this snapshot" detail="This shared issuer link cannot be resolved from the published company catalogue. Return to Radar to choose an available company." />}</>}
        {view === 'backtest-lab' && <MethodologyView data={data} manifest={manifest} />}
        {view === 'system-health' && <SystemHealthView manifest={manifest} research={data.research} settings={settings} />}
        {view === 'data-coverage' && (data.research ? <CoverageV2 data={data.research} /> : <DataCoverageView manifest={manifest} />)}
        {view === 'alert-center' && <AlertCenterView settings={settings} research={data.research} />}
        {view === 'settings' && <><Panel title="Local display preferences" subtitle="Saved only in this browser. They never change Telegram recipients, policy or selection.">
          <label className="flex flex-wrap items-center gap-3 text-sm">Display timezone<select aria-label="Display timezone" className={controlClass} value={timezone} onChange={(event) => setTimezone(event.target.value)}>{['Europe/Zagreb', 'America/New_York', 'UTC'].map((zone) => <option key={zone}>{zone}</option>)}</select></label>
          <p className="my-4 text-sm">Watchlist: {watchlist.length ? watchlist.map((id) => catalog.find((item) => item.issuerCik === id)?.ticker ?? id).join(', ') : 'No companies saved'}</p><button className={controlClass} onClick={resetPreferences}>Reset local preferences and watchlist</button>
        </Panel><SettingsView settings={settings} /></>}
        <footer className="border-t border-border pt-4 text-xs leading-5 text-muted-foreground">Public read-only research. Coverage and survivorship limitations apply. Not investment advice. Published source dates remain unchanged by display filters.</footer>
      </section>
    </div>
  </main>;
}
