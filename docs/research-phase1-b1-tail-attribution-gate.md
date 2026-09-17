# Phase-1 B1 tail/year attribution gate

Frozen: 2026-09-17, after the B1 robustness gate produced a blocking warning and **before inspecting the identities of the extreme B1 winners**.

This is an explanatory development-only audit. It does not create, optimize or approve a new signal filter. It must not open 2023+ OOS or change production scoring.

## Motivation

Canonical B1 has 5,944 mature 126-session observations and a +9.7882% arithmetic mean SPY-excess return, but the frozen robustness gate found that removing only the largest 1% of observations makes the mean negative and that only two of five development years have positive mean excess. The largest full-period contribution also coincides with 2020.

The purpose of this gate is to identify what is driving that tail/year concentration and whether the extreme observations look like coherent B1 outcomes or potential data/corporate-action problems. It is **not** to derive an ex-post exclusion rule.

## Frozen source and boundaries

- source cohort: persisted canonical B1 only;
- source run: `35263058619`;
- primary field: `excess_126`;
- mature observation requirement: non-null `excess_126`;
- cohort clock: canonical `evaluationSession`;
- development evaluation sessions: 2016–2020;
- outcomes through 2022 only;
- any date in 2023+ is a hard failure;
- production scoring remains unchanged;
- 2023+ OOS remains sealed.

For the canonical mature N = 5,944, the global top-1% audit set is frozen as the **59 largest `excess_126` observations** (`floor(5944 * 0.01)`). Ties at the cutoff are resolved deterministically by descending `excess_126`, then `evaluationSession`, issuer CIK and ticker.

## Audit family A — global top-1% attribution

For those 59 events report:

1. count and aggregate `excess_126` sum;
2. share of the full mature cohort's signed excess sum;
3. number of unique issuer CIKs and tickers;
4. maximum repeats for any issuer and ticker;
5. distribution by `evaluationSession` year;
6. share of the 59 events belonging to 2020;
7. issuer/ticker concentration: top issuer/ticker event count and share;
8. top ten events by `excess_126`, preserving issuer CIK, ticker, evaluation session, entry session, exit session, entry open, raw 126 return, excess 126 return, opportunistic-owner count and raw opportunistic purchase rows.

The top-ten table is audit evidence only, not a watchlist or recommendation.

## Audit family B — 2020 attribution

For mature 2020 evaluation-session events report:

1. N, mean, median and win rate;
2. signed excess sum;
3. top-1%-removed mean using `floor(N * 0.01)` highest observations;
4. 1% two-sided trimmed mean using the same deterministic cut semantics as the robustness gate;
5. contribution of the global top-59 observations that are from 2020 to the 2020 signed excess sum;
6. mean, median and win rate for the full canonical cohort excluding all 2020 evaluation-session events, explicitly as a diagnostic rather than a new model.

No year may be removed from the canonical result or production signal because of this audit.

## Audit family C — within-year tail sensitivity

For each development evaluation year 2016–2020:

- mature N;
- canonical mean/median/win rate;
- number removed at 1% (`floor(N * 0.01)`);
- top-1%-removed mean;
- 1% two-sided trimmed mean;
- largest single `excess_126` observation;
- top five observations' share of that year's signed excess sum.

This determines whether the extreme-tail problem is unique to 2020 or recurrent across development years.

## Audit family D — deterministic data sanity

For every global top-59 event verify and report:

- all required dates parse;
- no required date is in 2023+;
- `evaluationSession <= entrySession <= exit_126`;
- `entryOpen > 0` and finite;
- `raw_126` and `excess_126` are finite;
- issuer CIK and ticker are non-empty.

Do not automatically exclude an observation merely because its return is large. Large-return observations require separate market/corporate-action verification if this audit identifies them as influential.

## Interpretation rules frozen before identities are viewed

- This audit cannot promote B1 to OOS eligibility.
- No ticker, issuer, year, industry, market-cap group or return threshold discovered here may be converted into an exclusion/filter without a separate predeclared hypothesis and new development test.
- If one or a few issuers account for a material part of the top-59 set or signed excess sum, record concentration but do not delete them.
- If extreme observations show suspicious price-return mechanics, freeze a separate corporate-action/market-data verification protocol before deciding whether any record is invalid.
- If the observations appear data-consistent, retain them and treat the finding as genuine heavy-tail instability.

## Required output

Write one deterministic JSON summary containing:

- `researchOnly=true`;
- `oosOpened=false`;
- `productionScoringChanged=false`;
- `formalAlphaClaim=false`;
- `oosEligible=false`;
- source run and source-file identifiers;
- the global top-1% audit;
- 2020 attribution;
- all five within-year diagnostics;
- top-59 sanity results;
- top-ten audit rows;
- a flag indicating whether any deterministic sanity failure was found.

The implementation tests must lock cutoff/tie-break, year attribution, 2020 exclusion and sanity-check semantics before real top-event identities are inspected.
