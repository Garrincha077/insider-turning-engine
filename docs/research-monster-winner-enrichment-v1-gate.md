# Monster Winner Enrichment v1 — predeclared research gate

Frozen: 2026-09-22 after completion of the Phase-1 mean-separation feature
tournament and **before any monster-tail/MFE outcome is computed for this new
research objective**.

## Why this is a separate research track

The completed Phase-1 feature tournament asked whether an insider feature
produced stable average SPY-excess separation versus its complement. F2
`DIRECT_VS_INDIRECT` failed that frozen validation rule.

That is not the same objective as the intended active-investor workflow.

The owner’s practical objective is to use insider information as an
**opportunity screener**: concentrate the candidate pool toward rare, very large
future winners, then apply a separate later layer of technical judgment,
fundamental review and risk management before capital is committed.

Therefore this version does **not** reinterpret the completed F2 result. It
creates a new target variable and a new evaluation framework.

## Research question

> Does an insider-derived feature materially increase the density and capture
> rate of future monster winners relative to the neutral B0 insider-purchase
> universe, while reducing the number of stocks that require later review?

The goal is enrichment/ranking, not a high ordinary win rate and not a positive
median return.

## Time boundary

### Design / feature selection

Primary design cohort:
- evaluation sessions 2016-01-01 through 2020-12-31;
- same strict B0 feature-tournament event boundary: **24,190 exact-entry
  events / 4,729 issuers**;
- existing 20-XNYS-session issuer dedup remains unchanged.

Internal chronological split remains:
- discovery: 2016-2018;
- confirmation: 2019-2020.

### 2021-2022

2021-2022 are **not untouched validation anymore** because the completed F2
validation result is known.

They may later be used only as a clearly labelled
`KNOWN_SAMPLE_RETROSPECTIVE_DIAGNOSTIC` after the monster framework is frozen.
They may not be presented as fresh validation and may not be used to justify
calling a rule externally validated.

### 2023+

2023+ remains sealed. This gate does not authorize reading 2023+ filings,
market outcomes or performance.

A future OOS opening requires an additional explicit owner authorization and a
separate frozen execution gate.

## Event and entry semantics

- event unit: frozen B0 issuer event;
- entry: exact next XNYS regular-session open;
- no nearest/later-bar entry substitution;
- historical ticker/security identity remains PIT-safe;
- missing/delisted outcomes are never silently dropped;
- continuity transformations must use frozen performance-blind security
  contracts where available and must be resolved before negative MFE labels are
  assigned.

## Primary monster label

Primary opportunity window: **252 XNYS sessions after entry**.

Primary label:

`M100_252_CLOSE`

A positive label requires observed holder value at an exact eligible regular
session close within the first 252 XNYS sessions to reach at least:

`2.00 × entry holder value`

which is a **+100%** return from the exact entry-open value.

This is a path/opportunity label, not merely the terminal 252-session return.

## Secondary monster labels

Also report, without changing the primary advancement rule:

- `M50_252_CLOSE`  — at least +50%;
- `M200_252_CLOSE` — at least +200%;
- `M500_252_CLOSE` — at least +500%;
- `M100_126_CLOSE` — +100% within 126 sessions;
- `M200_126_CLOSE` — +200% within 126 sessions.

Daily-high MFE may be reported as a **descriptive diagnostic only**. It cannot
replace the primary close-based label in v1.

## Holder-value path semantics

For a one-entry-share starting position:

1. entry value is one historical entry share valued at the exact entry-session
   open;
2. before a transformation, holder value follows the historical security;
3. on a frozen effective date, holder quantities/cash change according to the
   frozen continuity contract;
4. successor shares are valued only on exact regular-session observations;
5. cash consideration is retained as cash and is not reinvested;
6. multi-component baskets are valued only when every required component has an
   exact supported value under the frozen contract;
7. unvalued mandatory consideration makes the path incomplete rather than
   silently assigning zero;
8. ordinary distributions already represented in the frozen adjusted-market
   semantics are not double counted.

## MFE missing-data rule

Positive monster labels are one-sided and monotone:

- once an exact observed holder-value close crosses the threshold, the monster
  label is positive even if a later market-data gap occurs.

A negative monster label requires all of:

- exact entry;
- zero unresolved security continuity for the event path;
- at least **95%** of required holder-value sessions observable over the
  applicable window;
- no internal run of more than **5 consecutive missing XNYS sessions** before
  the end of the applicable window;
- no mandatory unvalued holder-consideration leg.

If these conditions fail and no threshold was observed, the label is
`MFE_UNKNOWN`, not negative.

## Primary screening metrics

For each feature variant and its same-observation complement report:

### Monster density / precision

`monster_hit_rate = M100 positive events / M100 evaluable events`

Report as:
- percentage;
- monsters per 100 reviewed candidates;
- candidates reviewed per monster = `1 / hit_rate`.

### Lift

`M100 lift = preferred M100 hit rate / comparable B0/complement M100 hit rate`

Primary comparison is within the same feature-observed cohort so feature
missingness cannot create artificial enrichment.

### Capture / recall

`M100 capture = M100 monsters inside preferred group / all M100 monsters in the comparable cohort`

### Review share

`review_share = preferred evaluable events / comparable evaluable events`

Also report review reduction `1 - review_share`.

### Capture efficiency

`capture_efficiency = M100 capture / review_share`

This answers how much of the monster population is retained per unit of review
budget.

## Tail diagnostics

Also report:

- M50, M200 and M500 hit rate / lift / capture;
- top-10%, top-5%, top-1% and top-0.5% 252-session close-MFE enrichment;
- distinct monster issuers;
- distinct monster entry sessions;
- monster counts by year;
- largest single-issuer share of monster hits;
- largest single-entry-session share of monster hits;
- 252-session terminal raw and SPY-excess return as descriptive context only.

Ordinary median return and ordinary win rate are descriptive diagnostics, not
advancement criteria in this track.

## Candidate feature families

v1 reuses the already PIT-defined insider-only families without changing their
formation semantics:

### F1 — holdings-relative conviction
- F1_ABS_DOLLARS;
- F1_FRACTION_POST;
- F1_FRACTION_PRE;
- F1_OWNER_HISTORY_PERCENTILE;
- F1_ABS_PLUS_FRACTION_POST.

### F2 — direct versus indirect ownership
Evaluate both predeclared orientations under the new monster objective:
- INDIRECT_ONLY versus DIRECT_ONLY;
- DIRECT_ONLY versus INDIRECT_ONLY.

This does **not** reverse or reinterpret the completed Phase-1 F2 validation.
Monster-specific outcomes have not yet been read under this v1 objective.

### F3 — contrarian price context
- F3_RETURN_21;
- F3_RETURN_63;
- F3_RETURN_126;
- F3_RETURN_252;
- F3_DRAWDOWN_252;
- F3_NEW_52W_LOW.

### F4 — insider purchase-basis state
- F4_ABOVE_BASIS;
- F4_DISTANCE_ABOVE;
- F4_DISTANCE_BELOW;
- F4_TRUE_RECLAIM;
- F4_RECLAIM_PERSIST_2;
- F4_RECLAIM_PERSIST_5.

No technical Turning/Kell/Wish/Weinstein/Mansfield feature enters Monster
Enrichment v1. Those are intentionally reserved for the later user-controlled
technical filter layer.

## Benchmark/context screens

B1/B2/B3/B4 overlap may be reported as enrichment context, but they are not new
feature-family variants and cannot create additional tuning degrees of freedom.

## Discovery advancement — 2016-2018

A variant may become its family’s single monster-enrichment candidate only if
all of the following are true on the primary M100/252-close label:

1. preferred evaluable N >= **200**;
2. preferred distinct issuers >= **100**;
3. preferred group contains at least **20 M100 monsters**;
4. preferred review share <= **50%** of its comparable observed cohort;
5. pooled M100 lift >= **1.50×**;
6. pooled M100 capture >= **20%**;
7. M100 lift > **1.00×** in at least **2 of 3** discovery years;
8. M100 lift outside the bottom dollar-ADV quintile >= **1.25×**;
9. M200 lift > **1.00×** when the comparable discovery cohort contains at
   least 10 M200 events; otherwise M200 is descriptive and non-blocking;
10. no single issuer supplies more than **15%** of preferred-group M100 hits.

If multiple variants in one family pass, choose by this frozen tuple:

1. highest M100 capture efficiency;
2. highest M100 lift;
3. highest M200 lift when evaluable;
4. highest M100 capture;
5. lowest review share;
6. stable variant ID alphabetical.

At most one variant per family advances.

## Confirmation — 2019-2020

Apply the exact discovery-selected variant, direction and cutpoints unchanged.

All are required:

1. preferred evaluable N >= **150**;
2. preferred distinct issuers >= **75**;
3. preferred group contains at least **10 M100 monsters**;
4. pooled M100 lift >= **1.25×**;
5. pooled M100 capture >= **15%**;
6. 2019 M100 lift > **1.00×**;
7. 2020 M100 lift > **1.00×**;
8. M100 lift outside bottom dollar-ADV quintile > **1.00×**;
9. no single issuer supplies more than **20%** of preferred-group M100 hits.

M200/M500 remain important secondary tail diagnostics but do not veto a valid
M100 confirmation when event counts are too small.

There is no alternate threshold, direction, bucket or replacement variant
inside a family after confirmation opens.

## What counts as success

A successful v1 feature is **not** claimed to predict positive average returns.

It means only:

> the feature materially concentrates the incidence of future +100% 252-session
> opportunities while retaining a useful share of those opportunities and
> reducing the review universe.

This is intended as an upstream screener for later human/technical/fundamental
selection and risk management.

## Multiplicity / anti-overfit boundary

- fixed feature list above;
- fixed monster thresholds;
- fixed 252-session primary opportunity window;
- one family winner maximum;
- chronological discovery/confirmation;
- no composite weights;
- no optimization against 2021-2022;
- no technical/fundamental overlay in v1;
- no 2023+ read.

## Current progression boundary

After this gate is committed:

1. build a performance-blind MFE/path-coverage feasibility audit;
2. prove continuity/path semantics can support the labels without silent
   substitution;
3. freeze the exact outcome contract;
4. only then compute 2016-2018 monster outcomes;
5. run unchanged 2019-2020 confirmation;
6. optionally report 2021-2022 later as
   `KNOWN_SAMPLE_RETROSPECTIVE_DIAGNOSTIC`;
7. keep 2023+ sealed until an explicit later authorization.

Production scoring remains unchanged.
