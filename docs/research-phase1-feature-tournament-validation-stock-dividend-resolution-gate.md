# Phase-1 F2 validation stock-dividend primary resolution gate

Frozen: 2026-09-21 after residual-32 freeze and primary SEC review, before
applying any stock-dividend resolution and before validation outcomes are read.

## Source scope

Release:
`research-phase1-insider-feature-tournament-validation-residual32-scope-v1`.

Asset:
`validation-residual32-scope.json`.

SHA-256:
`sha256:17129c2aded50c6e97d55e4af5ea9c469cb33ec5ff9171731f8b309d6f0ae06a`.

Scope-key SHA-256:
`sha256:4b8d0df8ff1d06f018fdcbdf281b9fa2be05f21e77b57682012b36b419049e34`.

## Frozen provider inventory

The validation corporate-action inventory is the exact
`corporate-actions.json` included in
`research-phase1-insider-feature-tournament-validation-continuity-audit-v1`.

SHA-256:
`sha256:c45e1c5ea5263d2384527359a544f3b81e49fa9f5b64fc9ff792153ad1fb0457`.

The five target rows have exactly one `stock_dividends` provider action each.

Five-row semantic-key SHA-256:
`sha256:7dd0615edd13ae996379d9c49194a45edbeda6e5bcf418e1b47c948540a562a3`.

## Frozen terms and primary evidence

1. FGBI, event 2006
   - action ID: c6d028ca-0983-49a9-aa61-6e21cc586c40;
   - provider ex/action date: 2021-12-14;
   - provider quantity factor: 1.10;
   - SEC Form 8-K accession 0001408534-21-000065 states a 10% common stock
     dividend, record date 2021-12-15 and payable date 2021-12-17.

2. LARK, event 2273
   - action ID: 170e227a-52f7-4979-bc2c-edc87d4188b0;
   - provider ex/action date: 2021-11-30;
   - provider quantity factor: 1.05;
   - SEC Form 8-K accession 0001493152-21-026542 states a 5% stock dividend,
     record date 2021-12-01 and issue date 2021-12-15.

3. HWBK, event 7090
   - action ID: 1f2e1e66-1497-4dc0-ad10-dee5ab8c8dcc;
   - provider ex/action date: 2022-06-14;
   - provider quantity factor: 1.04;
   - SEC Form 8-K accession 0000893847-22-000014 states a special 4% stock
     dividend, record date 2022-06-15 and payable date 2022-07-01.

4. AROW, event 6300
   - action ID: 72776cb8-c85b-44d1-a4ab-be701549e075;
   - provider ex/action date: 2022-09-16;
   - provider quantity factor: 1.03;
   - SEC Form 8-K accession 0000717538-22-000190 states a 3% stock dividend,
     record date 2022-09-19 and distribution date 2022-09-23.

5. ATAX, event 6077
   - action ID: 855589cc-79ed-4e87-83eb-70812286ff2c;
   - provider ex/action date: 2022-09-29;
   - provider quantity factor: 1.01044;
   - SEC Form 8-K accession 0000950170-22-018459 states a supplemental BUC
     distribution of 0.01044 BUCs per outstanding BUC, record date 2022-09-30,
     payment date 2022-10-31, and explicitly says the BUCs trade
     ex-distribution on 2022-09-29.

Official URLs and complete frozen provider fields are pinned in
`research/validation-stock-dividend-primary-evidence-v1.json`.

## Frozen resolution semantics

For each target row:

- resolutionDecision: `TRANSFORMED_HOLDER_CONSIDERATION`;
- transformationKind: `STOCK_DIVIDEND_QUANTITY`;
- resultState: `TRANSFORMED_HOLDER_CONSIDERATION`;
- successorSymbol: unchanged historical ticker;
- successorSharesPerEntryShare: frozen provider rate;
- cashPerEntryShare: 0;
- sourceActionIds: exactly the one frozen provider action ID;
- effectiveDate: frozen provider ex/action date;
- evidenceClass: `PRIMARY_SEC_STOCK_DIVIDEND_TERMS_MATCH_PROVIDER`;
- classificationSource:
  `VALIDATION_PRIMARY_STOCK_DIVIDEND_TERMS`.

The provider quantity factor already represents original share plus stock
dividend (for example 10% = 1.10). It must not be incremented again.

ATAX is classified using its explicit ex-distribution date, not its later
payment date, because the frozen target session 2022-10-25 falls after
ex-distribution but before payment.

No cash distribution is added to the continuity overlay. Ordinary cash
distributions/dividends remain governed by the frozen adjusted-market return
semantics and are not duplicated in holder consideration.

## Expected residual

Exactly 5 rows are resolved. Expected unresolved validation continuity rows
after this wave: **27**.

## Boundary

- researchOnly=true;
- performanceRead=false;
- priceFieldsRead=[];
- featureOutcomesRead=false;
- validationOpened=false;
- validationPerformanceOpened=false;
- oosOpened=false;
- productionScoringChanged=false.

Validation performance remains blocked until continuity unresolved = 0.
