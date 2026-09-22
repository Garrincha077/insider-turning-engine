# Phase-1 F2 validation residual-19 continuity scope gate

Frozen: 2026-09-22 after immutable incomplete-stock-merger primary resolution
and before any validation outcome is read.

## Inputs

Residual-27 scope:
- release:
  `research-phase1-insider-feature-tournament-validation-residual27-scope-v1`;
- asset: `validation-residual27-scope.json`;
- SHA-256:
  `sha256:04b4e2280e9059aed8c10f9a6d9ac1853f23f34f5028dba6482c014c1ff190a4`;
- scope-key SHA-256:
  `sha256:683086e2a4ba61f734b45a22a24371f3f2a5ffa0f1fd74e7e9576275ab32da9f`.

Incomplete-stock-merger primary resolution:
- release:
  `research-phase1-insider-feature-tournament-validation-incomplete-stock-merger-resolution-v1`;
- asset:
  `validation-incomplete-stock-merger-primary-resolution.json`;
- SHA-256:
  `sha256:73722b4c87590a8a1fc0ad748534ce19a0d788281b965df1e475bc0dc789d584`;
- resolved rows: **8**;
- resolved semantic-key SHA-256:
  `sha256:31296aeae352b58fc55a6eba4cbfaf2fa0d600134a004afcf6c7980782a5b776`.

## Frozen subtraction rule

Subtract exactly those eight semantic keys from the immutable residual-27
scope. No other row or field may be changed.

Expected residual:
- rows: **19**;
- semantic-key SHA-256:
  `sha256:612f62f79717037ecb858998a03cf5fb6d6ce927f308fd08f535af5eeb99945d`;
- `PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED`: **9**;
- `LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED`: **10**.

Provider routing among the 9 rows:
- name-change + stock-merger/reorganization: **8 rows**
  - TBA;
  - SAII ×2;
  - LEGO ×2;
  - DDMX;
  - VOSO;
  - SV;
- standalone name-change: **1 row**
  - CBTX.

Long-gap rows remain exactly:
- ROCGU;
- APMIU;
- GRCY;
- MCAGU;
- NETC.U;
- KACLU;
- UPTD;
- JAGX;
- ACON;
- NVVE.

The routing labels do not predetermine continuity economics.

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
