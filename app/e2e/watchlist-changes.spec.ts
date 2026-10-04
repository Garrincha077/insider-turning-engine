import { expect, test } from '@playwright/test';
import fixture from './fixtures/research-v2.json' with { type: 'json' };
import { buildWatchlistChanges, createWatchlistBaseline, isWatchlistBaseline } from '../lib/watchlist-changes';
import type { EconomicEvent, ResearchSnapshot } from '../lib/research-v2';

const cik = '0001999001';
const watched = [cik];
const currentTime = '2026-09-01T21:00:00Z';
const activityTime = '2026-09-01T20:00:00Z';

function pair(): { prior: ResearchSnapshot; current: ResearchSnapshot } {
  const prior = structuredClone(fixture) as unknown as ResearchSnapshot;
  prior.researchScores[0].state = 'FALLING';
  const current = structuredClone(prior);
  current.runId = 'run_research_fixture_002';
  current.asOf = currentTime;
  current.researchScores[0].runId = current.runId;
  current.researchScores[0].asOf = current.asOf;
  return { prior, current };
}

function purchase(overrides: Partial<EconomicEvent> = {}): EconomicEvent {
  return { ...structuredClone(fixture.economicTransactions[0]) as EconomicEvent,
    eventId: 'new-purchase', accession: '0001234567-26-000003', transactionDate: '2026-09-01',
    knownAt: activityTime, acceptedAt: activityTime, value: 100_000, shares: 10_000, price: 10,
    ...overrides };
}

function newCluster(current: ResearchSnapshot, event: EconomicEvent) {
  const previous = current.clusters[0];
  return { ...previous, clusterId: 'new-cluster', end: event.transactionDate,
    eventIds: [...previous.eventIds, event.eventId], purchaseValue: previous.purchaseValue + (event.value ?? 0) };
}

test('new purchases respect the inclusive $100k threshold, stable IDs and joint-owner economic grain', () => {
  const { prior, current } = pair();
  const event = purchase();
  current.economicTransactions.push(event, structuredClone(event), purchase({ eventId: 'too-small', value: 99_999.99 }));
  const changes = buildWatchlistChanges(current, prior, watched).get(cik)!;
  expect(changes.baselineStatus).toBe('AVAILABLE');
  expect(changes.newPurchases).toHaveLength(1);
  expect(changes.newPurchases[0].value).toBe(100_000);
  expect(changes.newPurchases[0].owners).toEqual(event.owners);
  expect(changes.newPurchases[0].owners).toHaveLength(2);
  expect(changes.newPurchases[0].sourceUrl).toBe(event.sourceUrl);
  expect(changes.stateChange).toBeNull();
});

test('older knowledge or acceptance timestamps make a newly exported row a backfill, not new activity', () => {
  const { prior, current } = pair();
  const rows = [
    purchase({ eventId: 'older-both', knownAt: prior.asOf, acceptedAt: prior.asOf }),
    purchase({ eventId: 'older-knowledge', knownAt: prior.asOf }),
    purchase({ eventId: 'older-acceptance', acceptedAt: prior.asOf }),
  ];
  current.economicTransactions.push(...rows);
  current.clusters.push(...rows.map((event) => newCluster(current, event)));
  const changes = buildWatchlistChanges(current, prior, watched).get(cik)!;
  expect(changes.newPurchases).toEqual([]);
  expect(changes.newClusters).toEqual([]);
});

test('availability checks exclude future rows before deduplication and accept the current timestamp boundary', () => {
  const { prior, current } = pair();
  const event = purchase({ knownAt: currentTime, acceptedAt: currentTime });
  current.economicTransactions.unshift({ ...event, knownAt: '2026-09-01T21:00:01Z' });
  current.economicTransactions.push(event,
    purchase({ eventId: 'future-acceptance', acceptedAt: '2026-09-01T21:00:01Z' }),
    purchase({ eventId: 'future-transaction', transactionDate: '2026-09-02' }),
  );
  expect(buildWatchlistChanges(current, prior, watched).get(cik)!.newPurchases.map((row) => row.eventId)).toEqual([event.eventId]);
});

test('a purchase already in the predecessor cannot become new through changed export timestamps', () => {
  const { prior, current } = pair();
  current.economicTransactions[0] = purchase({ eventId: prior.economicTransactions[0].eventId });
  expect(buildWatchlistChanges(current, prior, watched).get(cik)!.newPurchases).toEqual([]);
});

test('only effective eligible qualified non-derivative buys enter new purchase comparisons', () => {
  const { prior, current } = pair();
  current.economicTransactions.push(
    purchase({ eventId: 'derivative', table: 'DERIVATIVE' }),
    purchase({ eventId: 'sale', side: 'SELL' }),
    purchase({ eventId: 'unqualified', qualified: false }),
    purchase({ eventId: 'ineligible', aggregateEligible: false }),
    purchase({ eventId: 'unavailable-value', value: null }),
    purchase({ eventId: 'invalid-value', value: Number.NaN }),
  );
  expect(buildWatchlistChanges(current, prior, watched).get(cik)!.newPurchases).toEqual([]);
});

test('new verified cluster memberships require new underlying purchases, including purchases below $100k', () => {
  const { prior, current } = pair();
  const event = purchase({ eventId: 'small-cluster-member', value: 50_000 });
  current.economicTransactions.push(event);
  const cluster = newCluster(current, event);
  current.clusters = [cluster, { ...cluster, clusterId: 'regenerated-id', eventIds: [...cluster.eventIds].reverse() }];
  const changes = buildWatchlistChanges(current, prior, watched).get(cik)!;
  expect(changes.newPurchases).toEqual([]);
  expect(changes.newClusters).toHaveLength(1);
  expect(changes.newClusters[0].newEventIds).toEqual([event.eventId]);
  expect(changes.newClusters[0].eventIds).toEqual(cluster.eventIds);
  expect(changes.newClusters[0].ownerCiks).toEqual(cluster.ownerCiks);
  expect(changes.newClusters[0].purchaseValue).toBe(52_000);
});

test('cluster ID changes, member ordering and regrouped old purchases do not fabricate new clusters', () => {
  const { prior, current } = pair();
  const cluster = current.clusters[0];
  current.clusters = [
    { ...cluster, clusterId: 'new-id-only', eventIds: [...cluster.eventIds].reverse() },
    { ...cluster, clusterId: 'old-row-regrouped', eventIds: [cluster.eventIds[0]] },
    { ...cluster, clusterId: 'broken-reference', eventIds: ['not-exported'] },
  ];
  expect(buildWatchlistChanges(current, prior, watched).get(cik)!.newClusters).toEqual([]);
});

test('actual recorded state transitions require established states and a timestamp after the predecessor', () => {
  const { prior, current } = pair();
  current.researchScores[0].state = 'EARLY_TURN';
  current.researchScores[0].stateChangedAt = currentTime;
  expect(buildWatchlistChanges(current, prior, watched).get(cik)!.stateChange).toEqual({
    from: 'FALLING', to: 'EARLY_TURN', changedAt: currentTime,
  });
  for (const at of [null, prior.asOf, '2026-09-01T21:00:01Z', 'invalid']) {
    current.researchScores[0].stateChangedAt = at;
    expect(buildWatchlistChanges(current, prior, watched).get(cik)!.stateChange).toBeNull();
  }
  current.researchScores[0].stateChangedAt = activityTime;
  prior.researchScores[0].state = 'UNKNOWN';
  expect(buildWatchlistChanges(current, prior, watched).get(cik)!.stateChange).toBeNull();
  prior.researchScores = [];
  expect(buildWatchlistChanges(current, prior, watched).get(cik)!.stateChange).toBeNull();
});

test('unchanged states and mixed score lineage do not create state transitions', () => {
  const { prior, current } = pair();
  current.researchScores[0].stateChangedAt = activityTime;
  expect(buildWatchlistChanges(current, prior, watched).get(cik)!.stateChange).toBeNull();
  current.researchScores[0].state = 'EARLY_TURN';
  current.researchScores[0].asOf = prior.asOf;
  expect(buildWatchlistChanges(current, prior, watched).get(cik)!.stateChange).toBeNull();
});

test('cross-version predecessors cannot report methodology changes as daily watchlist changes', () => {
  const { prior, current } = pair();
  const event = purchase();
  current.economicTransactions.push(event);
  current.clusters.push(newCluster(current, event));
  current.scoreVersion = 'scoring.v2';
  current.researchScores[0].scoreVersion = current.scoreVersion;
  current.researchScores[0].state = 'EARLY_TURN';
  current.researchScores[0].stateChangedAt = activityTime;
  const baseline = createWatchlistBaseline(prior, watched);
  expect(baseline.scoreVersion).toBe(prior.scoreVersion);
  for (const predecessor of [prior, baseline]) {
    const changes = buildWatchlistChanges(current, predecessor, watched).get(cik)!;
    expect(changes.baselineStatus).toBe('UNAVAILABLE');
    expect(changes.reason).toContain('different score version');
    expect(changes.newPurchases).toEqual([]);
    expect(changes.newClusters).toEqual([]);
    expect(changes.stateChange).toBeNull();
  }
});

test('same-run replay is empty and missing or invalid chronology reports an unavailable baseline', () => {
  const { prior, current } = pair();
  const replay = buildWatchlistChanges(prior, prior, watched).get(cik)!;
  expect(replay).toEqual({ baselineStatus: 'AVAILABLE', reason: null, newPurchases: [], newClusters: [], stateChange: null });
  for (const predecessor of [null, current]) {
    const changes = buildWatchlistChanges(prior, predecessor, watched).get(cik)!;
    expect(changes.baselineStatus).toBe('UNAVAILABLE');
    expect(changes.newPurchases).toEqual([]);
    expect(changes.stateChange).toBeNull();
  }
  current.runId = prior.runId;
  expect(buildWatchlistChanges(current, prior, watched).get(cik)!.baselineStatus).toBe('UNAVAILABLE');
  current.runId = 'new-run'; current.asOf = prior.asOf;
  expect(buildWatchlistChanges(current, prior, watched).get(cik)!.baselineStatus).toBe('UNAVAILABLE');
  current.asOf = 'invalid';
  expect(buildWatchlistChanges(current, prior, watched).get(cik)!.baselineStatus).toBe('UNAVAILABLE');
});

test('issuer holds in either publication suppress all purchase, cluster and state comparisons', () => {
  const holds: Array<(snapshot: ResearchSnapshot) => void> = [
    (snapshot) => { snapshot.companies[0].identityStatus = 'UNRESOLVED'; },
    (snapshot) => { snapshot.companies[0].insiderStatus = 'SOURCE_QUARANTINE'; },
    (snapshot) => { snapshot.companies[0].insiderStatus = 'UNRESOLVED_AMENDMENT'; },
    (snapshot) => { snapshot.companies[0].basis[0].coverage = 'BLOCKED'; },
    (snapshot) => { snapshot.coverage.unresolvedAmendmentIssuers = [cik]; },
    (snapshot) => { snapshot.economicTransactions[0].processing = 'UNRESOLVED_AMENDMENT'; },
  ];
  for (const hold of holds) for (const side of ['prior', 'current'] as const) {
    const publications = pair();
    const event = purchase();
    publications.current.economicTransactions.push(event);
    publications.current.clusters.push(newCluster(publications.current, event));
    publications.current.researchScores[0].state = 'EARLY_TURN';
    publications.current.researchScores[0].stateChangedAt = activityTime;
    hold(publications[side]);
    const changes = buildWatchlistChanges(publications.current, publications.prior, watched).get(cik)!;
    expect(changes.baselineStatus).toBe('SUPPRESSED');
    expect(changes.newPurchases).toEqual([]);
    expect(changes.newClusters).toEqual([]);
    expect(changes.stateChange).toBeNull();
  }
});

test('compact baselines serialize only watched issuer facts and compare identically to full predecessors', () => {
  const { prior, current } = pair();
  current.economicTransactions.push(purchase());
  current.researchScores[0].state = 'EARLY_TURN'; current.researchScores[0].stateChangedAt = activityTime;
  const baseline = createWatchlistBaseline(prior, watched);
  expect(baseline.scoreVersion).toBe(prior.scoreVersion);
  const saved: unknown = JSON.parse(JSON.stringify(baseline));
  expect(isWatchlistBaseline(saved)).toBe(true);
  if (!isWatchlistBaseline(saved)) throw new Error('Expected a valid serialized baseline');
  expect(buildWatchlistChanges(current, saved, watched)).toEqual(buildWatchlistChanges(current, prior, watched));
  expect(Object.keys(saved.issuers)).toEqual(watched);
  expect(saved.issuers[cik].purchases[0]).toEqual({ eventId: prior.economicTransactions[0].eventId,
    knownAt: prior.economicTransactions[0].knownAt, acceptedAt: prior.economicTransactions[0].acceptedAt });
  expect(JSON.stringify(saved)).not.toMatch(/companySeries|currentPrice|sourceUrl|purchaseValue|owners|total/);
  expect(buildWatchlistChanges(current, createWatchlistBaseline(prior, []), watched).get(cik)!.baselineStatus).toBe('UNAVAILABLE');
});

test('local baseline validation rejects malformed clocks, duplicate IDs, broken memberships and extra source data', () => {
  const { prior } = pair();
  const baseline = createWatchlistBaseline(prior, watched);
  expect(isWatchlistBaseline(null)).toBe(false);
  expect(isWatchlistBaseline({ ...baseline, version: 2 })).toBe(false);
  expect(isWatchlistBaseline({ ...baseline, scoreVersion: '' })).toBe(false);
  expect(isWatchlistBaseline({ ...baseline, scoreVersion: undefined })).toBe(false);
  const { scoreVersion: _scoreVersion, ...withoutScoreVersion } = baseline;
  expect(isWatchlistBaseline(withoutScoreVersion)).toBe(false);
  expect(isWatchlistBaseline({ ...baseline, companySeries: [] })).toBe(false);
  const corruptions: Array<(saved: ReturnType<typeof createWatchlistBaseline>) => void> = [
    (saved) => { saved.asOf = 'invalid'; },
    (saved) => { saved.issuers[cik].purchases[0].knownAt = currentTime; },
    (saved) => { saved.issuers[cik].purchases.push(saved.issuers[cik].purchases[0]); },
    (saved) => { saved.issuers[cik].clusters = [['not-exported']]; },
    (saved) => { saved.issuers[cik].state!.asOf = currentTime; },
    (saved) => { saved.issuers[cik].availability = 'SUPPRESSED'; },
  ];
  for (const corrupt of corruptions) {
    const saved = structuredClone(baseline);
    corrupt(saved);
    expect(isWatchlistBaseline(saved)).toBe(false);
  }
});

test('comparison does not mutate publications and uses CIK despite ticker changes', () => {
  const { prior, current } = pair();
  current.companies[0].ticker = 'RENAMED';
  current.economicTransactions.push(purchase());
  const before = structuredClone({ prior, current });
  const changes = buildWatchlistChanges(current, prior, [cik, cik, 'ACME']);
  expect([...changes.keys()]).toEqual([cik]);
  expect(changes.get(cik)!.newPurchases).toHaveLength(1);
  expect({ prior, current }).toEqual(before);
});
