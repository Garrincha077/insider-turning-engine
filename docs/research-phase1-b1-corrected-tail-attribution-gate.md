# Phase-1 B1 continuity-corrected residual tail/year attribution gate

Frozen: 2026-09-17, after the continuity-corrected robustness gate remained blocked and **before inspecting the identities/ranking of the residual corrected top-1% winners**.

This gate reuses the already frozen explanatory audit semantics in `docs/research-phase1-b1-tail-attribution-gate.md`. It does not add a new signal filter, return cutoff, issuer rule, year rule, sector rule or market-cap rule.

## Why this corrected audit is allowed

The continuity correction materially changed the 126-session arithmetic mean and reduced positive-tail concentration, but the unchanged corrected robustness gate still fired two blocking warnings:

- corrected top-1%-removed mean <= 0;
- fewer than three development years with positive corrected mean excess.

Therefore HAC/OOS remains closed. The next permitted work is an explanatory development-only audit of the residual corrected tail/year concentration using the same diagnostics that were frozen before the canonical tail identities were inspected.

## Frozen sources

Corrected outcome source:

- run `35277369958`;
- artifact `phase1-b1-continuity-corrected-performance-35277369958`;
- digest `sha256:d750c85b6019740ad381b2f53a9d6ceb379a5665cf8b43f0c70e799484bfa775`.

Canonical B1 metadata source, used only to restore fields not duplicated in the corrected long-format artifact:

- run `35263058619`;
- artifact `phase1-b1-b4-development-35263058619`;
- digest `sha256:1021de09ebaa190604bf1762714fe014ebc75e3e197b47d2d684003289ed638d`;
- B1 event order/key must match corrected `eventNumber` exactly.

No new SEC evidence, market outcomes, corporate-action decisions or 2023+ data may be read.

## Scope and primary field

- B1 definition unchanged.
- Primary horizon: 126 XNYS sessions.
- Primary value: continuity-corrected `correctedExcess` for horizon 126.
- Mature observation: `valuationStatus=VALUED` and finite corrected excess.
- Development cohort clock: canonical `evaluationSession`, 2016–2020.
- Outcomes through 2022 only.
- 2023+ is a hard failure.
- Corrected mature N is expected to reproduce the persisted corrected-performance summary before attribution.

For corrected mature N = 5,965, the global top-1% set is frozen as the **59 largest corrected 126-session excess observations** (`floor(5965 * 0.01)`). Ties use the already frozen order: descending excess, then evaluation session, issuer CIK and ticker.

## Audit families — unchanged semantics

### A. Global corrected top-1% attribution

For the 59 largest corrected observations report the same fields as the canonical tail gate: signed excess contribution, unique issuers/tickers, repeat concentration, year distribution, 2020 share and top-ten audit rows.

The top-ten table remains audit evidence only.

### B. Corrected 2020 attribution

Report corrected 2020 N/mean/median/win rate, signed excess sum, top-1%-removed mean, 1%-each-tail trimmed mean, global-top-set contribution to 2020 and full corrected cohort excluding 2020 as a diagnostic only.

### C. Corrected within-year tail sensitivity

For every evaluation year 2016–2020 report corrected N/mean/median/win rate, 1% removal count and mean, 1% two-sided trimmed mean, largest observation and top-five signed-excess contribution share.

### D. Deterministic corrected data sanity

For each global top-59 row require:

- non-empty issuer/ticker;
- required dates parse and remain before 2023;
- `evaluationSession <= entrySession <= targetExitSession`;
- finite positive entry open;
- finite corrected raw and corrected excess values;
- `valuationStatus=VALUED`;
- exact identity/date key agreement with the frozen canonical B1 metadata row selected by `eventNumber`.

A large corrected return is not itself a failure.

## Interpretation rules

- This audit cannot clear the corrected robustness warning gate by itself.
- No discovered ticker, issuer, year or return threshold may become an exclusion rule.
- No 2023+ OOS or HAC/calendar-time stage may be opened.
- If residual extreme observations expose a new deterministic data-validity problem, freeze a separate protocol before modifying any outcome.
- If sanity is clean, retain the observations and treat residual tail/year instability as a descriptive property of the corrected development sample.

## Required output

Persist deterministic JSON containing exact source run/artifact/digests, corrected primary-summary reproduction, global top-59 attribution, 2020 attribution, five within-year diagnostics, sanity failures, top-ten audit rows and guardrail flags:

- `researchOnly=true`;
- `oosOpened=false`;
- `productionScoringChanged=false`;
- `formalAlphaClaim=false`;
- `oosEligible=false`;
- `calendarTimeHacStageOpened=false`.

Tests must lock corrected/canonical join identity, 2023 hard fail, top-set cutoff/tie ordering, corrected-summary reproduction and sanity semantics before the real corrected top-59 identities are evaluated.
