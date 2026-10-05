import type { EconomicEvent, ResearchSnapshot } from './research-v2';

/** Existing display-only Pulse rule; not proof of an erroneous filing. */
export function isReportedPriceExtreme(price: number | null | undefined, reference: number | null | undefined): boolean {
  return reportedPriceReviewStatus(price, reference) === 'REVIEW';
}

export function reportedPriceReviewStatus(price: number | null | undefined, reference: number | null | undefined): 'REVIEW' | 'NO_FLAG' | 'UNAVAILABLE' {
  if (price == null || reference == null || !Number.isFinite(price) || !Number.isFinite(reference)
    || price <= 0 || reference <= 0) return 'UNAVAILABLE';
  return Math.max(price / reference, reference / price) >= 1_000 ? 'REVIEW' : 'NO_FLAG';
}

export const reportedPriceCaution = 'Reported price is at least 1,000× away from the snapshot market close. This is a review flag, not proof of an error; dates and price adjustments differ. Source amounts are unchanged.';

/** Only available, eligible purchases in the displayed calendar window. */
export function purchasePriceReviews(data: ResearchSnapshot, days: 30 | 90): Map<string, EconomicEvent[]> {
  const output = new Map<string, EconomicEvent[]>();
  const references = new Map(data.companies.map((row) => [row.issuerCik, row.currentPrice]));
  const asOf = Date.parse(data.asOf);
  if (!Number.isFinite(asOf)) return output;
  const end = new Date(asOf).toISOString().slice(0, 10);
  const start = new Date(Date.parse(end) - (days - 1) * 86_400_000).toISOString().slice(0, 10);
  const seen = new Set<string>();
  for (const row of data.economicTransactions) {
    const known = Date.parse(row.knownAt), accepted = Date.parse(row.acceptedAt);
    if (!Number.isFinite(known) || !Number.isFinite(accepted) || known > asOf || accepted > asOf
      || row.transactionDate < start || row.transactionDate > end || seen.has(row.eventId)
      || !row.qualified || !row.aggregateEligible || row.processing !== 'EFFECTIVE'
      || row.side !== 'BUY' || row.table !== 'NON_DERIVATIVE'
      || !isReportedPriceExtreme(row.price, references.get(row.issuerCik))) continue;
    seen.add(row.eventId);
    const rows = output.get(row.issuerCik) ?? [];
    rows.push(row); output.set(row.issuerCik, rows);
  }
  return output;
}
