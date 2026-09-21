# Phase-1 F2 validation residual-27 continuity scope gate

Frozen: 2026-09-21 after immutable stock-dividend primary resolution and before
any validation outcome is read.

## Inputs

Residual-32 scope:
- release: `research-phase1-insider-feature-tournament-validation-residual32-scope-v1`;
- asset: `validation-residual32-scope.json`;
- SHA-256:
  `sha256:17129c2aded50c6e97d55e4af5ea9c469cb33ec5ff9171731f8b309d6f0ae06a`;
- scope-key SHA-256:
  `sha256:4b8d0df8ff1d06f018fdcbdf281b9fa2be05f21e77b57682012b36b419049e34`.

Stock-dividend primary resolution:
- release:
  `research-phase1-insider-feature-tournament-validation-stock-dividend-resolution-v1`;
- asset: `validation-stock-dividend-primary-resolution.json`;
- SHA-256:
  `sha256:fcac9796cb768fda95f0b2c1fdffc083379f3140500fca68c48a39bd5b007ba9`;
- resolved rows: 5;
- resolved semantic-key SHA-256:
  `sha256:7dd0615edd13ae996379d9c49194a45edbeda6e5bcf418e1b47c948540a562a3`.

## Frozen subtraction rule

Subtract exactly the five stock-dividend semantic keys from the immutable
residual-32 scope. No other row or field may be changed.

Expected residual:
- rows: **27**;
- semantic-key SHA-256:
  `sha256:683086e2a4ba61f734b45a22a24371f3f2a5ffa0f1fd74e7e9576275ab32da9f`;
- `PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED`: **17**;
- `LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED`: **10**.

Frozen provider routing waves among the 17 provider rows:
- incomplete stock-merger terms: **8 rows** (SPRT×2, APO×2, TSE, DKNG×2, AEI);
- name-change + stock-merger/reorganization: **8 rows** (TBA, SAII×2,
  LEGO×2, DDMX, VOSO, SV);
- standalone name-change: **1 row** (CBTX).

The 10 long-gap rows remain separate:
ROCGU, APMIU, GRCY, MCAGU, NETC.U, KACLU, UPTD, JAGX, ACON, NVVE.

These wave labels are routing aids only and do not predetermine continuity or
holder consideration.

## Boundary

- researchOnly=true;
- performanceRead=false;
- priceFieldsRead=[];
- featureOutcomesRead=false;
- validationOpened=false;
- validationPerformanceOpened=false;
- oosOpened=false;
- productionScoringChanged=false.

Validation performance remains blocked until unresolved continuity = 0.
