import type { RatioPoint } from './insider-barometer';

export const COMPASS_MIN_PRIOR_MONTHS = 24;

export type CompassContext = {
  status: 'PARTIAL_MONTH' | 'NO_SALE_DENOMINATOR' | 'INSUFFICIENT_HISTORY' | 'AVAILABLE';
  percentile: number | null; priorMean: number | null; priorMonths: number;
  reading: string; explanation: string;
};

function previousMonth(label: string): string {
  const day = new Date(`${label}-01T00:00:00Z`);
  day.setUTCMonth(day.getUTCMonth() - 1);
  return day.toISOString().slice(0, 7);
}

/** Descriptive empirical position in strictly prior, consecutive complete months.
 * Not a probability of returns or a historical real-time trading signal. Callers
 * supply same-population, as-of-qualified data, never another provider's mean.
 */
export function compassContext(months: RatioPoint[], current: RatioPoint | null): CompassContext {
  const prior = new Map(months.filter((row) => current && row.label < current.label)
    .map((row) => [row.label, row]));
  const values: number[] = [];
  let cursor = current ? previousMonth(current.label) : '';
  while (cursor) {
    const row = prior.get(cursor);
    if (!row || row.partial || row.ratio == null || !Number.isFinite(row.ratio)) break;
    values.push(row.ratio);
    cursor = previousMonth(cursor);
  }
  const enough = values.length >= COMPASS_MIN_PRIOR_MONTHS;
  const priorMean = enough ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  const base = { percentile: null, priorMean, priorMonths: values.length };
  if (!current || current.ratio == null || !Number.isFinite(current.ratio)) return {
    ...base, status: 'NO_SALE_DENOMINATOR', reading: 'Ratio unavailable',
    explanation: 'No observed sale denominator. Missing activity is not a zero ratio.',
  };
  if (current.partial) return {
    ...base, status: 'PARTIAL_MONTH', reading: 'Provisional month',
    explanation: 'An unfinished or incompletely inventoried month is not classified against full historical months.',
  };
  if (!enough) return {
    ...base, status: 'INSUFFICIENT_HISTORY', reading: 'Historical context unavailable',
    explanation: `${values.length} consecutive prior complete months; at least ${COMPASS_MIN_PRIOR_MONTHS} are required. Current counts are descriptive, not evidence of a market top or bottom.`,
  };
  const percentile = 100 * values.reduce((sum, value) => sum + (value < current.ratio! ? 1 : value === current.ratio ? 0.5 : 0), 0) / values.length;
  const reading = percentile >= 95 ? 'Unusually high buying activity'
    : percentile >= 80 ? 'Elevated buying activity'
    : percentile <= 20 ? 'Relatively sale-heavy activity' : 'Within historical range';
  return { status: 'AVAILABLE', percentile, priorMean, priorMonths: values.length, reading,
    explanation: `Count ratio at the ${percentile.toFixed(0)}th percentile of ${values.length} prior complete months. This is activity context, not a market timing forecast; low buying does not establish a top.` };
}
