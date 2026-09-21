# Phase-1 F2 validation HSDT primary continuity resolution gate

Frozen: 2026-09-21 after the immutable HSDT gap-interval diagnostic and primary
SEC evidence review, before applying the resolution and before any validation
outcome is read.

## Frozen source

Gap diagnostic release:
`research-phase1-insider-feature-tournament-validation-hsdt-gap-interval-v1`.

Asset:
`validation-hsdt-gap-interval.json`.

SHA-256:
`sha256:ba5f63caad37bf476bbafff156182118b37d965d5a1406c93b7e45b5985707a2`.

Exact validation row:
- eventNumber: 3657;
- issuer CIK: 0001610853;
- ticker: HSDT;
- evaluationSession: 2021-11-15;
- entrySession: 2021-11-16;
- horizon: 126 XNYS sessions;
- targetExitSession: 2022-05-18.

Single-row semantic-key SHA-256:
`sha256:2dec9e57b3e6927b9c387764e2bcbfe0955cb450e9a546dfb900bcd9c8e92827`.

Exact market-presence gap:
- previous observed session: 2022-02-03;
- first missing session: 2022-02-04;
- last missing session: 2022-03-17;
- next observed session: 2022-03-18;
- missing XNYS sessions: 29.

The frozen validation continuity audit reports no candidate provider corporate
action IDs or action types for this row.

## Frozen primary SEC evidence

All evidence refers to the same issuer CIK 0001610853, Helius Medical
Technologies, Inc.

1. 2022-01-26 Form 8-K, accession 0001564590-22-002491:
   Section 12(b) cover page lists Common Stock, ticker HSDT, The Nasdaq Stock
   Market LLC. This filing predates the observed gap.
2. 2022-02-16 Form 8-K, accession 0001564590-22-005702:
   Section 12(b) cover page again lists Common Stock, HSDT, Nasdaq. The filing
   also defines the company's Class A Common Stock as the “Common Stock” in the
   equity-plan disclosure. This filing is inside the gap.
3. 2022-03-08 Form 8-K, accession 0001564590-22-009857:
   Section 12(b) cover page lists Class A Common Stock, $0.001, ticker HSDT,
   Nasdaq. This filing is inside the gap.
4. 2022-03-14 Form 8-K, accession 0001564590-22-010081:
   Section 12(b) cover page lists Common Stock, ticker HSDT, Nasdaq. This
   filing is inside the gap.
5. 2022-04-01 Form 8-K, accession 0001564590-22-013230:
   Section 12(b) cover page again lists Common Stock, ticker HSDT, Nasdaq,
   after market-presence observations resume.

The official URLs are pinned in
`research/validation-hsdt-primary-evidence-v1.json`.

## Frozen interpretation rule

The evidence establishes the same issuer and same registered HSDT common/Class
A common security across and around the exact market-data gap. The variation
between “Common Stock” and “Class A Common Stock” is treated as title
normalization, supported directly by the 2022-02-16 filing's definition of
Class A Common Stock as “Common Stock”.

No holder transformation, symbol change, merger consideration, redemption or
other corporate-action term is present in the frozen validation provider
inventory for the row.

Therefore the frozen resolution is:

- resolutionDecision: `SAME_SECURITY_CONTINUITY`;
- transformationKind: empty;
- resultState: `PRICE_CONTINUOUS_ADJUSTED`;
- successorSymbol: `HSDT`;
- successorSharesPerEntryShare: `1`;
- cashPerEntryShare: `0`;
- sourceActionIds: empty;
- effectiveDate: `2022-03-18` (first observed regular session after the
  exact 29-session gap);
- evidenceClass:
  `SEC_PRIMARY_EXACT_GAP_BRACKETING_SAME_SECURITY`;
- classificationSource:
  `VALIDATION_HSDT_PRIMARY_GAP_BRACKETING`.

This resolution classifies security continuity only. It does not create or
substitute any missing market price. Exact-session outcome rules remain
unchanged downstream.

## Boundary

- researchOnly=true;
- performanceRead=false;
- priceFieldsRead=[];
- featureOutcomesRead=false;
- validationOpened=false;
- validationPerformanceOpened=false;
- oosOpened=false;
- productionScoringChanged=false.

After this one-row resolution, expected validation continuity residual = 32.
