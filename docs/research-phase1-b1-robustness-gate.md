# Phase-1 B1 dependence and tail-robustness gate

Frozen: 2026-09-17, after the canonical B1/B4 development summaries were persisted and **before** running the diagnostics specified here.

This is a research-only development gate. It does not change B1, B2, B4, production scoring, or the sealed OOS boundary.

## Motivation

Canonical B1's predeclared 126-session development result has a high arithmetic mean SPY-excess return (+9.79%) but a negative median (-3.35%) and a sub-50% excess win rate (44.06%). That pattern can arise from genuine right-skewed signal economics, but it can also be produced by repeated issuers, simultaneous signals, overlapping outcome windows, or a small number of extreme winners.

The next step is therefore **not** to optimize B1. It is to test how much of the observed mean survives fixed dependence and tail diagnostics.

## Frozen scope

- cohort: canonical B1 only;
- signal definition: unchanged;
- primary outcome: `excess_126`;
- secondary descriptive horizons: 21, 63 and 252 sessions;
- development event dates: 2016-01-01 through 2020-12-31;
- available outcomes: through 2022 only;
- 2023+ OOS: sealed and forbidden;
- event source: persisted canonical B1 `events.csv` from `research-phase1-baselines-v1` / run `35263058619`;
- no new SEC records or later signal confirmation may be used.

## Diagnostic family A — event-level tail concentration

For each horizon, and especially 126 sessions, report on mature exact-entry events:

1. arithmetic mean, median and win rate, reproduced from the canonical summary;
2. 1% and 5% two-sided trimmed means;
3. mean after removing only the top 1% and top 5% of excess-return observations;
4. P01/P05/P95/P99 quantiles;
5. share of aggregate positive excess contributed by the top 1%, 5% and 10% of positive observations;
6. share of the total signed excess sum contributed by the ten largest winners, reported as a concentration diagnostic only.

The canonical untrimmed mean remains the primary descriptive statistic. Trimmed and top-tail-removed means are diagnostics and must not replace it post hoc.

## Diagnostic family B — repeated-issuer dependence

At the 126-session horizon:

1. aggregate each issuer CIK to one equal-weight issuer observation by taking that issuer's mean mature `excess_126` across its retained B1 events;
2. report the number of issuers, issuer-equal-weight mean, median and win rate;
3. report event-count concentration by issuer: maximum, P95/P99, and share of events belonging to the top 1% of issuers by event count;
4. report the canonical event-weighted mean next to the issuer-equal-weight mean.

This tests whether repeated issuers materially dominate the event-level arithmetic mean without changing the B1 event set.

## Diagnostic family C — same-entry-session dependence

At the 126-session horizon:

1. aggregate all mature B1 events with the same `entrySession` to one equal-weight session-cohort observation using the mean `excess_126` for that entry session;
2. report session count, session-equal-weight mean, median and win rate;
3. report the distribution of event counts per entry session and the share of events occurring in the busiest 1% of entry sessions;
4. report the canonical event-weighted mean next to the session-equal-weight mean.

This prevents a day with many simultaneous B1 signals from receiving proportionally more descriptive weight in this diagnostic.

This is **not** a full calendar-time portfolio and must not be described as one because the persisted event file contains forward-window outcomes rather than the full daily path of every active position.

## Diagnostic family D — development-year stability

Using `entrySession` year and mature `excess_126`:

- report N, mean, median and win rate for each of 2016, 2017, 2018, 2019 and 2020;
- report the number of development years with positive mean excess;
- report the number of development years with positive median excess;
- report max-minus-min yearly mean spread.

No year is to be removed because of poor performance.

## Gate interpretation rules

No single p-value or arbitrary cutoff will be used to relabel B1 as alpha. The output is descriptive and must explicitly identify whether the high canonical mean is robust in direction and approximate magnitude to issuer weighting, entry-session weighting and tail removal.

The following findings are predeclared as **warning conditions** that block progression toward OOS until investigated:

- 126-session issuer-equal-weight mean <= 0;
- 126-session entry-session-equal-weight mean <= 0;
- 126-session top-1%-removed mean <= 0;
- fewer than 3 of the 5 development years have positive 126-session mean excess;
- top 1% of positive-return events contribute >= 50% of aggregate positive excess.

Absence of these warnings is **not** sufficient evidence of alpha or production readiness. It only permits proceeding to a separate, frozen daily-path/calendar-time inference design.

## Deferred formal dependence inference

A true calendar-time portfolio / HAC inference stage requires the daily market path of active event positions rather than only terminal forward returns. It is intentionally not approximated here by pretending irregular event-cohort observations are daily portfolio returns.

If this diagnostic gate does not raise a blocking warning, the subsequent design must be frozen before execution and should construct daily equal-weight active-position excess returns, specify overlap handling, and predeclare the HAC lag / inference procedure.

## Required output

The implementation should write one deterministic JSON summary with:

- `researchOnly=true`;
- `oosOpened=false`;
- `productionScoringChanged=false`;
- source-run/source-summary identifiers;
- all four diagnostic families above;
- explicit warning-condition booleans;
- `formalAlphaClaim=false`;
- `oosEligible` left false until a later explicit decision after the formal dependence-inference gate.

Tests must lock the aggregation, tail-cut and warning semantics before the real B1 event file is evaluated.
