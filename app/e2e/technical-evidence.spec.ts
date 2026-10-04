import { expect, test } from '@playwright/test';
import { sampleDashboardData } from '../lib/dashboard-data';
import { buildTechnicalEvidence } from '../lib/technical-evidence';

test('technical evidence requires 50 observed closes and never invents a phase', () => {
  const data = structuredClone(sampleDashboardData);
  const company = { ...data.candidates[0], state: 'UNKNOWN' as const, marketRs: null };
  data.candidates = [company];
  data.companySeries = Array.from({ length: 49 }, (_, i) => ({ ticker: company.ticker, date: new Date(Date.UTC(2026, 6, 1 + i)).toISOString().slice(0, 10), price: 10, cost: null, mansfield: null }));
  const result = buildTechnicalEvidence(data).get(company.issuerCik)!;
  expect(result.checks[0].status).toBe('UNAVAILABLE');
  expect(result.checks[1].status).toBe('UNAVAILABLE');
  expect(result.summary).toContain('has not been established');
});

test('observed price and RS checks are independent of future price rows', () => {
  const data = structuredClone(sampleDashboardData);
  const company = data.candidates[0];
  data.candidates = [company];
  data.companySeries = Array.from({ length: 50 }, (_, i) => ({ ticker: company.ticker, date: new Date(Date.UTC(2026, 6, 1 + i)).toISOString().slice(0, 10), price: i === 49 ? 12 : 10, cost: null, mansfield: null }));
  const before = buildTechnicalEvidence(data).get(company.issuerCik)!;
  expect(before.checks[0].status).toBe('MET');
  data.companySeries.push({ ...data.companySeries[0], date: '2027-01-01', price: 1000 });
  expect(buildTechnicalEvidence(data).get(company.issuerCik)).toEqual(before);
  data.candidates[0].reasons = ['STALE_DATA_HOLD'];
  expect(buildTechnicalEvidence(data).get(company.issuerCik)!.checks.every((row) => row.status === 'UNAVAILABLE')).toBe(true);
});
