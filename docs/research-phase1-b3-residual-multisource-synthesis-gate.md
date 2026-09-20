# Phase-1 B3 residual multi-source continuity synthesis gate

Frozen: 2026-09-20, after the bounded P/S PIT, accession-pinned security-title,
successor-action, and all-Form345 corroboration runs, and before any corrected
B3 performance is opened.

## Purpose

This gate may promote only a narrow subset of the 162 residual B3
`UNRESOLVED_CONTINUITY` event-horizon rows to performance-blind resolution
candidates. It does not create the final continuity contract and it does not
open corrected performance, validation, HAC, or 2023+ OOS.

## Frozen upstream scope

- source unresolved rows: 264
- already deterministic candidate rows: 102
- residual rows entering this gate: 162
- development cohort: 2016-2020
- outcomes/evidence bounded through: 2022-12-31
- sealed OOS: 2023+
- horizons: 21/63/126/252 XNYS sessions
- primary horizon: 126
- long-gap threshold: 10 XNYS sessions
- production scoring unchanged

## Frozen promotion rule

A residual row may be promoted to `SAME_SECURITY_CONTINUITY` only when every
condition below is true:

1. the frozen source is `long_internal_gap`;
2. there is no provider identity-changing candidate action on the row;
3. bounded P/S PIT reports `EXPECTED_TICKER_BOTH_SIDES`;
4. both accession-pinned P/S observations have the row issuer CIK and exact row
   ticker;
5. the non-empty normalized SEC security-title sets on the two pinned
   accessions are exactly equal;
6. the title status is `TITLE_SET_EXACT_MATCH`;
7. bounded all-Form345 identity evidence independently reports
   `EXPECTED_TICKER_BOTH_SIDES`;
8. both nearest Form345 observations have the row issuer CIK and exact row
   ticker;
9. all row, pivot, and evidence dates remain before 2023.

A promoted row is only a new frozen candidate:

- evidence class: `SEC_MULTI_SOURCE_EXACT_CONTINUITY`
- resolution decision: `SAME_SECURITY_CONTINUITY`
- result state: `PRICE_CONTINUOUS_ADJUSTED`
- successor symbol: unchanged row ticker
- successor shares per entry share: 1.0
- cash per entry share: 0.0
- effective date: frozen continuity pivot date

## Fail-closed rules

The following do not qualify:

- one-sided evidence;
- title overlap without exact equality;
- changed security-title set;
- ticker change after the pivot;
- changed/different ticker evidence;
- provider ambiguity or identity-changing action;
- missing observations;
- any 2023+ evidence;
- any realized return, OHLC, MAE, excess-return, validation or OOS field.

Rows that do not satisfy the conjunction remain unresolved. No fallback or
same-ticker assumption is allowed.

## Stage boundaries

The expected count is frozen by the first green run, not hand-entered into the
methodology. This gate must report the count and digest of promoted and residual
keys while preserving:

- `researchOnly=true`
- `performanceRead=false`
- `priceFieldsRead=[]`
- `oosOpened=false`
- `productionScoringChanged=false`
- `finalResolutionContractCreated=false`
- `correctedPerformanceOpened=false`

Only a later separately frozen gate may combine all deterministic candidates
into a final continuity contract. Corrected B3 performance remains blocked
until the final unresolved count is zero.
