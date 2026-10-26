import report from '../../research/results/predictive-baseline-cost-audit.v1.json';

const primary = report.horizons['126'];
const percent = (value: number | null) => value == null ? '—' :
  new Intl.NumberFormat('en-US', {style:'percent', maximumFractionDigits:2}).format(value);

export function BaselineValidation() {
  return <section className="min-w-0 rounded-xl border border-border bg-card p-4 sm:p-5" aria-label="Existing insider benchmark">
    <h2 className="text-base font-semibold">Existing insider benchmark · development only</h2>
    <p className="mt-2 text-sm leading-6 text-muted-foreground">Unusual-purchase baseline B1, formation {report.formation[0]}–{report.formation[1]}, outcomes through {report.outcomeEnd}. This is previously viewed research, not the combined Turning Engine, current picks or an unseen test.</p>
    <p className="mt-3 text-sm" data-testid="baseline-observations">Six-month outcomes: {primary.observed.toLocaleString('en-US')} observed / {primary.events.toLocaleString('en-US')} events with entry. {primary.missing} outcomes remain missing. Signals without an entry are outside this denominator.</p>
    <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-xs" aria-label="Six-month cost sensitivity">
      <thead><tr>{['Assumed cost / side', 'Mean excess', 'Median excess', 'Beat SPY'].map(label => <th key={label} className="whitespace-nowrap p-2">{label}</th>)}</tr></thead>
      <tbody>{primary.costScenarios.map(row => <tr key={row.costBpsPerLeg} className="border-t border-border"><td className="whitespace-nowrap p-2">{row.costBpsPerLeg} bps</td><td className="p-2 font-mono">{percent(row.netExcessVsGrossSpy.mean)}</td><td className="p-2 font-mono">{percent(row.netExcessVsGrossSpy.median)}</td><td className="p-2 font-mono">{percent(row.netExcessVsGrossSpy.winRate)}</td></tr>)}</tbody>
    </table></div>
    <p className="mt-3 text-xs leading-5 text-muted-foreground">Stock returns include an assumed entry premium and exit haircut, compared with gross same-period SPY. The downloadable report also shows an equally costed SPY comparison. Costs are sensitivity assumptions, not observed fills or a choice of the best scenario.</p>
    <p className="mt-4 rounded-lg border border-amber-300/25 p-3 text-sm leading-6 text-amber-200" data-testid="baseline-conclusion">The median event underperformed SPY, including before costs. A positive mean does not establish a repeatable edge. Existing robustness restrictions remain in force; predictive alerts stay off.</p>
    <p className="mt-3 text-xs leading-5 text-muted-foreground">Not yet established: incremental value of technical/valuation filters, market-level ratio prediction, tradable capacity, corrected adverse-excursion paths and independent final evaluation. Missing outcomes are not automatically delistings or zero returns. No significance claim is made.</p>
    <div className="mt-4 flex flex-wrap gap-4 text-xs">
      <a className="text-emerald-200 underline" href={`https://github.com/Garrincha077/insider-turning-engine/actions/runs/${report.sourceRunId}`} target="_blank" rel="noreferrer">Original source run</a>
      <a className="text-emerald-200 underline" href="https://github.com/Garrincha077/insider-turning-engine/blob/main/research/results/predictive-baseline-cost-audit.v1.json" target="_blank" rel="noreferrer">Reproducible report and input hashes</a>
      <a className="text-emerald-200 underline" href="https://github.com/Garrincha077/insider-turning-engine/blob/main/docs/predictive-validation-goal.md" target="_blank" rel="noreferrer">Research protocol</a>
    </div>
  </section>;
}
