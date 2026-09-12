import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import schema from '../../schemas/research-snapshot.v2.schema.json';
import type { DashboardData, EngineState } from './dashboard-data';
import type { PublicationManifest } from './operations-data';

export type EconomicEvent = {
  eventId: string; issuerCik: string; accession: string; table: 'NON_DERIVATIVE' | 'DERIVATIVE'; rowSequence: number;
  transactionDate: string; acceptedAt: string; knownAt: string; code: string; side: 'BUY' | 'SELL' | 'OTHER';
  secDay?: string | null; securityTitle?: string;
  shares: number | null; price: number | null; value: number | null; ownership: 'D' | 'I'; rule10b51: 'true' | 'false' | 'unknown';
  sourceUrl: string; owners: Array<{ ownerCik: string; role: string }>;
  processing: 'EFFECTIVE' | 'UNRESOLVED_AMENDMENT'; qualified: boolean; aggregateEligible: boolean;
};
export type BasisWindow = { days: 30 | 90; start: string; end: string; weightedBasis: number | null; purchaseValue: number | null; purchaseCount: number | null; coverage: 'OBSERVED_COMPLETE_SEC_WINDOW' | 'PARTIAL' | 'BLOCKED' };
export type ResearchSnapshot = {
  schemaVersion: '2.0.0' | '2.1.0'; source: 'canonical-sec-research'; runId: string; asOf: string; scoreVersion: string;
  companies: Array<{ issuerCik: string; ticker: string | null; name: string; sector: string | null; identityStatus: 'RESOLVED' | 'UNRESOLVED'; insiderStatus: 'AVAILABLE' | 'UNRESOLVED_AMENDMENT' | 'SOURCE_QUARANTINE'; currentPrice: number | null; basis: BasisWindow[] }>;
  economicTransactions: EconomicEvent[];
  reportingOwners: Array<{ ownerCik: string; name: string }>;
  researchScores: Array<{ issuerCik: string; total: number | null; insider: number | null; divergence: number | null; turn: number | null; cluster: number | null; marketRs: number | null; sectorRs: number | null; state: string; stateChangedAt: string | null; reasons: string[]; scoreVersion: string; methodologyHash: string | null; configHash: string | null; runId: string; asOf: string }>;
  clusters: Array<{ clusterId: string; issuerCik: string; start: string; end: string; ownerCiks: string[]; eventIds: string[]; purchaseValue: number }>;
  companySeries: Array<{ issuerCik: string; date: string; price: number; volume: number | null; marketRs: number | null; sectorRs: number | null }>;
  coverage: { scope: string; expectedSecDays: string[]; missingSecDays: string[]; days: Array<{ day: string; discoveredFilings: number; storedFilings: number; parseRows: number; quarantinedRows: number; failures: number; complete: boolean }>; canonicalOwnerRows: number; economicEvents: number; eligibleCompanies: number; resolvedIdentities: number; pricedCompanies: number; completeScores: number; unresolvedAmendmentIssuers: string[]; exclusions: Record<string, number> };
  readiness: Record<'dashboard' | 'digest' | 'predictive', { status: 'READY' | 'PARTIAL' | 'BLOCKED'; reasons: string[] }>;
};

const validator = new Ajv2020({ allErrors: false, strict: false });
addFormats(validator);
const check = validator.compile<ResearchSnapshot>(schema);

export function validateResearch(value: unknown, manifest: PublicationManifest): ResearchSnapshot {
  if (!check(value)) throw new Error(`Research v2 schema mismatch at ${check.errors?.[0]?.instancePath ?? '/'}`);
  if (value.runId !== manifest.runId || Date.parse(value.asOf) !== Date.parse(manifest.asOf) || value.scoreVersion !== manifest.scoreVersion) throw new Error('Research v2 run lineage mismatch');
  const companies = new Set(value.companies.map((row) => row.issuerCik));
  const owners = new Set(value.reportingOwners.map((row) => row.ownerCik));
  const events = new Map(value.economicTransactions.map((row) => [row.eventId, row]));
  if (companies.size !== value.companies.length || owners.size !== value.reportingOwners.length || events.size !== value.economicTransactions.length) throw new Error('Research v2 duplicate identity');
  for (const row of value.economicTransactions) {
    if (!companies.has(row.issuerCik) || row.owners.some((owner) => !owners.has(owner.ownerCik)) || new Set(row.owners.map((owner) => owner.ownerCik)).size !== row.owners.length) throw new Error('Research v2 broken event reference');
    if (Math.max(Date.parse(row.knownAt), Date.parse(row.acceptedAt)) > Date.parse(value.asOf) || row.transactionDate > value.asOf.slice(0, 10)) throw new Error('Research v2 future event');
    if (row.processing !== 'EFFECTIVE' && row.aggregateEligible) throw new Error('Research v2 unresolved aggregate');
    if (row.shares == null && (value.schemaVersion !== '2.1.0' || row.table !== 'DERIVATIVE' || row.value == null || row.qualified || row.aggregateEligible)) throw new Error('Research v2 invalid amount-only event');
  }
  if (new Set(value.researchScores.map((row) => row.issuerCik)).size !== value.researchScores.length) throw new Error('Research v2 duplicate score');
  for (const row of value.researchScores) if (!companies.has(row.issuerCik) || row.runId !== value.runId || row.scoreVersion !== value.scoreVersion || Date.parse(row.asOf) !== Date.parse(value.asOf) || row.stateChangedAt != null && Date.parse(row.stateChangedAt) > Date.parse(value.asOf)) throw new Error('Research v2 mixed score lineage');
  for (const row of value.clusters) {
    if (!companies.has(row.issuerCik) || row.eventIds.some((id) => !events.has(id)) || row.ownerCiks.some((id) => !owners.has(id))) throw new Error('Research v2 broken cluster reference');
    const members = row.eventIds.map((id) => events.get(id)!);
    const memberOwners = new Set(members.flatMap((event) => event.owners.map((owner) => owner.ownerCik)));
    if (new Set(row.eventIds).size !== row.eventIds.length || members.some((event) => event.issuerCik !== row.issuerCik || event.side !== 'BUY' || !event.aggregateEligible) || memberOwners.size !== row.ownerCiks.length || row.ownerCiks.some((cik) => !memberOwners.has(cik)) || Math.abs(row.purchaseValue - members.reduce((sum, event) => sum + (event.value ?? 0), 0)) > 0.01) throw new Error('Research v2 inconsistent cluster economics');
  }
  if (value.companySeries.some((row) => !companies.has(row.issuerCik) || row.date > value.asOf.slice(0, 10))) throw new Error('Research v2 invalid company series');
  if (value.companies.some((row) => row.basis.map((window) => window.days).sort((a, b) => a - b).join(',') !== '30,90')) throw new Error('Research v2 basis windows missing');
  return value;
}

export function adaptResearch(legacy: DashboardData, research: ResearchSnapshot): DashboardData {
  const companies = new Map(research.companies.map((row) => [row.issuerCik, row]));
  const owners = new Map(research.reportingOwners.map((row) => [row.ownerCik, row.name]));
  const scores = new Map(research.researchScores.map((row) => [row.issuerCik, row]));
  const symbol = (cik: string) => companies.get(cik)?.ticker ?? `CIK:${cik}`;
  return {
    ...legacy, research,
    candidates: research.companies.map((row) => {
      const score = scores.get(row.issuerCik);
      const state = score?.state ?? 'UNKNOWN';
      return { ticker: symbol(row.issuerCik), issuerCik: row.issuerCik, company: row.name, sector: row.sector ?? 'Unknown', currentPrice: row.currentPrice,
        insiderCost: row.basis.find((item) => item.days === 90)?.weightedBasis ?? null,
        total: score?.total ?? null, insider: score?.insider ?? null, divergence: score?.divergence ?? null, turn: score?.turn ?? null, cluster: score?.cluster ?? null,
        marketRs: score?.marketRs ?? null, sectorRs: score?.sectorRs ?? null,
        state: (['FALLING', 'INSIDER_ACCUMULATION', 'BASE_FORMING', 'EARLY_TURN', 'CONFIRMED_TURN'].includes(state) ? state : 'UNKNOWN') as EngineState,
        stateChangedAt: score?.stateChangedAt, reasons: score?.reasons ?? ['INSUFFICIENT_COMPONENT_DATA'] };
    }),
    filings: research.economicTransactions.filter((row) => row.side !== 'OTHER' && row.table === 'NON_DERIVATIVE').map((row) => ({
      ticker: symbol(row.issuerCik), issuerCik: row.issuerCik, eventId: row.eventId, owner: row.owners.map((item) => owners.get(item.ownerCik) ?? item.ownerCik).join(' / '), role: row.owners.map((item) => item.role).join(' / '), side: row.side as 'BUY' | 'SELL', value: row.value,
      filedAt: row.acceptedAt, accession: row.accession, transactionDate: row.transactionDate, shares: row.shares, price: row.price, rule10b51: row.rule10b51, processing: row.processing, qualified: row.qualified, aggregateEligible: row.aggregateEligible, sourceReferences: { url: row.sourceUrl },
    })),
    companySeries: research.companySeries.map((row) => ({ ticker: symbol(row.issuerCik), date: row.date, price: row.price, cost: null, mansfield: row.marketRs, sectorMansfield: row.sectorRs, volume: row.volume })),
  };
}
