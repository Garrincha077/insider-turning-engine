# Phase-1 B1 continuity-corrected temporal-clustering diagnostic gate

Frozen: 2026-09-18, after the continuity-corrected robustness gate remained blocked and after the residual corrected tail/year attribution audit completed with no deterministic sanity failures, but **before computing any new temporal-clustering diagnostic described below**.

This is a development-only descriptive diagnostic. It is not a new signal definition, not a parameter search, not a regime filter, not a calendar-time portfolio, and not HAC inference.

## Motivation

The already frozen corrected robustness gate remains controlling:

- `blockingWarningPresent=true`;
- `BLOCK_HAC_AND_OOS`;
- `calendarTimeHacStageOpened=false`;
- `oosEligible=false`.

The residual corrected tail/year audit found that 2016 and 2020 remain positive while 2017–2019 remain negative after deterministic continuity correction and tail sensitivity checks. The permitted question is therefore narrower: **how temporally concentrated is the corrected development evidence within 2016–2020?**

The purpose is to characterize clustering and year/regime instability without creating any exclusion, threshold or production-scoring rule from the answer.

## Frozen sources

Corrected outcome source:

- GitHub Actions run `35277369958`;
- artifact `phase1-b1-continuity-corrected-performance-35277369958`;
- digest `sha256:d750c85b6019740ad381b2f53a9d6ceb379a5665cf8b43f0c70e799484bfa775`.

Canonical B1 metadata source, used only for fields not duplicated in the corrected long-format artifact:

- GitHub Actions run `35263058619`;
- artifact `phase1-b1-b4-development-35263058619`;
- digest `sha256:1021de09ebaa190604bf1762714fe014ebc75e3e197b47d2d684003289ed638d`.

No new SEC evidence, market history, corporate-action decisions or 2023+ data may be read.

## Scope

- B1 definition unchanged.
- Development cohort clock: canonical `evaluationSession`, 2016-01-01 through 2020-12-31.
- Primary horizon: 126 XNYS sessions.
- Primary value: continuity-corrected `correctedExcess` at horizon 126.
- Mature observation: `valuationStatus=VALUED` and finite corrected excess.
- Outcomes through 2022 only.
- 2023+ is a hard failure.
- `researchOnly=true`.
- `oosOpened=false`.
- `productionScoringChanged=false`.
- `formalAlphaClaim=false`.
- `calendarTimeHacStageOpened=false`.

## Frozen diagnostics

The following diagnostics are frozen before execution.

### A. Calendar-bucket cohort summaries

Using `evaluationSession`, aggregate the corrected mature 126-session observations by:

1. calendar month (`YYYY-MM`), and
2. calendar quarter (`YYYY-Qn`).

For every bucket report:

- N;
- mean corrected excess;
- median corrected excess;
- win rate;
- signed excess sum;
- number of unique issuers;
- largest issuer event count within the bucket.

No bucket may be dropped because of its result.

### B. Temporal concentration

Across monthly and quarterly buckets report:

- number of non-empty buckets;
- share of all events in the five busiest buckets;
- share of full signed excess contributed by the five highest signed-excess buckets;
- share of full positive excess contributed by the five highest positive-excess buckets;
- maximum bucket event count and its share of all events;
- Herfindahl-Hirschman concentration index of event counts across buckets, using count shares that sum to one.

For signed-excess shares, values above 100% or below 0% are permitted when the complement has offsetting signed contribution. They are descriptive, not failures.

### C. Positive/negative bucket stability

For monthly and quarterly buckets report:

- count and share of buckets with positive mean corrected excess;
- count and share with positive median corrected excess;
- count and share with win rate above 50%;
- longest consecutive run of positive-mean buckets;
- longest consecutive run of non-positive-mean buckets.

Calendar sequence must include every non-empty bucket in chronological order. Empty calendar buckets are not fabricated and do not break or extend runs.

### D. Year leave-one-out attribution

For each development year 2016–2020, remove that year's observations **for attribution only** and report the remaining cohort:

- N;
- mean corrected excess;
- median corrected excess;
- win rate;
- signed excess sum.

This does not authorize a year exclusion rule.

### E. Entry-session clustering reproduction

Reproduce, from the same corrected mature 126-session cohort, entry-session clustering quantities already used in the corrected robustness audit:

- number of unique entry sessions;
- maximum events on one entry session;
- P95 and P99 event counts per entry session;
- share of events contained in the busiest 1% of entry sessions.

This is a reproduction/consistency check, not a new progression gate.

## Interpretation restrictions

This diagnostic cannot:

- clear the existing corrected robustness warning gate;
- open HAC/calendar-time inference;
- open 2023+ OOS;
- create a month, quarter, year, ticker, issuer, sector, market-cap or return exclusion rule;
- change B1/B2/B4;
- change continuity decisions;
- change production scoring.

If temporal concentration is strong, record it as a descriptive property of the development sample. If concentration is weak but sign instability remains, record that sign instability is broader than a small number of calendar clusters.

No threshold from this audit is a pass/fail criterion.

## Deferred future hypothesis work

A later, separately frozen phase may investigate characteristics shared by the largest valid winners, including technical state, insider-purchase structure, issuer fundamentals, liquidity/size, valuation, market regime and other economically motivated factors. That work is explicitly out of scope here and must not use its findings to rewrite this frozen B1 development result.

## Required machine-readable output

Persist deterministic JSON containing:

- exact source run/artifact/digests;
- exact corrected 126-session primary-summary reproduction;
- monthly bucket rows and concentration/stability summary;
- quarterly bucket rows and concentration/stability summary;
- five leave-one-year-out rows;
- entry-session clustering reproduction;
- `diagnosticOnly=true`;
- `newFilterCreated=false`;
- `researchOnly=true`;
- `formalAlphaClaim=false`;
- `oosEligible=false`;
- `oosOpened=false`;
- `calendarTimeHacStageOpened=false`;
- `productionScoringChanged=false`.

Tests must lock 2023+ hard-fail behavior, exact corrected/canonical event identity join, bucket assignment, run-length arithmetic, concentration arithmetic, leave-one-year-out semantics, primary-summary reproduction and all guardrail flags before the real frozen artifacts are evaluated.
