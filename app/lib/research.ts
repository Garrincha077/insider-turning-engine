import type { Candidate, DashboardData, Filing } from './dashboard-data';

export const scoreLabel = 'Experimental score — not historically validated';
export const storagePrefix = 'ite.daily.v1.';
export const controlClass = 'h-10 rounded-lg border border-border bg-card px-3 text-sm text-foreground';

export function timestamp(value: string): number {
  const iso = value.replace(' ', 'T');
  return Date.parse(/(Z|[+-]\d{2}:\d{2})$/.test(iso) || iso.length === 10 ? iso : `${iso}Z`);
}

export function instant(value: string | undefined | null, timezone = 'UTC'): string {
  if (!value || !Number.isFinite(timestamp(value))) return 'Unavailable';
  return new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: timezone }).format(timestamp(value));
}

export function metric(value: number | null | undefined, digits = 1): string {
  return value == null || !Number.isFinite(value) ? '—' : value.toLocaleString('en-US', { maximumFractionDigits: digits });
}

export function money(value: number | null | undefined, compact = false): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: compact ? 'compact' : 'standard', maximumFractionDigits: compact ? 1 : 2 }).format(value);
}

export function costReturn(row: Candidate): number | null {
  return row.currentPrice == null || row.insiderCost == null || row.insiderCost <= 0 ? null : (row.currentPrice / row.insiderCost - 1) * 100;
}

// v1 exposes scored issuers and filing tickers, not a complete identity catalogue.
// Never invent a CIK, score, state, or independent-owner relationship for these rows.
export function companyCatalog(data: DashboardData): Candidate[] {
  const known = new Map(data.candidates.map((row) => [row.ticker, row]));
  for (const row of data.filings) if (!known.has(row.ticker)) known.set(row.ticker, {
    ticker: row.ticker, issuerCik: '', company: row.ticker, sector: 'Unknown',
    total: null, insider: null, divergence: null, turn: null, cluster: null,
    marketRs: null, sectorRs: null, insiderCost: null, currentPrice: null,
    state: 'UNKNOWN', reasons: ['COMPLETE_SCORE_NOT_EXPORTED'],
  });
  return [...known.values()].sort((a, b) => (b.total ?? -Infinity) - (a.total ?? -Infinity) || a.issuerCik.localeCompare(b.issuerCik) || a.ticker.localeCompare(b.ticker));
}

const reasonLabels: Record<string, string> = {
  COMPLETE_SCORE_NOT_EXPORTED: 'This snapshot contains SEC activity but no complete score or resolved company detail.',
  INSUFFICIENT_COMPONENT_DATA: 'One or more required score inputs are unavailable.',
  LOW_CONFIDENCE_HISTORY: 'Limited prior history reduces confidence.',
  STALE_DATA_HOLD: 'State held because a required data source is stale.',
  SAME_SESSION_STATE_REUSED: 'The recorded state is reused; rerunning one market session does not advance hysteresis.',
  UNRESOLVED_IDENTITY: 'A unique eligible US common-stock identity is not yet resolved. SEC facts remain inspectable.',
  UNRESOLVED_AMENDMENT: 'An unresolved correction prevents reliable issuer totals and scores.',
  SOURCE_QUARANTINE: 'A filing for this issuer contains quarantined rows. Its totals and scores are withheld until repaired.',
  JOINT_OWNER_SCORE_NOT_RECOMPUTED: 'Joint reporting owners are counted once in factual totals; the legacy score is withheld until its owner weighting is reconciled.',
  FIRST_BUY_3Y: 'First observed purchase in a three-year history.',
  INSIDER_REENTRY: 'Buying resumed after a prolonged gap.',
};
export function observedContext(data: DashboardData, company: Candidate): string {
  if (!data.research) return 'Price drawdown history: not exported in v1.';
  const rows = data.research.companySeries.filter((row) => row.issuerCik === company.issuerCik).sort((a, b) => a.date.localeCompare(b.date));
  const latest = rows.at(-1);
  const high = rows.length ? Math.max(...rows.map((row) => row.price)) : 0;
  const buys = data.research.economicTransactions.filter((row) => row.issuerCik === company.issuerCik && row.aggregateEligible && row.side === 'BUY');
  return `${latest && high > 0 ? `${metric((latest.price / high - 1) * 100)}% from observed price high · ${rows[0].date}–${latest.date}` : 'Price history unavailable'} · ${buys.length} observed purchases, ${money(buys.reduce((sum, row) => sum + (row.value ?? 0), 0), true)}. Window may be incomplete.`;
}
export function reasonText(value: string): string {
  return reasonLabels[value] ?? (/^[A-Z\d_: .-]+$/.test(value) ? value.replaceAll('_', ' ').toLowerCase().replace(/^\w/, (s) => s.toUpperCase()) : value);
}

export function secUrl(row: Filing): string | undefined {
  const url = row.sourceReferences?.url;
  if (typeof url !== 'string') return undefined;
  try { const parsed = new URL(url); return parsed.protocol === 'https:' && ['www.sec.gov', 'sec.gov'].includes(parsed.hostname) ? url : undefined; }
  catch { return undefined; }
}

export function csvText(headers: string[], rows: unknown[][]): string {
  const cell = (value: unknown) => {
    const raw = value == null ? '' : typeof value === 'string' ? value : typeof value === 'number' || typeof value === 'boolean' ? String(value) : JSON.stringify(value) ?? '';
    // SEC company/owner strings are untrusted spreadsheet input.
    const safe = /^[\s]*[=+@-]/.test(raw) && typeof value !== 'number' ? `'${raw}` : raw;
    return `"${safe.replaceAll('"', '""')}"`;
  };
  return [headers, ...rows].map((row) => row.map(cell).join(',')).join('\r\n');
}

export function downloadCsv(name: string, headers: string[], rows: unknown[][]) {
  const url = URL.createObjectURL(new Blob(['\uFEFF', csvText(headers, rows)], { type: 'text/csv;charset=utf-8' }));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
