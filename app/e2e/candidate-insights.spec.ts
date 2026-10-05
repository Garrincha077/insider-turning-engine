import { expect, test } from '@playwright/test';
import fixture from './fixtures/research-v2.json' with { type: 'json' };
import { buildCandidateInsights } from '../lib/candidate-insights';
import { sampleDashboardData, type DashboardData } from '../lib/dashboard-data';
import type { EconomicEvent, ResearchSnapshot } from '../lib/research-v2';

const cik = '0001999001';

function dashboard(): DashboardData & { research: ResearchSnapshot } {
  const research = structuredClone(fixture) as unknown as ResearchSnapshot;
  for (const window of research.companies[0].basis) window.coverage = 'OBSERVED_COMPLETE_SEC_WINDOW';
  return { ...sampleDashboardData, research, candidates: [{ ...sampleDashboardData.candidates[0],
    issuerCik: cik, ticker: 'ACME', currentPrice: 999, cluster: 100 }], filings: [], companySeries: [] };
}

function event(overrides: Partial<EconomicEvent>): EconomicEvent {
  return { ...structuredClone(fixture.economicTransactions[0]) as EconomicEvent, ...overrides };
}

test('joint reporting owners preserve economic-event dollars and distinct reporting identities', () => {
  const data = dashboard();
  const insight = buildCandidateInsights(data).get(cik)!;
  expect(insight.buyValue90d).toBe(2000);
  expect(insight.buyCount90d).toBe(2);
  expect(insight.reportingOwnerCount90d).toBe(3);
  expect(insight.verifiedClusterCount30d).toBe(1);
  expect(insight.lastPurchaseDate).toBe('2026-08-20');
  expect(insight.summary).toContain('2 observed qualified purchases totaling $2K in 90D');
  expect(insight.summary).toContain('3 distinct reporting owners');
  expect(insight.summary).not.toMatch(/independent|JOINT_OWNER|score|cluster/i);
  expect(insight.cautions.join(' ')).toContain('do not establish independent buying decisions');
  // Neither candidate prices nor score magnitude manufacture facts.
  expect(insight.drawdownPct).toBe(0);
  data.research.clusters = [];
  expect(buildCandidateInsights(data).get(cik)!.verifiedClusterCount30d).toBe(0);
});

test('stable event and cluster IDs deduplicate repeated exported facts', () => {
  const data = dashboard();
  const before = buildCandidateInsights(data);
  data.research.economicTransactions.push(...structuredClone(data.research.economicTransactions));
  data.research.clusters.push(structuredClone(data.research.clusters[0]));
  expect(buildCandidateInsights(data)).toEqual(before);
});

test('reported-price review never corrects purchase facts and missing references are not zero flags', () => {
  const data = dashboard();
  data.research.economicTransactions[0].price = 11_000;
  const reviewed = buildCandidateInsights(data).get(cik)!;
  expect(reviewed.priceReviewCount90d).toBe(1);
  expect(reviewed.buyValue90d).toBe(2000);
  expect(reviewed.cautions.join(' ')).toContain('not proof of an error');
  for (const price of [null, 0, -1, NaN]) {
    data.research.companies[0].currentPrice = price;
    const unavailable = buildCandidateInsights(data).get(cik)!;
    expect(unavailable.priceReviewCount90d).toBeNull();
    expect(unavailable.buyValue90d).toBe(2000);
  }
});

test('future transactions, knowledge, acceptance, clusters and prices leave current facts invariant', () => {
  const data = dashboard();
  const before = buildCandidateInsights(data);
  // A future duplicate preceding the valid copy cannot consume its stable ID.
  data.research.economicTransactions.unshift(event({ knownAt: '2026-08-31T21:00:01Z', value: 900000 }));
  data.research.economicTransactions.push(
    event({ eventId: 'future-date', transactionDate: '2026-09-01' }),
    event({ eventId: 'future-accepted', acceptedAt: '2026-08-31T21:00:01Z' }),
    event({ eventId: 'future-known', knownAt: '2026-08-31T21:00:01Z' }),
    event({ eventId: 'future-amendment', knownAt: '2026-09-01T00:00:00Z', processing: 'UNRESOLVED_AMENDMENT' }),
  );
  data.research.clusters.push({ ...data.research.clusters[0], clusterId: 'future-cluster', start: '2026-09-01', end: '2026-09-01', eventIds: ['future-date'] });
  data.research.clusters.push({ ...data.research.clusters[0], clusterId: 'future-member-cluster', eventIds: ['future-accepted'] });
  data.research.companySeries.push({ ...data.research.companySeries[0], date: '2026-09-01', price: 100000 });
  expect(buildCandidateInsights(data)).toEqual(before);
});

test('90D uses inclusive calendar-date boundaries and the UTC snapshot date', () => {
  const data = dashboard();
  data.research.asOf = '2026-09-01T01:00:00+04:00'; // 31 August in UTC.
  data.research.economicTransactions = [
    event({ eventId: 'first-day', transactionDate: '2026-06-03', value: 10 }),
    event({ eventId: 'last-day', transactionDate: '2026-08-31', value: 20, knownAt: data.research.asOf, acceptedAt: data.research.asOf }),
    event({ eventId: 'too-old', transactionDate: '2026-06-02', value: 300 }),
    event({ eventId: 'tomorrow', transactionDate: '2026-09-01', value: 400 }),
    event({ eventId: 'sale', transactionDate: '2026-08-31', side: 'SELL', value: 500 }),
    event({ eventId: 'derivative', transactionDate: '2026-08-31', table: 'DERIVATIVE', value: 600 }),
    event({ eventId: 'unqualified', qualified: false, value: 700 }),
    event({ eventId: 'ineligible', aggregateEligible: false, value: 800 }),
  ];
  data.research.clusters = [];
  const insight = buildCandidateInsights(data).get(cik)!;
  expect(insight.buyValue90d).toBe(30);
  expect(insight.buyCount90d).toBe(2);
  expect(insight.reportingOwnerCount90d).toBe(2);
  expect(insight.lastPurchaseDate).toBe('2026-08-31');
});

test('blocked, unresolved and quarantined issuers withhold insider facts rather than zero them', () => {
  const holds: Array<(research: ResearchSnapshot) => void> = [
    (research) => { research.companies[0].identityStatus = 'UNRESOLVED'; },
    (research) => { research.companies[0].insiderStatus = 'UNRESOLVED_AMENDMENT'; },
    (research) => { research.companies[0].insiderStatus = 'SOURCE_QUARANTINE'; },
    (research) => { research.companies[0].basis[1].coverage = 'BLOCKED'; },
    (research) => { research.coverage.unresolvedAmendmentIssuers = [cik]; },
    (research) => { research.economicTransactions.push(event({ eventId: 'amendment', processing: 'UNRESOLVED_AMENDMENT', aggregateEligible: false })); },
  ];
  for (const hold of holds) {
    const data = dashboard();
    hold(data.research);
    const insight = buildCandidateInsights(data).get(cik)!;
    expect(insight.buyValue90d).toBeNull();
    expect(insight.buyCount90d).toBeNull();
    expect(insight.reportingOwnerCount90d).toBeNull();
    expect(insight.verifiedClusterCount30d).toBeNull();
    expect(insight.lastPurchaseDate).toBeNull();
    expect(insight.priceReviewCount90d).toBeNull();
    expect(insight.drawdownPct).toBe(0);
    expect(insight.summary).toContain('Qualified purchase facts are unavailable');
    expect(insight.cautions.join(' ')).toMatch(/withheld/);
  }
});

test('incomplete windows describe observed facts and do not invent a zero-purchase conclusion', () => {
  const data = dashboard();
  for (const window of data.research.companies[0].basis) window.coverage = 'PARTIAL';
  const insight = buildCandidateInsights(data).get(cik)!;
  expect(insight.buyValue90d).toBe(2000);
  expect(insight.summary).toContain('observed qualified purchases');
  expect(insight.cautions.join(' ')).toContain('Partial observed SEC window');
  expect(insight.cautions.join(' ')).toContain('2026-06-03–2026-08-31');
  expect(insight.cautions.join(' ')).toContain('observed 30D SEC window is partial');
  data.research.economicTransactions = [];
  data.research.clusters = [];
  const missing = buildCandidateInsights(data).get(cik)!;
  expect(missing.buyValue90d).toBeNull();
  expect(missing.buyCount90d).toBeNull();
  expect(missing.reportingOwnerCount90d).toBeNull();
  expect(missing.summary).not.toContain('No qualified purchases');
  // A complete exported window supports a factual observed zero.
  for (const window of data.research.companies[0].basis) window.coverage = 'OBSERVED_COMPLETE_SEC_WINDOW';
  const complete = buildCandidateInsights(data).get(cik)!;
  expect(complete.buyCount90d).toBe(0);
  expect(complete.buyValue90d).toBe(0);
  expect(complete.reportingOwnerCount90d).toBe(0);
});

test('drawdown uses the latest dated exported price against its available observed high', () => {
  const data = dashboard();
  const point = data.research.companySeries[0];
  data.research.companySeries = [
    { ...point, date: '2026-08-31', price: 75 },
    { ...point, date: '2026-08-01', price: 100 },
    { ...point, date: '2026-08-20', price: 60 },
    { ...point, date: '2026-09-01', price: 200 },
    { ...point, date: 'not-a-date', price: 10000 },
    { ...point, date: '2026-07-31', price: Number.NaN },
  ];
  const insight = buildCandidateInsights(data).get(cik)!;
  expect(insight.drawdownPct).toBe(-25);
  expect(insight.priceWindow).toEqual({ start: '2026-08-01', end: '2026-08-31' });
  expect(insight.summary).toContain('25% below the observed high');
  expect(insight.cautions.join(' ')).toContain('Observed price window: 2026-08-01–2026-08-31');
  expect(insight.summary).not.toMatch(/52-week|52W/);
  data.research.companySeries = [];
  expect(buildCandidateInsights(data).get(cik)!.drawdownPct).toBeNull();
});

test('clusters must be supplied, recent and supported by available qualified purchases', () => {
  const data = dashboard();
  const template = data.research.clusters[0];
  data.research.clusters = [
    { ...template, clusterId: 'too-old', start: '2026-08-01', end: '2026-08-20' },
    { ...template, clusterId: 'missing-event', eventIds: ['not-exported'] },
    template,
  ];
  expect(buildCandidateInsights(data).get(cik)!.verifiedClusterCount30d).toBe(1);
  data.research.economicTransactions[0].qualified = false;
  expect(buildCandidateInsights(data).get(cik)!.verifiedClusterCount30d).toBe(0);
});

test('missing purchase values stay unavailable while observed event and reporter counts remain factual', () => {
  const data = dashboard();
  data.research.economicTransactions[0].value = null;
  const insight = buildCandidateInsights(data).get(cik)!;
  expect(insight.buyValue90d).toBeNull();
  expect(insight.buyCount90d).toBe(2);
  expect(insight.reportingOwnerCount90d).toBe(3);
  expect(insight.summary).not.toContain('$1K');
  expect(insight.cautions.join(' ')).toContain('purchase dollar total is withheld');
});

test('a stale-source state hold is disclosed without erasing still-available SEC facts', () => {
  const data = dashboard();
  data.research.researchScores[0].reasons = ['STALE_DATA_HOLD'];
  const insight = buildCandidateInsights(data).get(cik)!;
  expect(insight.buyValue90d).toBe(2000);
  expect(insight.cautions).toContain('A required source is stale; the recorded engine state is held.');
  expect(insight.summary).not.toContain('STALE_DATA_HOLD');
});

test('v1 score reasons and filing amounts cannot supply missing canonical facts', () => {
  const data: DashboardData = { ...sampleDashboardData,
    candidates: [{ ...sampleDashboardData.candidates[0], ticker: 'KNOWN', issuerCik: cik },
      { ...sampleDashboardData.candidates[1], ticker: 'FALLBACK', issuerCik: '' }],
    filings: [{ ...sampleDashboardData.filings[0], ticker: 'KNOWN' },
      { ...sampleDashboardData.filings[0], ticker: 'TAPE_ONLY' }],
  };
  const insights = buildCandidateInsights(data);
  expect([...insights.keys()]).toEqual([cik, 'FALLBACK', 'TAPE_ONLY']);
  for (const insight of insights.values()) {
    expect(insight.buyValue90d).toBeNull();
    expect(insight.buyCount90d).toBeNull();
    expect(insight.reportingOwnerCount90d).toBeNull();
    expect(insight.verifiedClusterCount30d).toBeNull();
    expect(insight.drawdownPct).toBeNull();
    expect(insight.priceWindow).toBeNull();
    expect(insight.lastPurchaseDate).toBeNull();
    expect(insight.summary).toContain('unavailable in this v1 snapshot');
  }
});
