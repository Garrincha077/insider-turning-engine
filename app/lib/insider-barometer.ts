import type { BenchmarkPoint, ResearchSnapshot } from './research-v2';

export type RatioPoint = {
  label: string; start: string; end: string; ratio: number | null;
  buys: number; sales: number; partial: boolean; mean3m: number | null;
  spy: number | null; spyDate: string | null;
};

export function dateOffset(day: string, offset: number): string {
  const value = new Date(`${day}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() + offset);
  return value.toISOString().slice(0, 10);
}

const endOfDay = (day: string) => Date.parse(`${day}T23:59:59.999Z`);
const ratio = (buys: number, sales: number) => sales ? buys / sales : null;

/** A descriptive count ratio, never a calibrated forecast of market extremes. */
export function buildInsiderBarometer(data: ResearchSnapshot, sector = 'All sectors') {
  const asOf = Date.parse(data.asOf);
  const asOfDay = new Date(asOf).toISOString().slice(0, 10);
  const expected = [...new Set(data.coverage.expectedSecDays.filter((day) => day <= asOfDay))].sort();
  const evidence = new Map(data.coverage.days.map((row) => [row.day, row]));
  const complete = expected.filter((day) => evidence.get(day)?.complete);
  const latestDay = complete.at(-1) ?? null;
  const firstDay = expected[0] ?? null;
  const start = latestDay ? dateOffset(latestDay, -89) : null;
  const monthStart = start ? `${start.slice(0, 7)}-01` : null;
  const priorMonths = monthStart ? new Date(`${monthStart}T00:00:00Z`) : null;
  priorMonths?.setUTCMonth(priorMonths.getUTCMonth() - 2);
  const historyStart = priorMonths?.toISOString().slice(0, 10) ?? null;
  const companies = new Map(data.companies.map((row) => [row.issuerCik, row]));
  const sectors = [...new Set(data.companies.map((row) => row.sector ?? 'Unmapped'))].sort();
  const seen = new Set<string>();
  let missingLineage = 0;
  const eligible = data.economicTransactions.filter((row) => {
    const company = companies.get(row.issuerCik);
    if (!company || company.identityStatus !== 'RESOLVED' || company.insiderStatus !== 'AVAILABLE'
      || !row.aggregateEligible || !row.qualified || row.processing !== 'EFFECTIVE'
      || row.table !== 'NON_DERIVATIVE' || !(row.code === 'P' && row.side === 'BUY' || row.code === 'S' && row.side === 'SELL')
      || Math.max(Date.parse(row.knownAt), Date.parse(row.acceptedAt)) > asOf
      || row.transactionDate > asOfDay
      || sector !== 'All sectors' && (company.sector ?? 'Unmapped') !== sector) return false;
    if (row.secDay == null) { missingLineage++; return false; }
    if (!latestDay || !historyStart || row.secDay > latestDay || row.transactionDate < historyStart
      || row.transactionDate > latestDay || Math.max(Date.parse(row.knownAt), Date.parse(row.acceptedAt)) > Math.min(asOf, endOfDay(latestDay))) return false;
    if (seen.has(row.eventId)) return false;
    seen.add(row.eventId);
    return true;
  });
  const windowPartial = (from: string, to: string) => !firstDay || from < firstDay
    || !latestDay || to > latestDay
    || expected.some((day) => day >= from && day <= to && !evidence.get(day)?.complete);
  const count = (from: string, to: string, cutoff: string) => {
    let buys = 0, sales = 0;
    for (const row of eligible) {
      if (row.transactionDate < from || row.transactionDate > to || row.secDay! > cutoff
        || Math.max(Date.parse(row.knownAt), Date.parse(row.acceptedAt)) > Math.min(asOf, endOfDay(cutoff))) continue;
      if (row.side === 'BUY') buys++; else sales++;
    }
    return { buys, sales, ratio: ratio(buys, sales) };
  };
  const benchmarks = (data.benchmarkSeries ?? []).filter((row) => row.symbol === 'SPY'
    && monthStart != null && latestDay != null && row.date >= monthStart && row.date <= latestDay
    && row.price > 0 && Number.isFinite(row.price)
    && (row.availableAt == null || Date.parse(row.availableAt) <= asOf))
    .toSorted((a, b) => a.date.localeCompare(b.date));
  const bases = new Set(benchmarks.map((row) => `${row.isAdjusted}:${row.adjustmentBasis}`));
  const spyReason = !benchmarks.length ? 'SPY observations are unavailable in this snapshot.'
    : bases.size > 1 ? 'SPY adjustment basis changes within this window; comparison is unavailable.' : null;
  const spyFor = (from: string, to: string): BenchmarkPoint | undefined => spyReason ? undefined
    : benchmarks.findLast((row) => row.date >= from && row.date <= to
      && (row.availableAt == null || Date.parse(row.availableAt) <= Math.min(asOf, endOfDay(to))));
  const point = (label: string, from: string, to: string, cutoff: string): RatioPoint => {
    const spy = spyFor(from, to);
    return { label, start: from, end: to, ...count(from, to, cutoff),
      partial: windowPartial(from, to), mean3m: null, spy: spy?.price ?? null, spyDate: spy?.date ?? null };
  };
  const rolling = complete.filter((day) => start != null && day >= start).map((day) =>
    point(day, dateOffset(day, -29), day, day));
  const monthly: RatioPoint[] = [];
  if (historyStart && latestDay) {
    const cursor = new Date(`${historyStart}T00:00:00Z`);
    while (cursor.toISOString().slice(0, 10) <= latestDay) {
      const from = cursor.toISOString().slice(0, 10);
      cursor.setUTCMonth(cursor.getUTCMonth() + 1);
      const to = dateOffset(cursor.toISOString().slice(0, 10), -1);
      const actualTo = to > latestDay ? latestDay : to;
      const row = point(from.slice(0, 7), from, actualTo, latestDay);
      row.partial ||= actualTo !== to;
      monthly.push(row);
    }
    for (let index = 2; index < monthly.length; index++) {
      const trailing = monthly.slice(index - 2, index + 1);
      if (trailing.every((row) => !row.partial && row.ratio != null))
        monthly[index].mean3m = trailing.reduce((sum, row) => sum + row.ratio!, 0) / 3;
    }
  }
  const firstSpy = spyReason ? undefined : benchmarks[0];
  const lastSpy = spyReason ? undefined : benchmarks.at(-1);
  return { latestDay, start, sectors, missingLineage, rolling,
    monthly: monthly.filter((row) => monthStart != null && row.start >= monthStart), current: rolling.at(-1) ?? null,
    spyReason, spyProviders: [...new Set(benchmarks.map((row) => row.provider))].sort(),
    spyBasis: bases.size === 1 ? benchmarks[0].adjustmentBasis : null,
    spyChangePct: firstSpy && lastSpy && firstSpy.date !== lastSpy.date ? (lastSpy.price / firstSpy.price - 1) * 100 : null,
    spyStart: firstSpy?.date ?? null, spyEnd: lastSpy?.date ?? null };
}
