# Phase-1 B3 P/S PIT history gate

Status: **FROZEN BEFORE PILOT EXECUTION**  
Date: **2026-09-18**  
Scope: research-only preparation for B3 company net buying.  
Sealed OOS: **2023+ remains closed.**  
Production scoring: **unchanged.**

## Purpose

B3 requires a complete point-in-time history of both qualified open-market purchases and qualified open-market sales. The existing historical PIT release was intentionally selected from original filings with `buyCount > 0`. Although the canonical parser retains sale rows that coexist inside those filings, sale-only filings were not hydrated and therefore the existing release is not a complete buy/sell universe.

This gate freezes a separate **P/S PIT universe** before inspecting pilot results.

## Frozen transaction universe

A candidate original filing is eligible when all of the following hold:

- source year is 2013–2022 only;
- form is an original Form 4 or Form 5, not `/A`;
- the verified SEC bulk tables contain at least one priced positive-share non-derivative:
  - `P` with acquisition/disposition code `A`, or
  - `S` with acquisition/disposition code `D`;
- accession and issuer CIK pass the existing deterministic source checks.

The canonical XML parser remains unchanged. It already distinguishes `OPEN_MARKET_PURCHASE` and `OPEN_MARKET_SALE`.

No derivative sale, option exercise, tax withholding, gift, award, transfer, or other disposition is treated as a B3 open-market sale.

## PIT clock

For historical reconstruction:

- SEC `accepted_at` is the public-information clock;
- canonical `knowledgeAt == acceptedAt`;
- actual later research retrieval remains separate in `recordedAt` / provenance;
- later amendments may not repair an earlier state before their own acceptance time.

## Pilot before scale

The first execution is limited to **2016 Q1** and uses the already verified SEC bulk candidate source.

Pilot gates:

1. **100% candidate-accession discovery/hydration coverage**.
2. **Zero hydration/parser failures**.
3. **100% `knowledgeAt == acceptedAt`**.
4. **No 2023+ canonical or source evidence**.
5. **Unique transaction IDs, revision IDs and exact SEC row identities**.
6. Pilot must contain at least one **sale-only original filing**; otherwise it does not test the missing-history problem.
7. Bulk-to-canonical P/S concordance is reported by accession:
   - every bulk sale candidate is checked for at least one canonical qualified `S/D` row;
   - every bulk buy candidate is checked for at least one canonical qualified `P/A` row;
   - primary scale threshold: **>= 99.5% concordance** separately for sale candidates and buy candidates.
8. Any non-concordant accession remains explicit audit evidence; it is never silently dropped or reclassified.

A pilot below the concordance threshold blocks scale pending deterministic audit. The threshold must not be changed after pilot results are seen.

## Full-history completion gate

Passing the pilot does **not** make B3 usable.

Before `b3Eligible=true`, all of the following are required:

- original P/S PIT history complete for **40 quarters, 2013 Q1 through 2022 Q4**;
- persistent quarter evidence and deterministic checksums;
- all transaction-bearing Form 4/A and 5/A evidence reconciled against the broader P/S predecessor universe;
- unresolved/ambiguous amendment evidence explicitly quarantined;
- effective point-in-time P/S revisions available through end-2022;
- no 2023+ evidence opened;
- no production scoring changes.

The existing buy-only amendment-reconciliation result is not silently relabeled as complete for B3 because many amendment predecessors were outside the narrower original-buy universe.

## B3 definition remains unopened

This stage builds the prerequisite historical transaction universe only. It does **not** yet choose or test a company net-buying formula, window, threshold, buy/sell weighting, owner weighting, role weighting, or outcome performance.

Those B3 signal definitions must be frozen separately **after** the P/S history gate is complete and **before** B3 development results are computed.

## Required artifact flags

Every pilot/full-history summary must preserve:

- `researchOnly=true`
- `oosOpened=false`
- `productionScoringChanged=false`
- `canonicalReady=false`
- `signalReady=false`
- `b3Eligible=false` until the full-history + amendment gate is complete.
