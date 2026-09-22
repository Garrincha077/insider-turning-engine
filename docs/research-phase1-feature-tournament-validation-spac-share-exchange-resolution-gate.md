# Phase-1 F2 validation SPAC share-exchange primary resolution gate

Frozen: 2026-09-22 after immutable residual-19 scope and before any validation
outcome is read.

## Source scope

Release:
`research-phase1-insider-feature-tournament-validation-residual19-scope-v1`.

Asset:
`validation-residual19-scope.json`.

SHA-256:
`sha256:2b2ebcf18d1ab74594141cbbaec00f911f4db4c01e529d34f000a8b24ddfcf67`.

This gate resolves exactly the **8** rows whose frozen provider action-type set
is `["name_changes", "stock_mergers"]`.

Eight-row semantic-key SHA-256:
`sha256:f08070c07a6bb411490e8f97b6413c5b498496d4f178067ceab5059db4d159c0`.

Frozen identities:

- TBA -> IS — 1 row;
- SAII -> OTMO — 2 rows;
- LEGO -> ASTL — 2 rows;
- DDMX -> CDRO — 1 row;
- VOSO -> WEJO — 1 row;
- SV -> SMR — 1 row.

## Frozen primary SEC holder terms

Every target is a one-for-one public SPAC/common-share exchange into the
successor public common security. No cash consideration is added.

### TBA -> IS

Closing date: **2021-06-28**.

Primary evidence:
- ironSource/TBA closing Form 8-K, accession
  `0001193125-21-202203`.

Each outstanding TBA Class A share was converted automatically into one
ironSource Class A ordinary share. ironSource began trading as IS on
2021-06-29.

### SAII -> OTMO

Closing date: **2021-08-13**.

Primary evidence:
- Software Acquisition Group II/Otonomo closing Form 8-K, accession
  `0001193125-21-246267`.

Each outstanding SAII Class A share was exchanged for one Otonomo ordinary
share. OTMO began trading after closing.

### LEGO -> ASTL

Closing date: **2021-10-19**.

Primary evidence:
- Legato/Algoma closing Form 8-K, accession
  `0001213900-21-053600`.

Each outstanding Legato common share was exchanged for one Algoma common
share. ASTL began trading on 2021-10-20.

### DDMX -> CDRO

Closing date: **2021-11-30**.

Primary evidence:
- DD3/Codere Online closing Form 8-K, accession
  `0001829126-21-015613`;
- Codere Online 2021 Form 20-F, accession
  `0001829126-22-009210`.

The merger issuance was one Codere Online ordinary share for each outstanding
DD3 Class A share. CDRO began trading on 2021-12-01.

### VOSO -> WEJO

Closing date: **2021-11-18**.

Primary evidence:
- Wejo/Virtuoso registration statement, accession
  `0001104659-21-093068`;
- Wejo closing Form 8-K, accession
  `0001104659-21-143665`.

Each outstanding Virtuoso Class A or Class B common share was converted into
one Wejo Group common share. WEJO began trading on 2021-11-19.

### SV -> SMR

Public-share conversion date: **2022-04-29**.

Business-combination closing date: **2022-05-02**.

Primary evidence:
- Spring Valley/NuScale closing Form 8-K, accession
  `0001104659-22-056493`.

At the domestication each outstanding Spring Valley Class A ordinary share
converted one-for-one into NuScale Power Corporation Class A common stock.
Spring Valley securities ceased trading on 2022-05-02 and SMR began trading on
2022-05-03.

## Frozen resolution semantics

All eight rows:

- resolutionDecision: `TRANSFORMED_HOLDER_CONSIDERATION`;
- transformationKind: `PRIMARY_SEC_SPAC_STOCK_EXCHANGE`;
- resultState: `TRANSFORMED_HOLDER_CONSIDERATION`;
- successorSharesPerEntryShare: `1`;
- cashPerEntryShare: `0`;
- basket: empty;
- sourceActionIds: exactly the frozen two-action ID set for the row;
- evidenceClass: `PRIMARY_SEC_SPAC_COMMON_SHARE_EXCHANGE_1_TO_1`;
- classificationSource:
  `VALIDATION_PRIMARY_SPAC_SHARE_EXCHANGE_TERMS`.

## Expected residual

Exactly 8 rows are resolved.

Expected unresolved continuity after this wave: **11** rows:
- 1 standalone name-change provider row: CBTX;
- 10 long-gap rows.

Expected 11-row residual semantic-key SHA-256:
`sha256:46381d68c3ad51f9d6d9d7a934d88d807c599f78712f34d4e210c9f4248e5d55`.

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
