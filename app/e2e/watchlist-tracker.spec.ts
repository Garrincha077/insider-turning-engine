import { expect, test } from '@playwright/test';
import fixture from './fixtures/research-v2.json' with { type: 'json' };
import type { ResearchSnapshot } from '../lib/research-v2';
import { advanceWatchlistTracking, isWatchlistTracking } from '../lib/watchlist-tracker';
import { buildWatchlistChanges } from '../lib/watchlist-changes';

test('local tracking retains the previous publication across reload and same-run UI deploy', () => {
  const first = structuredClone(fixture) as unknown as ResearchSnapshot;
  const cik = first.companies[0].issuerCik;
  const initial = advanceWatchlistTracking(null, first, [cik]);
  expect(initial.previous).toBeNull();
  expect(isWatchlistTracking(initial)).toBe(true);
  expect(advanceWatchlistTracking(initial, first, [cik])).toBe(initial);
  const next = structuredClone(first);
  next.runId = 'next_run'; next.asOf = '2026-09-01T21:00:00Z';
  const stored = advanceWatchlistTracking(initial, next, [cik]);
  expect(stored.previous?.runId).toBe(first.runId);
  const reloaded = JSON.parse(JSON.stringify(stored));
  expect(isWatchlistTracking(reloaded)).toBe(true);
  expect(advanceWatchlistTracking(reloaded, next, [cik])).toEqual(stored);
  expect(buildWatchlistChanges(next, stored.previous, [cik]).get(cik)?.newPurchases).toEqual([]);
});

test('new watches get no fabricated predecessor and removed watches are erased locally', () => {
  const first = structuredClone(fixture) as unknown as ResearchSnapshot;
  const cik = first.companies[0].issuerCik;
  const initial = advanceWatchlistTracking(null, first, []);
  const next = { ...first, runId: 'next_run', asOf: '2026-09-01T21:00:00Z' };
  const added = advanceWatchlistTracking(initial, next, [cik]);
  expect(buildWatchlistChanges(next, added.previous, [cik]).get(cik)?.baselineStatus).toBe('UNAVAILABLE');
  const removed = advanceWatchlistTracking(added, next, []);
  expect(removed.current.issuers).toEqual({});
  expect(removed.previous?.issuers).toEqual({});
});

test('an older publication cannot overwrite a newer viewed baseline', () => {
  const first = structuredClone(fixture) as unknown as ResearchSnapshot;
  const next = { ...first, runId: 'next_run', asOf: '2026-09-01T21:00:00Z' };
  const saved = advanceWatchlistTracking(null, next, []);
  expect(advanceWatchlistTracking(saved, first, [])).toBe(saved);
  expect(isWatchlistTracking({ ...saved, previous: saved.current })).toBe(false);
  expect(isWatchlistTracking({ ...saved, extraData: [] })).toBe(false);
});
