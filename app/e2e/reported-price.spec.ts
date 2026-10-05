import { expect, test } from '@playwright/test';
import fixture from './fixtures/research-v2.json' with { type: 'json' };
import type { EconomicEvent, ResearchSnapshot } from '../lib/research-v2';
import { isReportedPriceExtreme, purchasePriceReviews, reportedPriceReviewStatus } from '../lib/reported-price';

function research(): ResearchSnapshot { return structuredClone(fixture) as unknown as ResearchSnapshot; }
function event(overrides: Partial<EconomicEvent>): EconomicEvent {
  return { ...structuredClone(fixture.economicTransactions[0]) as EconomicEvent, price: 11_000, ...overrides };
}

test('reported-price review uses the existing inclusive relative threshold in both directions', () => {
  expect(isReportedPriceExtreme(11_000, 11)).toBe(true);
  expect(isReportedPriceExtreme(11, 11_000)).toBe(true);
  expect(isReportedPriceExtreme(10_999, 11)).toBe(false);
  expect(isReportedPriceExtreme(11, 10_999)).toBe(false);
  // A high absolute share price is not evidence of a source error.
  expect(reportedPriceReviewStatus(650_000, 660_000)).toBe('NO_FLAG');
});

test('missing or invalid comparison inputs remain unavailable, not a verified normal price', () => {
  for (const missing of [null, undefined, 0, -1, NaN, Infinity]) {
    expect(reportedPriceReviewStatus(missing, 11)).toBe('UNAVAILABLE');
    expect(reportedPriceReviewStatus(11, missing)).toBe('UNAVAILABLE');
    expect(isReportedPriceExtreme(11_000, missing)).toBe(false);
  }
});

test('review counts preserve economic-event grain, availability and qualifying purchase scope', () => {
  const data = research();
  const valid = event({ eventId: 'valid' });
  data.economicTransactions = [
    { ...valid, knownAt: '2026-08-31T21:00:01Z' }, // Must not consume the stable ID.
    valid, structuredClone(valid),
    event({ eventId: 'future-accepted', acceptedAt: '2026-08-31T21:00:01Z' }),
    event({ eventId: 'future-date', transactionDate: '2026-09-01' }),
    event({ eventId: 'sale', side: 'SELL' }),
    event({ eventId: 'derivative', table: 'DERIVATIVE' }),
    event({ eventId: 'not-qualified', qualified: false }),
    event({ eventId: 'held', aggregateEligible: false }),
    event({ eventId: 'amendment', processing: 'UNRESOLVED_AMENDMENT' }),
    event({ eventId: 'invalid-known', knownAt: 'not-a-time' }),
  ];
  const before = structuredClone(data);
  expect(purchasePriceReviews(data, 90).get(data.companies[0].issuerCik)?.map((row) => row.eventId)).toEqual(['valid']);
  expect(data).toEqual(before); // Review never rewrites raw prices or dollars.
  data.companies[0].currentPrice = null;
  expect(purchasePriceReviews(data, 90).size).toBe(0);
});

test('30D and 90D review windows are inclusive and anchored to the UTC snapshot date', () => {
  const data = research();
  data.asOf = '2026-09-01T01:00:00+04:00'; // August 31 UTC.
  data.economicTransactions = [
    event({ eventId: '90-first', transactionDate: '2026-06-03' }),
    event({ eventId: 'too-old', transactionDate: '2026-06-02' }),
    event({ eventId: '30-first', transactionDate: '2026-08-02' }),
    event({ eventId: '30-too-old', transactionDate: '2026-08-01' }),
    event({ eventId: 'last', transactionDate: '2026-08-31', acceptedAt: data.asOf, knownAt: data.asOf }),
  ];
  const cik = data.companies[0].issuerCik;
  expect(purchasePriceReviews(data, 30).get(cik)?.map((row) => row.eventId)).toEqual(['30-first', 'last']);
  expect(purchasePriceReviews(data, 90).get(cik)?.map((row) => row.eventId)).toEqual(['90-first', '30-first', '30-too-old', 'last']);
});
