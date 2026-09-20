# Phase-1 B3 development-performance gate

Status: **PREDECLARED / PENDING FINAL IDENTITY ARTIFACT PIN**  
Date: **2026-09-20**  
Purpose: define the first B3 development performance run before any B3 forward
returns are read.  
Development cohort: **2016–2020 evaluation sessions**.  
Outcome evidence: **2016–2022 only**.  
Validation cohort performance: **not opened by this gate**.  
2023+ OOS: **sealed**.  
Production scoring: unchanged.

Definition file:
`research/b3-development-performance-v1.json`.

## Prerequisite

The B3 PIT identity-attachment gate must pass first.

Its final release asset SHA-256 must be pinned into the definition file before
the performance workflow is allowed to execute. Pinning the completed input
artifact is not a methodology change.

## Frozen market source

Use only the existing bounded release:

`research-market-alpaca-v1`

for 2016 through 2022.

All seven annual archive digests are frozen in the JSON definition.

No 2023 market archive may be downloaded or present.

## Coverage gate before returns

Before calculating a single B3 forward return:

1. verify the frozen identity event count and identity summary;
2. verify exact frozen `evaluationSession` and `entrySession`;
3. require a regular stock bar on the exact entry session;
4. require the corresponding regular SPY entry bar;
5. compute event-specific exact-entry coverage by year;
6. combine the frozen identity attrition metrics with exact-entry and SPY
   coverage;
7. apply the already frozen P0 A/B/C thresholds.

Minimum allowed tier for the first descriptive B3 performance run:
**C_EXPLORATORY**.

If B3-specific data quality is below Tier C, the workflow must stop before
forward returns are calculated.

Thresholds must not be lowered after seeing B3 coverage or performance.

## Development outcome calculation

For events that pass exact entry:

- entry price: stock exact next-XNYS-session open already frozen by event
  construction;
- benchmark entry: SPY open on the same session;
- horizons: **21, 63, 126, 252 XNYS sessions**;
- primary horizon: **126**;
- exit: exact XNYS target session close;
- SPY benchmark exit: same exact session close;
- no nearest/later stock-bar substitution;
- no missing-return imputation.

Report for every horizon:

- matured count;
- distinct issuers;
- raw mean and median;
- SPY-excess mean and median;
- excess win rate;
- excess p05 and p10;
- MAE count/mean/median when the exact path is complete;
- explicit exit/terminal/delisting attrition.

## Study-boundary censoring

A horizon is `STUDY_BOUNDARY_RIGHT_CENSORED` only when its required XNYS
target lies after **2022-12-31**.

A missing stock bar on an in-bound target session is not study-boundary
censoring.

## Security continuity

The first B3 development result is a **canonical descriptive** run on the
frozen adjusted market archives.

Any symbol/security continuity correction is a separate research gate. It must
be specified and resolved without choosing rules from B3 realized returns.

Missing/discontinuous outcomes remain explicit in the first run.

## Interpretation

The first result may be described only as:

`research/descriptive`.

It is not a formal alpha PASS even if arithmetic mean excess is positive.

Dependence-aware calendar-time/HAC, issuer clustering, tail sensitivity,
year-stability and continuity work remain required before stronger inference.

## Locked boundaries

- no validation-event performance;
- no 2023+ data;
- no production scoring changes;
- no feature-threshold tuning from B3 outcomes;
- no silent identity repair;
- no lowering of P0 data-quality thresholds.
