import type { EconomicEvent, ResearchSnapshot } from './research-v2';

const recordedStates = ['FALLING', 'INSIDER_ACCUMULATION', 'BASE_FORMING', 'EARLY_TURN', 'CONFIRMED_TURN'] as const;
type RecordedState = typeof recordedStates[number];
type Cluster = ResearchSnapshot['clusters'][number];
export type WatchlistIssuerBaseline = {
  availability: 'AVAILABLE' | 'SUPPRESSED';
  purchases: Array<{ eventId: string; knownAt: string; acceptedAt: string }>;
  clusters: string[][];
  state: { state: RecordedState; asOf: string } | null;
};
export type WatchlistBaseline = {
  version: 1; runId: string; asOf: string; scoreVersion: string;
  issuers: Record<string, WatchlistIssuerBaseline>;
};
export type WatchlistIssuerChanges = {
  baselineStatus: 'AVAILABLE' | 'UNAVAILABLE' | 'SUPPRESSED';
  reason: string | null;
  newPurchases: EconomicEvent[];
  newClusters: Array<Cluster & { newEventIds: string[] }>;
  stateChange: { from: RecordedState; to: RecordedState; changedAt: string } | null;
};

function time(value: unknown): number {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? Date.parse(value) : Number.NaN;
}
function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value != null && !Array.isArray(value);
}
function keys(value: Record<string, unknown>, allowed: string[]): boolean {
  return Object.keys(value).every((key) => allowed.includes(key));
}
function identifier(value: unknown): value is string { return typeof value === 'string' && value.length > 0 && value.length <= 256; }
function state(value: unknown): value is RecordedState { return typeof value === 'string' && recordedStates.some((item) => item === value); }
function membership(eventIds: string[]): string { return JSON.stringify([...eventIds].sort()); }

/** Validate local storage without importing the research schema validator or its AJV runtime. */
export function isWatchlistBaseline(value: unknown): value is WatchlistBaseline {
  if (!object(value) || !keys(value, ['version', 'runId', 'asOf', 'scoreVersion', 'issuers']) || value.version !== 1
    || !identifier(value.runId) || !identifier(value.scoreVersion) || !Number.isFinite(time(value.asOf)) || !object(value.issuers)) return false;
  const asOf = time(value.asOf);
  const seenEvents = new Set<string>();
  for (const [cik, issuer] of Object.entries(value.issuers)) {
    if (!/^\d{10}$/.test(cik) || !object(issuer) || !keys(issuer, ['availability', 'purchases', 'clusters', 'state'])
      || !['AVAILABLE', 'SUPPRESSED'].includes(String(issuer.availability)) || !Array.isArray(issuer.purchases) || !Array.isArray(issuer.clusters)) return false;
    const eventIds = new Set<string>();
    for (const purchase of issuer.purchases) {
      if (!object(purchase) || !keys(purchase, ['eventId', 'knownAt', 'acceptedAt']) || !identifier(purchase.eventId)
        || seenEvents.has(purchase.eventId) || !Number.isFinite(time(purchase.knownAt)) || !Number.isFinite(time(purchase.acceptedAt))
        || time(purchase.knownAt) > asOf || time(purchase.acceptedAt) > asOf) return false;
      eventIds.add(purchase.eventId); seenEvents.add(purchase.eventId);
    }
    const memberships = new Set<string>();
    for (const cluster of issuer.clusters) {
      if (!Array.isArray(cluster) || !cluster.length || !cluster.every((id) => identifier(id) && eventIds.has(id))
        || new Set(cluster).size !== cluster.length || memberships.has(membership(cluster))) return false;
      memberships.add(membership(cluster));
    }
    if (issuer.state !== null && (!object(issuer.state) || !keys(issuer.state, ['state', 'asOf'])
      || !state(issuer.state.state) || time(issuer.state.asOf) !== asOf)) return false;
    if (issuer.availability === 'SUPPRESSED' && (issuer.purchases.length || issuer.clusters.length || issuer.state !== null)) return false;
  }
  return true;
}

function indexSnapshot(snapshot: ResearchSnapshot, watchedIssuerCiks: readonly string[]) {
  const watched = new Set(watchedIssuerCiks.filter((cik) => /^\d{10}$/.test(cik)));
  const at = time(snapshot.asOf);
  const day = Number.isFinite(at) ? new Date(at).toISOString().slice(0, 10) : '';
  const issuers: WatchlistBaseline['issuers'] = Object.fromEntries([...watched].map((cik) => [cik,
    { availability: 'SUPPRESSED', purchases: [], clusters: [], state: null } satisfies WatchlistIssuerBaseline]));
  const held = new Set(snapshot.coverage.unresolvedAmendmentIssuers);
  for (const company of snapshot.companies) if (watched.has(company.issuerCik)) {
    const available = company.identityStatus === 'RESOLVED' && company.insiderStatus === 'AVAILABLE'
      && !company.basis.some((window) => window.coverage === 'BLOCKED') && !held.has(company.issuerCik);
    issuers[company.issuerCik].availability = available ? 'AVAILABLE' : 'SUPPRESSED';
  }
  const events = new Map<string, EconomicEvent>();
  const seen = new Set<string>();
  for (const event of snapshot.economicTransactions) {
    if (!watched.has(event.issuerCik) || !Number.isFinite(at) || !Number.isFinite(time(event.knownAt))
      || !Number.isFinite(time(event.acceptedAt)) || time(event.knownAt) > at || time(event.acceptedAt) > at
      || !/^\d{4}-\d{2}-\d{2}$/.test(event.transactionDate) || event.transactionDate > day) continue;
    if (event.processing === 'UNRESOLVED_AMENDMENT') issuers[event.issuerCik].availability = 'SUPPRESSED';
    if (!identifier(event.eventId) || seen.has(event.eventId)) continue;
    seen.add(event.eventId);
    if (event.table !== 'NON_DERIVATIVE' || event.side !== 'BUY' || event.processing !== 'EFFECTIVE'
      || !event.qualified || !event.aggregateEligible) continue;
    events.set(event.eventId, event);
    issuers[event.issuerCik].purchases.push({ eventId: event.eventId, knownAt: event.knownAt, acceptedAt: event.acceptedAt });
  }
  for (const score of snapshot.researchScores) if (watched.has(score.issuerCik) && state(score.state)
    && score.runId === snapshot.runId && score.scoreVersion === snapshot.scoreVersion && time(score.asOf) === at) {
    issuers[score.issuerCik].state = { state: score.state, asOf: score.asOf };
  }
  const clusters = new Map<string, Cluster[]>();
  const clusterMemberships = new Map<string, Set<string>>();
  for (const cluster of snapshot.clusters) {
    if (!watched.has(cluster.issuerCik) || !cluster.eventIds.length || cluster.start > cluster.end || cluster.end > day
      || new Set(cluster.eventIds).size !== cluster.eventIds.length || !cluster.eventIds.every((id) => {
        const event = events.get(id);
        return event?.issuerCik === cluster.issuerCik && event.transactionDate >= cluster.start && event.transactionDate <= cluster.end;
      })) continue;
    const signature = membership(cluster.eventIds);
    const signatures = clusterMemberships.get(cluster.issuerCik) ?? new Set<string>();
    if (signatures.has(signature)) continue;
    signatures.add(signature); clusterMemberships.set(cluster.issuerCik, signatures);
    issuers[cluster.issuerCik].clusters.push([...cluster.eventIds]);
    const rows = clusters.get(cluster.issuerCik) ?? [];
    rows.push(cluster); clusters.set(cluster.issuerCik, rows);
  }
  for (const issuer of Object.values(issuers)) if (issuer.availability === 'SUPPRESSED') {
    issuer.purchases = []; issuer.clusters = []; issuer.state = null;
  }
  return { baseline: { version: 1, runId: snapshot.runId, asOf: snapshot.asOf, scoreVersion: snapshot.scoreVersion, issuers } satisfies WatchlistBaseline, events, clusters };
}

/** Only facts needed for the next local comparison; no prices, company series or score components. */
export function createWatchlistBaseline(snapshot: ResearchSnapshot, watchedIssuerCiks: readonly string[]): WatchlistBaseline {
  return indexSnapshot(snapshot, watchedIssuerCiks).baseline;
}

function empty(baselineStatus: WatchlistIssuerChanges['baselineStatus'], reason: string | null): WatchlistIssuerChanges {
  return { baselineStatus, reason, newPurchases: [], newClusters: [], stateChange: null };
}

/** Inputs are verified publications; a saved predecessor additionally passes the compact validation guard. */
export function buildWatchlistChanges(
  current: ResearchSnapshot,
  predecessor: ResearchSnapshot | WatchlistBaseline | null | undefined,
  watchedIssuerCiks: readonly string[],
): Map<string, WatchlistIssuerChanges> {
  const indexed = indexSnapshot(current, watchedIssuerCiks);
  const prior = predecessor && 'version' in predecessor ? predecessor
    : predecessor ? createWatchlistBaseline(predecessor, watchedIssuerCiks) : null;
  const results = new Map<string, WatchlistIssuerChanges>();
  const now = time(current.asOf);
  const validPrior = isWatchlistBaseline(prior);
  const before = validPrior ? time(prior.asOf) : Number.NaN;
  const replay = validPrior && prior.runId === current.runId && before === now;
  const methodologyChanged = validPrior && prior.scoreVersion !== current.scoreVersion;
  const chronologyValid = validPrior && !methodologyChanged && Number.isFinite(now) && (replay || before < now && prior.runId !== current.runId);
  const currentScores = new Map(current.researchScores.map((score) => [score.issuerCik, score]));
  for (const [cik, issuer] of Object.entries(indexed.baseline.issuers)) {
    if (!chronologyValid || !prior) {
      results.set(cik, empty('UNAVAILABLE', methodologyChanged
        ? 'The saved baseline uses a different score version; daily changes are unavailable.'
        : 'An earlier verified local baseline is unavailable.'));
      continue;
    }
    const previous = prior.issuers[cik];
    if (!previous) {
      results.set(cik, empty('UNAVAILABLE', 'This issuer has no saved predecessor.'));
      continue;
    }
    if (issuer.availability === 'SUPPRESSED' || previous.availability === 'SUPPRESSED') {
      results.set(cik, empty('SUPPRESSED', 'Issuer identity, amendments or source quarantine prevent a reliable comparison.'));
      continue;
    }
    const changes = empty('AVAILABLE', null);
    results.set(cik, changes);
    if (replay) continue;
    const oldIds = new Set(previous.purchases.map((purchase) => purchase.eventId));
    const newIds = new Set<string>();
    for (const purchase of issuer.purchases) {
      // A newly exported backfill is not new activity if either availability clock predates the baseline.
      if (oldIds.has(purchase.eventId) || time(purchase.knownAt) <= before || time(purchase.acceptedAt) <= before) continue;
      newIds.add(purchase.eventId);
      const event = indexed.events.get(purchase.eventId)!;
      if (event.value != null && Number.isFinite(event.value) && event.value >= 100_000) changes.newPurchases.push(event);
    }
    const oldMemberships = new Set(previous.clusters.map(membership));
    for (const cluster of indexed.clusters.get(cik) ?? []) {
      const newEventIds = cluster.eventIds.filter((id) => newIds.has(id));
      if (newEventIds.length && !oldMemberships.has(membership(cluster.eventIds))) changes.newClusters.push({ ...cluster, newEventIds });
    }
    const score = currentScores.get(cik);
    const changedAt = time(score?.stateChangedAt);
    if (previous.state && issuer.state && previous.state.state !== issuer.state.state
      && Number.isFinite(changedAt) && changedAt > before && changedAt <= now) {
      changes.stateChange = { from: previous.state.state, to: issuer.state.state, changedAt: score!.stateChangedAt! };
    }
  }
  return results;
}
