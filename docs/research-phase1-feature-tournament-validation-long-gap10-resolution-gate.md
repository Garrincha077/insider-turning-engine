# Phase-1 F2 validation long-gap10 primary SEC resolution gate

Frozen: 2026-09-22 after the residual-10 long-gap scope was published and
before any validation performance or 2023+ OOS value is opened.

## Purpose

Resolve the final ten F2 validation continuity rows only from frozen exact-gap
metadata and primary SEC security evidence.

The source scope is:

- release:
  `research-phase1-insider-feature-tournament-validation-residual10-long-gap-scope-v1`;
- asset: `validation-residual10-long-gap-scope.json`;
- asset SHA-256:
  `sha256:a1db8f513116f57d30a4ab07c32ccbc66a6868c52cd58250f240703011832f22`;
- semantic-key SHA-256:
  `sha256:bba1bd1512a8ab6b8009e477689e189c2bd5ebf3033801f50753b023d5d6a426`;
- rows: **10**.

Exact gap metadata comes from:

- release:
  `research-phase1-insider-feature-tournament-validation-gap-diagnostics-v1`;
- asset: `gap-diagnostics.csv`;
- SHA-256:
  `sha256:1e7d783cee4bdd3a5c64fc42cb0cc7a8e1a41e14f36220809aa0ba5d80af75b7`.

## Frozen exact gaps

| Ticker | Previous observed | First missing | Last missing | Next observed | Sessions |
| --- | --- | --- | --- | --- | ---: |
| ROCGU | 2022-01-12 | 2022-01-13 | 2022-02-04 | 2022-02-07 | 16 |
| APMIU | 2021-11-29 | 2021-11-30 | 2021-12-14 | 2021-12-15 | 11 |
| GRCY | 2021-12-27 | 2021-12-28 | 2022-01-10 | 2022-01-11 | 10 |
| MCAGU | 2022-03-04 | 2022-03-07 | 2022-03-21 | 2022-03-22 | 11 |
| NETC.U | 2022-03-15 | 2022-03-16 | 2022-04-11 | 2022-04-12 | 19 |
| KACLU | 2022-03-16 | 2022-03-17 | 2022-04-05 | 2022-04-06 | 14 |
| UPTD | 2022-08-01 | 2022-08-02 | 2022-08-19 | 2022-08-22 | 14 |
| JAGX | 2022-04-04 | 2022-04-05 | 2022-06-08 | 2022-06-09 | 45 |
| ACON | 2022-05-19 | 2022-05-20 | 2022-06-14 | 2022-06-15 | 17 |
| NVVE | 2022-07-05 | 2022-07-06 | 2022-07-26 | 2022-07-27 | 15 |

## Primary-evidence rule

Repository evidence contract:

`research/validation-long-gap10-primary-evidence-v1.json`

Five rows are original SPAC-unit securities: ROCGU, APMIU, MCAGU, NETC.U and
KACLU. Separate trading of component common shares, warrants or rights does not
by itself transform an unseparated unit. The primary SEC record must preserve
the original unit ticker through the relevant gap/target period.

The remaining five rows are common/ordinary-share securities: GRCY, UPTD,
JAGX, ACON and NVVE. Primary SEC filings must preserve the same registrant,
security class and public ticker across the relevant gap, with no holder
exchange, cancellation, reverse split inside the frozen gap, or other
corporate-action transformation.

The frozen provider audit has zero action candidates for every row. That fact
is corroborative only; it is not a substitute for primary evidence.

## Authorized result

All ten rows are authorized only as:

- `SAME_SECURITY_CONTINUITY`;
- `PRICE_CONTINUOUS_ADJUSTED`;
- same successor ticker and issuer CIK;
- one successor security per entry security;
- zero cash;
- effective date equal to the exact next observed market session.

For SPAC units, the resolver must never silently map the unit to its separately
trading component common share.

## Progression boundary

A green primary-resolution workflow produces ten deterministic resolutions and
zero residual rows, but it does **not** yet open validation performance.

The next required stage is an immutable merged F2 validation continuity
contract reconciling every prior resolution source, proving unique
event-horizon keys and zero unresolved rows. Until that contract is green:

`performanceRead=false`, `priceFieldsRead=[]`,
`featureOutcomesRead=false`, `validationOpened=false`,
`validationPerformanceOpened=false`, `oosOpened=false`, and
`productionScoringChanged=false`.
