export type EngineState =
  | 'FALLING'
  | 'INSIDER_ACCUMULATION'
  | 'BASE_FORMING'
  | 'EARLY_TURN'
  | 'CONFIRMED_TURN';

export type Candidate = {
  ticker: string;
  issuerCik: string;
  company: string;
  sector: string;
  total: number;
  insider: number;
  divergence: number;
  turn: number;
  cluster: number;
  marketRs: number | null;
  sectorRs: number | null;
  insiderCost: number | null;
  currentPrice: number | null;
  state: EngineState;
  reasons: string[];
};

export type Filing = {
  ticker: string;
  owner: string;
  role: string;
  side: 'BUY' | 'SELL';
  value: number;
  filedAt: string;
  accession: string;
};

export type DashboardData = {
  schemaVersion: string;
  scoreVersion: string;
  generatedAt: string;
  status: 'VALIDATED' | 'EXPERIMENTAL' | 'STALE';
  marketPulse: number | null;
  pulsePercentile: number | null;
  pulseHistory: Array<{ date: string; market: number | null; technology: number | null; financials: number | null }>;
  candidates: Candidate[];
  filings: Filing[];
  backtest: Array<{ horizon: string; fullEngine: number; clusterBuy: number; simpleRatio: number }>;
  companySeries: Array<{ ticker: string; date: string; price: number; cost: number | null; mansfield: number | null }>;
};

export const sampleDashboardData: DashboardData = {
  schemaVersion: '1.0.0',
  scoreVersion: 'scoring.v1',
  generatedAt: '2026-08-30T02:30:00Z',
  status: 'EXPERIMENTAL',
  marketPulse: 72,
  pulsePercentile: 88,
  pulseHistory: [
    { date: 'Mar', market: 42, technology: 38, financials: 51 },
    { date: 'Apr', market: 49, technology: 44, financials: 54 },
    { date: 'May', market: 46, technology: 52, financials: 49 },
    { date: 'Jun', market: 57, technology: 61, financials: 55 },
    { date: 'Jul', market: 64, technology: 70, financials: 62 },
    { date: 'Aug', market: 72, technology: 78, financials: 66 },
  ],
  candidates: [
    { ticker: 'NVDA', issuerCik: '0001045810', company: 'NVIDIA Corporation', sector: 'Technology', total: 91, insider: 94, divergence: 96, turn: 78, cluster: 92, marketRs: 4.8, sectorRs: 2.6, insiderCost: 112.84, currentPrice: 109.34, state: 'EARLY_TURN', reasons: ['CEO + CFO cluster within 11 days', '$4.7M qualified open-market buying', '99th percentile company insider activity', 'Price −46% over six months', 'No relevant insider sales in 90 days', 'Ordinary and Mansfield RS improving'] },
    { ticker: 'DAL', issuerCik: '0000027904', company: 'Delta Air Lines', sector: 'Industrials', total: 86, insider: 89, divergence: 92, turn: 71, cluster: 84, marketRs: 2.3, sectorRs: 1.1, insiderCost: 43.22, currentPrice: 40.02, state: 'BASE_FORMING', reasons: ['Three independent buyers in 18 days', 'Insiders remain underwater', 'Volume contraction through six weeks', '3M ordinary RS has stopped falling'] },
    { ticker: 'HUM', issuerCik: '0000049071', company: 'Humana Inc.', sector: 'Health Care', total: 82, insider: 87, divergence: 90, turn: 64, cluster: 76, marketRs: 1.7, sectorRs: 0.8, insiderCost: 246.8, currentPrice: 251.49, state: 'EARLY_TURN', reasons: ['Chairman and director cluster', 'First qualified buy in three years', 'Mansfield sector RS slope positive', 'Price reclaimed 90D insider cost'] },
    { ticker: 'F', issuerCik: '0000037996', company: 'Ford Motor Company', sector: 'Consumer Discretionary', total: 77, insider: 82, divergence: 84, turn: 58, cluster: 71, marketRs: -0.4, sectorRs: 0.5, insiderCost: 10.82, currentPrice: 10.11, state: 'INSIDER_ACCUMULATION', reasons: ['Two officers averaging down', 'Price 6.6% below insider cost', 'No material sales in 90 days'] },
    { ticker: 'PFE', issuerCik: '0000078003', company: 'Pfizer Inc.', sector: 'Health Care', total: 74, insider: 79, divergence: 81, turn: 52, cluster: 68, marketRs: -1.2, sectorRs: -0.2, insiderCost: 24.04, currentPrice: 22.73, state: 'BASE_FORMING', reasons: ['Director cluster after 31% drawdown', 'Weekly volatility contracting', 'Ordinary RS improvement is early'] },
  ],
  filings: [
    { ticker: 'NVDA', owner: 'Avery Morgan', role: 'CEO', side: 'BUY', value: 2800000, filedAt: '2026-08-29 21:42', accession: '0001045810-26-000101' },
    { ticker: 'NVDA', owner: 'Jordan Lee', role: 'CFO', side: 'BUY', value: 1900000, filedAt: '2026-08-29 21:39', accession: '0001045810-26-000100' },
    { ticker: 'DAL', owner: 'Morgan Hill', role: 'Director', side: 'BUY', value: 620000, filedAt: '2026-08-29 20:54', accession: '0000027904-26-000083' },
    { ticker: 'PFE', owner: 'Casey Wright', role: 'Director', side: 'BUY', value: 275000, filedAt: '2026-08-29 20:17', accession: '0000078003-26-000145' },
  ],
  backtest: [
    { horizon: '1M', fullEngine: 1.8, clusterBuy: 1.1, simpleRatio: 0.4 },
    { horizon: '3M', fullEngine: 4.9, clusterBuy: 3.2, simpleRatio: 1.2 },
    { horizon: '6M', fullEngine: 8.7, clusterBuy: 5.1, simpleRatio: 2.4 },
    { horizon: '12M', fullEngine: 13.4, clusterBuy: 8.2, simpleRatio: 4.7 },
  ],
  companySeries: [
    { ticker: 'NVDA', date: 'Mar', price: 154, cost: 132, mansfield: -8.2 },
    { ticker: 'NVDA', date: 'Apr', price: 138, cost: 128, mansfield: -7.1 },
    { ticker: 'NVDA', date: 'May', price: 119, cost: 122, mansfield: -5.4 },
    { ticker: 'NVDA', date: 'Jun', price: 103, cost: 117, mansfield: -3.8 },
    { ticker: 'NVDA', date: 'Jul', price: 106, cost: 114, mansfield: -1.9 },
    { ticker: 'NVDA', date: 'Aug', price: 109, cost: 113, mansfield: -0.4 },
  ],
};
