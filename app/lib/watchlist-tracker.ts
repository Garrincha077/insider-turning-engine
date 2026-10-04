import type { ResearchSnapshot } from './research-v2';
import { createWatchlistBaseline, isWatchlistBaseline, type WatchlistBaseline } from './watchlist-changes';

export type WatchlistTracking = { version: 1; current: WatchlistBaseline; previous: WatchlistBaseline | null };

export function isWatchlistTracking(value: unknown): value is WatchlistTracking {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const row = value as Partial<WatchlistTracking>;
  return Object.keys(row).every((key) => ['version', 'current', 'previous'].includes(key))
    && row.version === 1 && isWatchlistBaseline(row.current)
    && (row.previous === null || isWatchlistBaseline(row.previous)
      && Date.parse(row.previous.asOf) < Date.parse(row.current.asOf)
      && row.previous.runId !== row.current.runId);
}

/** Keep the preceding viewed publication across reloads; a new watch never creates old activity. */
export function advanceWatchlistTracking(
  saved: WatchlistTracking | null, snapshot: ResearchSnapshot, watched: string[],
): WatchlistTracking {
  if (saved && Date.parse(snapshot.asOf) < Date.parse(saved.current.asOf)) return saved;
  const current = createWatchlistBaseline(snapshot, watched);
  if (!saved) return { version: 1, current, previous: null };
  const same = snapshot.runId === saved.current.runId && Date.parse(snapshot.asOf) === Date.parse(saved.current.asOf);
  if (!same && (snapshot.runId === saved.current.runId || Date.parse(snapshot.asOf) === Date.parse(saved.current.asOf))) return saved;
  const predecessor = same ? saved.previous : saved.current;
  const previous = predecessor ? { ...predecessor,
    issuers: Object.fromEntries(Object.entries(predecessor.issuers).filter(([cik]) => watched.includes(cik))),
  } : null;
  const next: WatchlistTracking = { version: 1, current, previous };
  return JSON.stringify(next) === JSON.stringify(saved) ? saved : next;
}
