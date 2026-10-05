import type { DashboardData } from './dashboard-data';
import type { EconomicEvent, ResearchSnapshot } from './research-v2';
import { metric, money, timestamp } from './research';
import { purchasePriceReviews, reportedPriceCaution } from './reported-price';

export type CandidateInsight = {
  buyValue90d: number | null;
  buyCount90d: number | null;
  reportingOwnerCount90d: number | null;
  verifiedClusterCount30d: number | null;
  drawdownPct: number | null;
  priceWindow: { start: string; end: string } | null;
  lastPurchaseDate: string | null;
  priceReviewCount90d: number | null;
  summary: string;
  cautions: string[];
};

type PurchaseFacts = { value: number; missingValue: boolean; count: number; owners: Set<string>; lastDate: string | null };
type PriceFacts = { start: string; end: string; high: number; latest: number };
type Company = ResearchSnapshot['companies'][number];
const calendarDayMs = 86_400_000;

function dateOnly(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value))
    && new Date(value).toISOString().slice(0, 10) === value;
}

function unavailable(cautions: string[], summary: string): CandidateInsight {
  return { buyValue90d: null, buyCount90d: null, reportingOwnerCount90d: null,
    verifiedClusterCount30d: null, drawdownPct: null, priceWindow: null,
    lastPurchaseDate: null, priceReviewCount90d: null, summary, cautions };
}

function holdCautions(company: Company | undefined, unresolved: Set<string>, cik: string): string[] {
  if (!company) return ['Issuer facts are not exported in this research snapshot.'];
  const cautions: string[] = [];
  if (company.identityStatus !== 'RESOLVED') cautions.push('Issuer identity is unresolved; insider totals are withheld.');
  if (company.insiderStatus === 'SOURCE_QUARANTINE') cautions.push('Source quarantine holds this issuer; insider totals are withheld.');
  if (company.insiderStatus === 'UNRESOLVED_AMENDMENT' || unresolved.has(cik)) cautions.push('An unresolved amendment holds this issuer; insider totals are withheld.');
  if (company.basis.some((window) => window.coverage === 'BLOCKED') && !cautions.length) cautions.push('The exported insider window is blocked; insider totals are withheld.');
  return cautions;
}

function completeWindow(company: Company | undefined, days: 30 | 90, start: string, end: string): boolean {
  return Boolean(company?.basis.some((window) => window.days === days
    && window.coverage === 'OBSERVED_COMPLETE_SEC_WINDOW' && window.start === start && window.end === end));
}

function purchaseSummary(insight: CandidateInsight): string {
  if (insight.buyCount90d == null) return 'Qualified purchase facts are unavailable';
  if (insight.buyCount90d === 0) return 'No qualified purchases were observed in the trailing 90D window';
  const count = insight.buyCount90d;
  const owners = insight.reportingOwnerCount90d;
  return `${count} observed qualified purchase${count === 1 ? '' : 's'}${insight.buyValue90d == null ? '' : ` totaling ${money(insight.buyValue90d, true)}`} in 90D`
    + (owners == null ? '' : `, reported by ${owners} distinct reporting owner${owners === 1 ? '' : 's'}`);
}

/** Index each source once; event dollars remain at the economic-event grain. */
export function buildCandidateInsights(data: DashboardData): Map<string, CandidateInsight> {
  const insights = new Map<string, CandidateInsight>();
  const research = data.research;
  if (!research) {
    const addLegacy = (issuerCik: string | undefined, ticker: string) => {
      const key = issuerCik || ticker;
      if (!insights.has(key)) insights.set(key, unavailable(
        ['v1 does not export verified economic events, reporting-owner identities, clusters, or dated observed price history.'],
        'Qualified purchase and observed price-history facts are unavailable in this v1 snapshot.',
      ));
    };
    const legacyTickers = new Set<string>();
    for (const candidate of data.candidates) {
      addLegacy(candidate.issuerCik, candidate.ticker);
      legacyTickers.add(candidate.ticker);
    }
    for (const filing of data.filings) if (!legacyTickers.has(filing.ticker)) addLegacy(filing.issuerCik, filing.ticker);
    return insights;
  }

  const companies = new Map(research.companies.map((company) => [company.issuerCik, company]));
  const priceReviews = purchasePriceReviews(research, 90);
  const heldSourceIssuers = new Set<string>();
  for (const score of research.researchScores) if (score.reasons.includes('STALE_DATA_HOLD')) heldSourceIssuers.add(score.issuerCik);
  const issuerCiks = new Set(companies.keys());
  for (const candidate of data.candidates) if (candidate.issuerCik) {
    issuerCiks.add(candidate.issuerCik);
    if (candidate.reasons.includes('STALE_DATA_HOLD')) heldSourceIssuers.add(candidate.issuerCik);
  }
  const asOf = timestamp(research.asOf);
  if (!Number.isFinite(asOf)) {
    for (const cik of issuerCiks) insights.set(cik, unavailable(
      ['The snapshot time is unavailable; point-in-time facts cannot be established.'],
      'Qualified purchase and observed price-history facts are unavailable.',
    ));
    return insights;
  }
  const end = new Date(asOf).toISOString().slice(0, 10);
  const midnight = Date.parse(end);
  const start90 = new Date(midnight - 89 * calendarDayMs).toISOString().slice(0, 10);
  const start30 = new Date(midnight - 29 * calendarDayMs).toISOString().slice(0, 10);
  const unresolved = new Set(research.coverage.unresolvedAmendmentIssuers);
  const purchases = new Map<string, PurchaseFacts>();
  const availableEvents = new Map<string, EconomicEvent>();
  const seenEventIds = new Set<string>();

  for (const event of research.economicTransactions) {
    // Discard future observations before deduplication or issuer holds.
    const knownAt = timestamp(event.knownAt);
    const acceptedAt = timestamp(event.acceptedAt);
    if (!Number.isFinite(knownAt) || !Number.isFinite(acceptedAt) || knownAt > asOf || acceptedAt > asOf
      || !dateOnly(event.transactionDate) || event.transactionDate > end) continue;
    if (event.processing === 'UNRESOLVED_AMENDMENT') unresolved.add(event.issuerCik);
    if (!event.eventId || seenEventIds.has(event.eventId)) continue;
    seenEventIds.add(event.eventId);
    if (event.table !== 'NON_DERIVATIVE' || event.side !== 'BUY' || event.processing !== 'EFFECTIVE'
      || !event.qualified || !event.aggregateEligible) continue;
    availableEvents.set(event.eventId, event);
    if (event.transactionDate < start90) continue;
    let facts = purchases.get(event.issuerCik);
    if (!facts) {
      facts = { value: 0, missingValue: false, count: 0, owners: new Set(), lastDate: null };
      purchases.set(event.issuerCik, facts);
    }
    facts.count += 1;
    if (event.value == null || !Number.isFinite(event.value) || event.value < 0) facts.missingValue = true;
    else facts.value += event.value;
    for (const owner of event.owners) facts.owners.add(owner.ownerCik);
    if (facts.lastDate == null || event.transactionDate > facts.lastDate) facts.lastDate = event.transactionDate;
  }

  const clusters = new Map<string, number>();
  const seenClusterIds = new Set<string>();
  for (const cluster of research.clusters) {
    if (!cluster.clusterId || seenClusterIds.has(cluster.clusterId) || !dateOnly(cluster.start) || !dateOnly(cluster.end)
      || cluster.start < start30 || cluster.start > cluster.end || cluster.end > end || !cluster.eventIds.length) continue;
    // Only supplied clusters whose underlying purchases are available are verified.
    if (!cluster.eventIds.every((id) => {
      const event = availableEvents.get(id);
      return event?.issuerCik === cluster.issuerCik && event.transactionDate >= cluster.start && event.transactionDate <= cluster.end;
    })) continue;
    seenClusterIds.add(cluster.clusterId);
    clusters.set(cluster.issuerCik, (clusters.get(cluster.issuerCik) ?? 0) + 1);
  }

  const prices = new Map<string, PriceFacts>();
  for (const row of research.companySeries) {
    if (!dateOnly(row.date) || row.date > end || !Number.isFinite(row.price) || row.price <= 0) continue;
    const facts = prices.get(row.issuerCik);
    if (!facts) prices.set(row.issuerCik, { start: row.date, end: row.date, high: row.price, latest: row.price });
    else {
      if (row.date < facts.start) facts.start = row.date;
      if (row.date > facts.end) { facts.end = row.date; facts.latest = row.price; }
      facts.high = Math.max(facts.high, row.price);
    }
  }

  for (const cik of issuerCiks) {
    const company = companies.get(cik);
    const referenceAvailable = company?.currentPrice != null && Number.isFinite(company.currentPrice) && company.currentPrice > 0;
    const cautions = holdCautions(company, unresolved, cik);
    const held = cautions.length > 0;
    const complete90 = completeWindow(company, 90, start90, end);
    const complete30 = completeWindow(company, 30, start30, end);
    const buys = purchases.get(cik);
    const observedCount = buys?.count ?? 0;
    const hasPurchaseFacts = !held && (observedCount > 0 || complete90);
    const price = prices.get(cik);
    if (heldSourceIssuers.has(cik)) cautions.push('A required source is stale; the recorded engine state is held.');
    if (!held && !complete90) cautions.push(`Partial observed SEC window: 90D totals cover exported qualifying events dated ${start90}–${end}; missing purchases may exist.`);
    if (!held && !complete30) cautions.push('The observed 30D SEC window is partial; exported verified clusters may not cover all activity.');
    if (buys?.missingValue && !held) cautions.push('Some qualifying purchase values are unavailable; the 90D purchase dollar total is withheld.');
    if (!held && priceReviews.has(cik)) cautions.push(reportedPriceCaution);
    if (observedCount > 0 && !held) cautions.push('Distinct reporting owners do not establish independent buying decisions; joint-owner purchases count once.');
    if (price) cautions.push(`Observed price window: ${price.start}–${price.end}; the exported high does not establish a 52-week high.`);
    else cautions.push('Dated observed price history is unavailable.');
    const insight: CandidateInsight = {
      buyValue90d: hasPurchaseFacts && !buys?.missingValue ? buys?.value ?? 0 : null,
      buyCount90d: hasPurchaseFacts ? observedCount : null,
      reportingOwnerCount90d: hasPurchaseFacts ? buys?.owners.size ?? 0 : null,
      verifiedClusterCount30d: held ? null : clusters.get(cik) ?? 0,
      drawdownPct: price ? (price.latest / price.high - 1) * 100 : null,
      priceWindow: price ? { start: price.start, end: price.end } : null,
      lastPurchaseDate: held ? null : buys?.lastDate ?? null,
      priceReviewCount90d: held || !referenceAvailable ? null : priceReviews.get(cik)?.length ?? 0,
      summary: '', cautions,
    };
    const priceSummary = insight.drawdownPct == null ? ''
      : insight.drawdownPct === 0 ? '; latest exported price is at the observed high'
      : `; latest exported price is ${metric(-insight.drawdownPct)}% below the observed high`;
    insight.summary = `${purchaseSummary(insight)}${priceSummary}.`;
    insights.set(cik, insight);
  }
  return insights;
}
