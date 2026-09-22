# Phase-1 F2 validation residual-10 long-gap scope gate

Frozen: 2026-09-22 after immutable CBTX->STEL symbol-change resolution and
before any validation outcome is read.

## Inputs

Residual-11:
- release `research-phase1-insider-feature-tournament-validation-residual11-scope-v1`;
- asset `validation-residual11-scope.json`;
- SHA-256 `sha256:9f240f9c4fd4f565449ef5261d6a696bc70beb9725213f4a7c5f73d01781915d`;
- scope key `sha256:46381d68c3ad51f9d6d9d7a934d88d807c599f78712f34d4e210c9f4248e5d55`.

CBTX resolution:
- release `research-phase1-insider-feature-tournament-validation-cbtx-symbol-change-v1`;
- asset `validation-cbtx-symbol-change-resolution.json`;
- SHA-256 `sha256:bf074cb873959b5da66fdb98af015349a1ec09bf6e5192785bac1e23699cdf5f`;
- resolved key `sha256:a8705b17cd9f57eab966148e2ecaef12126e7010698ee812090b26151bed0e75`.

Subtract only that CBTX semantic key.

Expected residual:
- rows: **10**;
- scope-key SHA-256:
  `sha256:bba1bd1512a8ab6b8009e477689e189c2bd5ebf3033801f50753b023d5d6a426`;
- all category: `LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED`;
- tickers exactly:
  ROCGU, APMIU, GRCY, MCAGU, NETC.U, KACLU, UPTD, JAGX, ACON, NVVE.

No provider/action row remains.

## Boundary

researchOnly=true; performanceRead=false; priceFieldsRead=[];
featureOutcomesRead=false; validationOpened=false;
validationPerformanceOpened=false; oosOpened=false;
productionScoringChanged=false.

The next stage may inspect only market-presence dates and primary security
evidence for these exact ten rows. Validation performance remains blocked.
