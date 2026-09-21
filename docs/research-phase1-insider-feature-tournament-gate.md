# Phase-1 insider-feature tournament gate

Frozen: 2026-09-21 before any new feature-tournament outcome is read.

## Objective

Test whether a small, predeclared set of insider-information features provides
stable incremental separation beyond the completed simple benchmark family.

This is **not** a search for the largest in-sample arithmetic mean. The
benchmark synthesis shows that the simple B0 development mean exceeds the final
continuity-corrected B1/B3 and canonical B2/B4 means, while every benchmark has
a negative 126-session median and B1/B3 fail frozen right-tail robustness
gates.

The tournament therefore prioritizes stability, tail resistance, time
confirmation and coverage.

## Frozen benchmark anchors

Primary neutral reference:

- **B0** — any qualified open-market purchase.

Contextual benchmark/stratification references:

- **B1 continuity-corrected** — opportunistic purchase;
- **B2** — independent-owner cluster;
- **B3 continuity-corrected** — company net buying;
- **B4** — opportunistic + cluster intersection.

Primary horizon remains **126 XNYS sessions**. Secondary descriptive horizons
remain 21 / 63 / 252.

No benchmark definition may be changed during this tournament.

## Time boundary

The existing development period is internally split chronologically:

- **discovery:** 2016-01-01 through 2018-12-31 evaluation sessions;
- **confirmation:** 2019-01-01 through 2020-12-31 evaluation sessions.

2021-2022 remains untouched by feature selection and threshold tuning.

2023+ remains sealed.

The confirmation period may not be used to choose feature definitions,
cutpoints, orientation, transforms or family winners.

## Stage A — coverage and cutpoint freeze, no outcome read

Before any feature return is read:

1. build the feature matrix using PIT information available by signal formation;
2. publish coverage by year and required quality strata;
3. compute distribution cutpoints from **2016-2018 feature values only**;
4. freeze those cutpoints;
5. apply the same frozen cutpoints unchanged to 2019-2020;
6. do not read forward-return, SPY-excess, MAE or robustness fields in this
   stage.

Continuous feature bins use discovery-period empirical quintiles. The bin
construction is distribution-only and cannot use outcomes.

For two-dimensional holdings size, use discovery-period quintiles and define
`HIGH_HIGH` as both component variables in Q4 or Q5. This definition is
frozen before outcomes.

## Security-continuity precondition before Stage B outcomes

The B0 event universe is the neutral feature-tournament reference, but its
canonical descriptive return file has **not** received the same complete
scope-specific security-continuity program as corrected B1 and corrected B3.

Therefore:

- Stage A coverage/cutpoint work may proceed because it reads no outcomes;
- before Stage B discovery returns are computed, freeze the exact
  feature-tournament event/horizon scope;
- run a performance-blind security-continuity audit on that exact scope using
  the already-frozen B1/B3 continuity semantics/evidence wherever applicable;
- classify every affected row deterministically;
- require **zero unresolved rows** before tournament outcomes are opened;
- do not use canonical B0 return values to decide a continuity classification;
- the feature-tournament performance runner must consume the frozen corrected
  holder-outcome contract, not silently fall back to a later same-ticker bar.

This scope-specific continuity step may reuse already frozen B1/B3 evidence and
resolution rules, but may not change those rules after feature performance is
seen.

## Event unit

The tournament retains the frozen B0 issuer-event/execution clock and its
20-session issuer deduplication. It does not create transaction-row pseudo
events.

Owner-row features are attached to a B0 issuer event using only qualified
purchase rows known at formation.

Frozen event aggregators:

- event purchase dollars: sum of qualified purchase dollars;
- holdings-relative fraction: maximum valid owner-row fraction in the event;
- same-insider historical size percentile: maximum valid owner-row percentile
  in the event;
- D/I category: classify the full event as DIRECT_ONLY, INDIRECT_ONLY, MIXED,
  or UNKNOWN from its qualified purchase rows;
- issuer price/context variables: one PIT issuer value at evaluation time.

The maximum holdings-relative aggregator does not combine ownership
denominators across different owners.

## Feature family F1 — holdings-relative conviction

Predeclared variants:

- **F1_ABS_DOLLARS** — event purchase dollars; preferred group Q5 versus Q1-Q4;
- **F1_FRACTION_POST** — max purchased shares / post-transaction shares;
  preferred group Q5 versus Q1-Q4;
- **F1_FRACTION_PRE** — max purchased shares / reconstructed pre-transaction
  shares when internally consistent; preferred group Q5 versus Q1-Q4;
- **F1_OWNER_HISTORY_PERCENTILE** — max same-insider historical purchase-size
  percentile; preferred group Q5 versus Q1-Q4;
- **F1_ABS_PLUS_FRACTION_POST** — HIGH_HIGH indicator defined above versus all
  other valid observations.

PIT rules from R-014 remain controlling. Future amendments cannot repair an
earlier historical denominator. Missing/inconsistent denominators remain
missing.

At most **one** F1 variant may leave discovery as the frozen family candidate.

## Feature family F2 — direct versus indirect ownership

Primary contrast:

- **F2_DIRECT_VS_INDIRECT** — DIRECT_ONLY versus INDIRECT_ONLY.

MIXED and UNKNOWN are reported as separate descriptive strata but do not enter
the primary contrast.

No `D > I` scoring assumption is made. Discovery establishes the contrast
orientation, and that exact orientation is frozen for confirmation.

F2 has no alternative numeric transform and therefore no within-family
variant search.

## Feature family F3 — contrarian price context

Predeclared variants:

- **F3_RETURN_21** — bottom discovery quintile of trailing 21-session return
  versus Q2-Q5;
- **F3_RETURN_63** — bottom quintile versus Q2-Q5;
- **F3_RETURN_126** — bottom quintile versus Q2-Q5;
- **F3_RETURN_252** — bottom quintile versus Q2-Q5 when history is sufficient;
- **F3_DRAWDOWN_252** — deepest drawdown quintile versus Q1-Q4, where
  drawdown depth is non-negative `1 - price / trailing_252_high`;
- **F3_NEW_52W_LOW** — new-52-week-low state versus not-new-low.

These are contrarian-context tests, not automatic bonuses. No optimized
continuous drawdown coefficient is allowed.

At most **one** F3 variant may leave discovery as the frozen family candidate.

## Feature family F4 — insider purchase-basis state

The anchor must be frozen from qualified purchases public by formation time.
Later purchases/amendments cannot move the historical basis backward.

Predeclared variants:

- **F4_ABOVE_BASIS** — price at/above frozen purchase VWAP versus below;
- **F4_DISTANCE_ABOVE** — highest quintile of
  `price / frozen_purchase_vwap - 1` versus Q1-Q4;
- **F4_DISTANCE_BELOW** — lowest quintile of the same distance versus Q2-Q5;
- **F4_TRUE_RECLAIM** — prior eligible session below the same frozen basis and
  current eligible session at/above it versus eligible non-reclaim states;
- **F4_RECLAIM_PERSIST_2** — true reclaim that remains above for 2 sessions;
- **F4_RECLAIM_PERSIST_5** — true reclaim that remains above for 5 sessions.

This family tests insider-anchored state only. Generic moving-average,
Mansfield-RS, Weinstein/Kell/Wish/technical-turning features remain excluded
until a later Turning-overlay phase.

At most **one** F4 variant may leave discovery as the frozen family candidate.

## Mandatory quality/context strata — not tournament features

These variables are controls/coverage diagnostics and cannot win the feature
tournament by themselves:

- PIT market capitalization;
- trailing 20-session dollar ADV;
- trailing 60-session dollar ADV sensitivity;
- stock price;
- exchange/security-identity quality;
- amendment/quarantine state;
- postTransactionShares availability;
- calendar year.

Primary distribution strata for market cap, ADV and price are discovery-period
quintiles, frozen without outcomes.

A feature effect concentrated only in the bottom dollar-ADV quintile cannot
advance as a general feature.

## Coverage classes

Coverage is measured on frozen B0 exact-entry events in each relevant period.

### GENERAL_ELIGIBLE

A feature is eligible as a general/core candidate only if:

- overall feature coverage is at least **50%** of B0 exact-entry events; and
- coverage is at least **35% in every development year 2016-2020**.

### SPECIALTY_ELIGIBLE

If general coverage fails, a feature may remain a specialty/subgroup candidate
only if:

- overall coverage is at least **15%**; and
- coverage is at least **10% in every development year**.

A specialty candidate cannot become the default/core scoring feature from this
phase.

Anything below specialty coverage is coverage-diagnostic only; its outcome is
not used for tournament advancement.

These thresholds are frozen before feature coverage is measured.

## Fair comparison cohort

Every variant is evaluated against its complement **within the same
feature-observed cohort and time window**. Missing feature values never enter
the complement.

This prevents a clean-filings/coverage selection effect from masquerading as
feature separation.

Primary incremental effect:

`preferred-group 126d SPY-excess mean - complement 126d SPY-excess mean`.

The same contrast is also computed with issuer equal weighting and entry-session
equal weighting.

## Discovery advancement rule — 2016-2018 only

A variant can become its family's single frozen confirmation candidate only if
all of the following hold in discovery:

1. at least **200 mature 126-session observations** in the preferred group;
2. at least **100 distinct issuers** in the preferred group;
3. event-weighted incremental 126-session SPY-excess mean is positive;
4. issuer-equal-weight incremental mean is positive;
5. entry-session-equal-weight incremental mean is positive;
6. top-1%-removed event-weighted incremental mean is positive;
7. at least **2 of 3 discovery years** have positive incremental mean;
8. outside the bottom dollar-ADV quintile, incremental mean remains positive.

If multiple variants in one family satisfy all conditions, choose
lexicographically by:

1. highest top-1%-removed incremental mean;
2. then highest issuer-equal-weight incremental mean;
3. then highest entry-session-equal-weight incremental mean;
4. then highest ordinary event-weighted incremental mean;
5. then stable variant ID alphabetical order.

This selection tuple is frozen before outcomes.

If no variant passes, the family advances **no** candidate.

## Confirmation rule — 2019-2020, no reselection

The exact discovery-selected family variant, cutpoints and contrast are applied
unchanged.

A family candidate is marked
`CONFIRMED_DEVELOPMENT_CANDIDATE` only if all of the following hold:

1. preferred-group mature N >= 150;
2. distinct issuers >= 75;
3. pooled 2019-2020 event-weighted incremental mean > 0;
4. pooled issuer-equal-weight incremental mean > 0;
5. pooled entry-session-equal-weight incremental mean > 0;
6. pooled top-1%-removed incremental mean > 0;
7. **2019 incremental mean > 0**;
8. **2020 incremental mean > 0**;
9. incremental mean outside the bottom dollar-ADV quintile > 0.

There is no alternate threshold, direction, bucket or replacement variant if
confirmation fails.

## Multiple-testing control

No IID event-level p-value is used as a tournament PASS criterion.

Multiplicity is controlled structurally by:

- a finite feature list frozen in this document;
- distribution-only cutpoints frozen before outcomes;
- one candidate maximum per family after discovery;
- chronological 2019-2020 confirmation with no reselection;
- no composite feature weights fitted in this phase;
- no new variants added after discovery results.

Formal dependence-aware inference, if later authorized, requires a separate
predeclared gate.

## Relation to simple benchmarks

The tournament's primary incremental comparison is within the B0 event universe.

For every discovery-selected and confirmation-tested candidate also report:

- overlap and subgroup result within B1 where available;
- overlap and subgroup result within B2 where available;
- overlap with B3 positive-net events where exact event alignment exists;
- overlap with B4.

These are diagnostic controls, not extra selection opportunities.

A candidate is not promoted merely because it recreates B1/B2/B3/B4.

## Frozen outcome reporting

For discovery and confirmation report at minimum:

- coverage / missingness;
- mature N and distinct issuers;
- preferred and complement raw/SPY-excess mean and median;
- preferred and complement excess win rate;
- incremental event-weighted mean;
- incremental issuer-EW mean;
- incremental entry-session-EW mean;
- top-1%-removed incremental mean;
- year-specific incremental means;
- market-cap / ADV / price strata;
- overlap with B1/B2/B3/B4.

Secondary horizons 21/63/252 are descriptive and cannot reverse a primary 126d
failure.

## Progression boundary

A confirmed development candidate is only a **candidate for later frozen
validation**, not proof of alpha and not authorization for production.

This gate does not:

- open 2021-2022 validation for selection;
- open 2023+ OOS;
- open HAC;
- authorize production score changes;
- authorize technical/Turning features.

The generic Turning overlay remains a separate later phase after the
insider-feature tournament is frozen and understood.
