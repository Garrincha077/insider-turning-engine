import type { Candidate, DashboardData, EngineState } from './dashboard-data';
import { metric, reasonText, timestamp } from './research';

export type TechnicalCheck = { label: string; status: 'MET' | 'NOT_MET' | 'UNAVAILABLE'; detail: string };
export type TechnicalEvidence = { checks: TechnicalCheck[]; summary: string; caution: string };

const phaseDescriptions: Record<EngineState, string> = {
  UNKNOWN: 'A reliable accumulation or turn phase has not been established.',
  FALLING: 'Weak price structure is recorded; no accumulation or turn phase is established.',
  INSIDER_ACCUMULATION: 'Insider accumulation is recorded; a technical turn is not yet established.',
  BASE_FORMING: 'A base is recorded; relative strength and price confirmation still matter.',
  EARLY_TURN: 'An early turn is recorded; sustained price confirmation is still needed.',
  CONFIRMED_TURN: 'Technical confirmation is recorded; this is not a return forecast.',
};

/** Display evidence, not a browser-side recomputation of the scoring state machine. */
export function buildTechnicalEvidence(data: DashboardData): Map<string, TechnicalEvidence> {
  const cutoff = timestamp(data.generatedAt);
  const series = new Map<string, Array<{ date: string; price: number }>>();
  const source = data.research
    ? data.research.companySeries.map((row) => ({ ...row, key: row.issuerCik }))
    : data.companySeries.map((row) => ({ ...row, key: row.ticker }));
  for (const row of source) {
    if (!Number.isFinite(timestamp(row.date)) || timestamp(row.date) > cutoff || !Number.isFinite(row.price) || row.price <= 0) continue;
    const rows = series.get(row.key) ?? [];
    rows.push(row); series.set(row.key, rows);
  }
  const result = new Map<string, TechnicalEvidence>();
  for (const company of data.candidates) {
    const rows = [...new Map((series.get(data.research ? company.issuerCik : company.ticker) ?? []).map((row) => [row.date, row])).values()].sort((a, b) => a.date.localeCompare(b.date));
    const recent = rows.slice(-50);
    const latest = recent.at(-1);
    const average = recent.length === 50 ? recent.reduce((sum, row) => sum + row.price, 0) / 50 : null;
    const held = company.reasons.includes('STALE_DATA_HOLD');
    const priceCheck: TechnicalCheck = {
      label: 'Price above observed 50-close average',
      status: held || !latest || average == null ? 'UNAVAILABLE' : latest.price >= average ? 'MET' : 'NOT_MET',
      detail: held ? 'A source hold prevents a fresh check.' : average == null ? `${recent.length} of 50 required exported closes available.` : `${metric(latest!.price, 2)} vs ${metric(average, 2)} USD · ${latest!.date}`,
    };
    const rs = (label: string, value: number | null): TechnicalCheck => ({
      label,
      status: held || value == null || !Number.isFinite(value) ? 'UNAVAILABLE' : value >= 0 ? 'MET' : 'NOT_MET',
      detail: held ? 'A source hold prevents a fresh check.' : value == null || !Number.isFinite(value) ? 'Required benchmark or relative-strength history is unavailable.' : `Mansfield RS ${metric(value)} · zero is the comparison baseline.`,
    });
    result.set(company.issuerCik || company.ticker, {
      checks: [priceCheck, rs('Market relative strength at or above zero', company.marketRs), rs('Sector relative strength at or above zero', company.sectorRs)],
      summary: phaseDescriptions[company.state],
      caution: held ? reasonText('STALE_DATA_HOLD') : 'These are checks of available evidence, not all phase prerequisites. Missing sessions can affect the observed-close average; recorded phases use the server methodology.',
    });
  }
  return result;
}

export function evidenceFor(map: Map<string, TechnicalEvidence>, company: Candidate): TechnicalEvidence {
  return map.get(company.issuerCik || company.ticker) ?? { checks: [], summary: phaseDescriptions[company.state], caution: 'Technical inputs are unavailable.' };
}
