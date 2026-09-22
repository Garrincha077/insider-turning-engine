# Monster Winner Enrichment v1 — outcome execution gate

Frozen: 2026-09-22 after the performance-blind holder-path feasibility audit
and before any MFE value, threshold crossing or monster label is read.

## Purpose

Open Monster Winner Enrichment v1 outcomes in the already-predeclared
chronological order while preventing incomplete market paths from creating an
artificially high monster hit rate.

This gate does not change the Monster Winner objective, thresholds, feature
families, discovery/confirmation years or family tie-break. It freezes the
exact holder-value engine and missing-label denominator semantics before price
outcomes are opened.

## Immutable upstream contracts

Monster Winner definition:
- `docs/research-monster-winner-enrichment-v1-gate.md`;
- `research/monster-winner-enrichment-v1.json`;
- definition: `MONSTER_WINNER_ENRICHMENT_V1`.

Performance-blind path audit:
- workflow run: **35729304894**;
- release: `research-monster-winner-enrichment-path-feasibility-v1`;
- archive: `monster-winner-path-feasibility-v1.tar.gz`;
- archive SHA-256:
  `sha256:311482bf583cb8c9d0e7e4ebcef6cf29149bc92ffc1ab5842a772c0ae7f5ad38`;
- summary SHA-256:
  `sha256:8cf04cfbf67471a84d35e393ca831d2dac47cc6f8d0909d93df3163d6eda927e`.

Feasibility result, observed before any MFE price:
- source events: **24,190**;
- negative-label feasible: **22,293 (92.1579%)**;
- no-crossing would remain `MFE_UNKNOWN`: **1,897 (7.8421%)**;
- path coverage below 95%: **1,868**;
- internal gap >5 sessions: **1,193**;
- mandatory unvalued consideration: **2**.

The reason counts overlap.

This pattern is dominated by ordinary historical market-path incompleteness:
1,814 of the 1,897 non-feasible events are
`PRICE_CONTINUOUS_ADJUSTED` transformation-kind rows. No price-blind
corporate-action remediation is expected to repair those ordinary missing
market observations without introducing an alternate-data/substitution policy.

Therefore v1 proceeds with explicit unknowns rather than filling gaps.

## Primary missing-label amendment

The original Monster Winner v1 gate described
`monster_hit_rate = positives / evaluable events`.

The performance-blind feasibility audit established that 7.8421% of events can
be one-sided observable: an observed threshold crossing can prove a positive
monster, while absence of an observed crossing cannot always prove a negative.

To prevent a feature with more incomplete paths from receiving a favorable
smaller denominator, the **primary advancement metric is amended before any
monster outcome is read**.

### Primary observed-positive density

For every feature-observed comparable cohort:

`M100_observed_positive_density = observed_M100_positives / all_feature_observed_events`

All feature-observed events remain in this denominator, including
`MFE_UNKNOWN` no-crossing events.

### Primary lift

`M100_lift = preferred_observed_positive_density / complement_observed_positive_density`

The frozen discovery and confirmation lift thresholds from Monster Winner v1
apply to this conservative density-based lift.

### Capture

`M100_capture = preferred_observed_M100_positives / all_observed_M100_positives_in_comparable_cohort`

Unknown no-crossing rows stay in the review universe but never enter the
positive numerator.

### Secondary evaluable hit rate

Also report:
`M100_evaluable_hit_rate = positives / (positives + proven_negatives)`.

This is diagnostic only and cannot advance a feature.

Report preferred/complement unknown shares explicitly.

## Exact label states

For each threshold/window, every event is exactly one of:

- `POSITIVE`: at least one exact observed holder-value close crosses the
  frozen threshold;
- `NEGATIVE`: no crossing is observed and the applicable path meets the
  frozen >=95% coverage, <=5-session maximum-gap and complete-consideration
  rules;
- `UNKNOWN`: no crossing is observed but a negative label is not justified.

A positive label has priority once a valid crossing is observed.

No missing session may be imputed or replaced by the nearest/later bar.

## Price fields authorized at outcome stage

Only after this gate is frozen, the discovery runner may read:

- historical exact entry-session `open`;
- exact regular-session `close` values along the holder path.

It does not use intraday `high` for v1 labels.

Daily high MFE remains descriptive-only and is not opened in v1 discovery.

The primary +100% label therefore means a closing holder value at least
2.00 times the entry-open holder value.

## Holder-value engine

The runner must reuse the frozen Stage-B continuity semantics and the frozen
provider completeness amendment.

For one entry share:

### Ordinary adjusted continuity
- entry value: original adjusted ticker exact entry-session open;
- path value: one adjusted share at each exact regular close.

### Adjusted stock dividend
- same adjusted ticker market quantity = 1;
- legal stock-dividend quantity remains audit metadata only.

### Same-security symbol change
- original security before effective date;
- successor security on/after effective date;
- frozen one-for-one quantity unless the frozen contract states otherwise.

### Stock merger
- original security before effective date;
- on/after effective date:
  `cash + successor_quantity × successor_close`.

### Cash merger / redemption
- original security before effective date;
- on/after effective date: frozen cash consideration, constant through the
  remaining opportunity window.

### Multi-component consideration
- original before effective date;
- on/after effective date:
  frozen cash plus the sum of every frozen basket
  `quantity × exact_component_close`;
- a session is unobservable if any mandatory component lacks an exact regular
  bar.

### Discontinuous incomplete valuation
- original security may be valued before the frozen discontinuity date;
- on/after the discontinuity mandatory holder value is unavailable;
- a pre-discontinuity crossing can still be POSITIVE;
- otherwise the label is UNKNOWN.

## Opportunity windows and thresholds

Entry-session close is observation index 0.

Primary:
- `M100_252_CLOSE`: holder value >= 2.00 × entry open on any exact close
  from entry session through XNYS entry+252.

Secondary:
- `M50_252_CLOSE`: >= 1.50×;
- `M200_252_CLOSE`: >= 3.00×;
- `M500_252_CLOSE`: >= 6.00×;
- `M100_126_CLOSE`: >= 2.00× through entry+126;
- `M200_126_CLOSE`: >= 3.00× through entry+126.

For the 126-session labels, the same >=95% / <=5 missing-session negative
eligibility rule is recalculated on the 127-session local path.

## Discovery opening boundary

The first outcome run may score only events with:
`evaluationSession <= 2018-12-31`.

Expected frozen discovery events: **14,340**.

Market years after 2018 may be mounted only to mature those already-selected
discovery events through their frozen 252-session window.

No event evaluated in 2019-2020 may be scored during discovery.

2021-2022 event outcomes remain unopened by this discovery run.
2023+ remains sealed.

## Variant grouping

Use Stage-A cutpoints unchanged.

F1, F3 and F4 preserve their predeclared preferred/complement definitions.

F2 is explicitly two Monster Winner variants:
- `F2_INDIRECT_VS_DIRECT`: INDIRECT_ONLY preferred, DIRECT_ONLY complement;
- `F2_DIRECT_VS_INDIRECT`: DIRECT_ONLY preferred, INDIRECT_ONLY complement.

MIXED/UNKNOWN ownership is outside both primary F2 contrasts.

## Discovery advancement

The frozen Monster Winner v1 discovery checks remain:

1. preferred cohort N >= 200;
2. preferred distinct issuers >= 100;
3. preferred observed M100 positives >= 20;
4. review share <= 50%;
5. primary density-based M100 lift >= 1.50x;
6. observed M100 capture >= 20%;
7. primary density-based M100 lift >1 in at least 2/3 discovery years;
8. density-based M100 lift outside bottom ADV quintile >=1.25x;
9. M200 density-based lift >1 when comparable cohort has >=10 observed M200
   positives;
10. no issuer supplies >15% of preferred M100 positives.

Unknown/no-crossing rows remain in relevant cohort denominators.

Family tie-break remains:
1. M100 capture efficiency;
2. M100 lift;
3. M200 lift when evaluable;
4. M100 capture;
5. lower review share;
6. variant ID alphabetical.

At most one variant per family advances.

## Required discovery reporting

For every variant:
- observed cohort N;
- preferred/complement N;
- preferred/complement M100 POSITIVE/NEGATIVE/UNKNOWN counts;
- primary observed-positive densities;
- density-based lift;
- secondary evaluable hit rates;
- unknown shares;
- M100 capture;
- review share/reduction;
- capture efficiency;
- M50/M200/M500 diagnostics;
- 126-session monster diagnostics;
- year-specific M100 density/lift;
- outside-bottom-ADV M100 density/lift;
- largest issuer share of preferred M100 positives;
- largest entry-session share of preferred M100 positives;
- top-tail MFE diagnostics restricted to path-negative-feasible rows, with
  incomplete-path observed maxima reported separately if desired.

## Progression boundary

A successful discovery run may freeze at most one Monster Winner candidate per
F1/F2/F3/F4 family for unchanged 2019-2020 confirmation.

It does not:
- use 2019-2020 outcomes for discovery selection;
- call 2021-2022 fresh validation;
- open 2023+ OOS;
- add technical/fundamental overlays;
- fit composite weights;
- change production scoring.
