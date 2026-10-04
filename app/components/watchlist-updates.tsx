import type { Candidate, DashboardData } from '@/lib/dashboard-data';
import type { WatchlistIssuerChanges } from '@/lib/watchlist-changes';
import { instant, money, reasonText } from '@/lib/research';

export function WatchlistUpdates({ data, catalog, watched, changes, comparedAt, timezone, openCompany }: {
  data: DashboardData; catalog: Candidate[]; watched: string[];
  changes: Map<string, WatchlistIssuerChanges>; comparedAt: string | null; timezone: string;
  openCompany: (ticker: string) => void;
}) {
  if (!watched.length) return null;
  const companies = new Map(catalog.map((company) => [company.issuerCik, company]));
  const owners = new Map(data.research?.reportingOwners.map((owner) => [owner.ownerCik, owner.name]));
  const count = [...changes.values()].reduce((sum, row) => sum + row.newPurchases.length + row.newClusters.length + (row.stateChange ? 1 : 0), 0);
  return <details className="rounded-xl border border-border bg-card p-4" open={count > 0} data-testid="watchlist-updates">
    <summary className="cursor-pointer text-sm font-semibold">Watchlist updates · {count ? `${count} observed change${count === 1 ? '' : 's'}` : 'no new changes established'}</summary>
    <p className="my-3 text-xs leading-5 text-muted-foreground">{comparedAt ? `Compared with the previous verified snapshot viewed in this browser: ${instant(comparedAt, timezone)}.` : 'A local baseline is saved for the next published snapshot; no historical backlog is labeled new.'} Local tracking never changes Telegram selection.</p>
    <ul className="divide-y divide-border">{watched.map((cik) => {
      const company = companies.get(cik);
      const change = changes.get(cik);
      const noChanges = !change?.newPurchases.length && !change?.newClusters.length && !change?.stateChange;
      return <li className="py-3 text-sm" key={cik}>
        {company ? <button onClick={() => openCompany(company.ticker)} className="font-mono font-semibold text-emerald-200">{company.ticker}</button> : <span>CIK {cik} · not in this publication</span>}
        {change?.baselineStatus !== 'AVAILABLE' ? <p className="mt-1 text-xs text-muted-foreground">{change?.reason ?? 'Economic-event tracking is unavailable in this snapshot.'}</p>
          : noChanges ? <p className="mt-1 text-xs text-muted-foreground">No new eligible purchases ≥$100K, verified clusters or recorded phase changes observed.</p> : <>
            {change.newPurchases.toSorted((a, b) => b.value! - a.value! || a.eventId.localeCompare(b.eventId)).map((event) => <p className="mt-2 text-xs leading-5" key={event.eventId}><span className="text-emerald-200">New purchase · {money(event.value, true)}</span> · {event.transactionDate} · {event.owners.map((owner) => owners.get(owner.ownerCik) ?? `CIK ${owner.ownerCik}`).join(', ')} · <a className="underline" href={event.sourceUrl} target="_blank" rel="noreferrer">SEC</a></p>)}
            {change.newClusters.map((cluster) => <p className="mt-2 text-xs text-emerald-200" key={cluster.clusterId}>New cluster evidence · {cluster.ownerCiks.length} reporting owners · {cluster.newEventIds.length} newly available purchase{cluster.newEventIds.length === 1 ? '' : 's'}</p>)}
            {change.stateChange && <p className="mt-2 text-xs">Recorded phase: {reasonText(change.stateChange.from)} → {reasonText(change.stateChange.to)} · {instant(change.stateChange.changedAt, timezone)}</p>}
          </>}
      </li>;
    })}</ul>
  </details>;
}
