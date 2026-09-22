# Phase-1 F2 validation residual-11 continuity scope gate

Frozen: 2026-09-22 after immutable SPAC share-exchange primary resolution and
before any validation outcome is read.

## Inputs

Residual-19 scope:
- release: `research-phase1-insider-feature-tournament-validation-residual19-scope-v1`;
- asset: `validation-residual19-scope.json`;
- SHA-256: `sha256:2b2ebcf18d1ab74594141cbbaec00f911f4db4c01e529d34f000a8b24ddfcf67`;
- scope key: `sha256:612f62f79717037ecb858998a03cf5fb6d6ce927f308fd08f535af5eeb99945d`.

SPAC share-exchange resolution:
- release: `research-phase1-insider-feature-tournament-validation-spac-share-exchange-resolution-v1`;
- asset: `validation-spac-share-exchange-primary-resolution.json`;
- SHA-256: `sha256:ebc41a7a0e65c6bcb696330f6e6121deff55e954bcafde6fe4fe83ea59ca4581`;
- resolved rows: **8**;
- resolved key SHA-256: `sha256:f08070c07a6bb411490e8f97b6413c5b498496d4f178067ceab5059db4d159c0`.

## Frozen subtraction

Subtract exactly those eight semantic keys from residual-19.

Expected residual:
- rows: **11**;
- semantic-key SHA-256:
  `sha256:46381d68c3ad51f9d6d9d7a934d88d807c599f78712f34d4e210c9f4248e5d55`;
- provider new-primary: **1**;
- long-gap new-primary: **10**.

The only provider row is CBTX, event 7087, standalone `name_changes`.
The ten long-gap rows are ROCGU, APMIU, GRCY, MCAGU, NETC.U, KACLU, UPTD,
JAGX, ACON and NVVE.

## Boundary

performanceRead=false; priceFieldsRead=[]; featureOutcomesRead=false;
validationOpened=false; validationPerformanceOpened=false; oosOpened=false;
productionScoringChanged=false.

Validation performance remains blocked until unresolved continuity = 0.
