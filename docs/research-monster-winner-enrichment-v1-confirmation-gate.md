# Monster Winner Enrichment v1 — confirmation binding gate

Frozen: 2026-09-22 after immutable 2016-2018 Monster Winner discovery and
before any 2019-2020 monster/MFE outcome is read.

## Immutable discovery result

Workflow run:
**35730351909 — SUCCESS**

Release:
`research-monster-winner-enrichment-discovery-v1`

Result:
`monster-discovery-results.json`

SHA-256:
`sha256:e3d081908a3b72dd4fd36e3d58b1aa38f132371ebcd1821ae771715386a61588`

Archive SHA-256:
`sha256:d3a7e162532e5ff8626f0c257d33ffc489e7aef873586b51e9a5c8a04db43501`

Discovery scope:
- evaluation years: 2016-2018 only;
- events: **14,340**;
- M100/252 positives: **1,250**;
- M200/252 positives: **321**;
- M500/252 positives: **47**;
- 2019-2020 event outcomes were not opened;
- 2021-2022 known-sample diagnostics were not opened;
- 2023+ remained sealed.

## Frozen family result

Only two families produced a discovery candidate under the predeclared
Monster Winner v1 advancement checks.

### F3

Frozen candidate:
`F3_DRAWDOWN_252`

Formation rule is unchanged from Stage A:
- feature: `1 - evaluation_close / trailing_252_high`;
- Stage-A discovery cutpoints remain frozen;
- preferred group: **Q5 deepest drawdown**;
- complement: Q1-Q4.

Frozen discovery selection tuple:
- M100 capture efficiency: **2.5996395839769333**;
- M100 lift: **4.33314022100633**;
- M200 lift: **7.09943933617403**;
- M100 capture: **0.5200803212851406**;
- review share: **0.20005862523816503**.

The Stage-A coverage-class label is `BELOW_SPECIALTY` because the 252-session
formation feature is unavailable in the early history needed for 2016.
This does not alter the already-frozen Monster v1 discovery rule, which
required positive lift in at least 2 of 3 discovery years and did not add the
old mean-separation coverage-class gate. No post-discovery coverage rule is
introduced here.

### F4

Frozen candidate:
`F4_DISTANCE_BELOW`

Formation rule:
- source: `F4_DISTANCE_TO_BASIS`;
- basis: frozen 90-calendar-day insider purchase basis from Stage A;
- preferred: Q1 lowest distance to basis;
- complement: Q2-Q5;
- cutpoint remains the original 2016-2018 Stage-A cutpoint.

Frozen discovery selection tuple:
- M100 capture efficiency: **1.535617991979141**;
- M100 lift: **1.7731089884227222**;
- M200 lift: **2.0472973782643304**;
- M100 capture: **0.30718954248366015**;
- review share: **0.20004294302891498**.

### F1 and F2

No F1 or F2 variant advances.

In particular:
- `F2_INDIRECT_VS_DIRECT` M100 lift = **1.1525712478347898**, below the
  frozen 1.50 discovery threshold;
- `F2_DIRECT_VS_INDIRECT` M100 lift = **0.8676253219734495** and its
  review share exceeds 50%.

They may not be reoriented, combined or substituted in confirmation.

## Confirmation scope

Evaluation sessions:
- 2019-01-01 through 2020-12-31.

Expected Stage-A events:
- 2019: **4,529**;
- 2020: **5,321**;
- total: **9,850**.

The exact Stage-A feature values and 2016-2018 cutpoints are applied unchanged.

No new feature variant, threshold or direction may be selected.

## Outcome / path semantics

Reuse without change:
- `MONSTER_WINNER_ENRICHMENT_V1_OUTCOME_EXECUTION`;
- close-path M100/252 primary label;
- exact entry-session open;
- exact regular-session closes;
- frozen security-continuity routing;
- positive / negative / unknown label semantics;
- unknown no-crossing rows remain in the primary observed-positive-density
  denominator;
- no nearest/later-bar substitution.

Market years after 2020 may be mounted only to mature already-selected
2019-2020 events through their frozen 252-session opportunity window.

No 2021-2022 event may be evaluated or feature-scored.

## Frozen confirmation checks

For each of the two frozen candidates, all are required:

1. preferred **label-resolvable** M100 N
   (`POSITIVE + NEGATIVE`) >= **150**;
2. preferred distinct issuers >= **75**;
3. preferred observed M100 positives >= **10**;
4. pooled primary density-based M100 lift >= **1.25×**;
5. pooled observed M100 capture >= **15%**;
6. 2019 primary M100 lift > **1.00×**;
7. 2020 primary M100 lift > **1.00×**;
8. outside-bottom-dollar-ADV primary M100 lift > **1.00×**;
9. no single issuer supplies more than **20%** of preferred observed M100
   positives.

Primary density is still:
`observed positives / all feature-observed group events`.

The evaluable hit rate
`positives / (positives + proven negatives)`
is secondary diagnostic only.

There is no replacement candidate if F3 or F4 fails.

## Confirmation output

Report for each frozen candidate:
- preferred/complement cohort N;
- POSITIVE / NEGATIVE / UNKNOWN;
- label-resolvable N;
- observed-positive densities;
- evaluable hit rates;
- M100 lift;
- M100 capture;
- review share;
- unknown share;
- 2019 and 2020 lift;
- outside-bottom-ADV lift;
- largest issuer share of preferred M100 hits;
- secondary M50/M200/M500 and 126-session diagnostics.

## Progression

A candidate that passes all nine checks becomes
`MONSTER_CONFIRMED_DEVELOPMENT_CANDIDATE`.

A confirmed development candidate is not production evidence.

After confirmation:
- 2021-2022 may only be opened under a separate, explicitly labelled
  `KNOWN_SAMPLE_RETROSPECTIVE_DIAGNOSTIC` gate;
- it may never be called untouched validation;
- 2023+ remains sealed until explicit owner authorization and a separate
  frozen OOS gate;
- technical/fundamental overlays remain separate;
- production scoring remains unchanged.
