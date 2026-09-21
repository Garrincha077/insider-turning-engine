# Phase-1 F2 validation residual-32 continuity scope gate

Frozen: 2026-09-21 after immutable HSDT primary resolution and before any
validation outcome is read.

## Inputs

Residual-33 scope:
- release: `research-phase1-insider-feature-tournament-validation-residual33-scope-v1`;
- asset: `validation-residual33-scope.json`;
- SHA-256:
  `sha256:0dab36d7553ec3ceb0838c79cf7ad70a85fa240686d7493930de160c55adb946`;
- scope-key SHA-256:
  `sha256:9ee5091b18344e67b58fe567b92ce99d3f923e4df2829af935158947bdcae2a2`.

HSDT primary resolution:
- release:
  `research-phase1-insider-feature-tournament-validation-hsdt-primary-resolution-v1`;
- asset: `validation-hsdt-primary-resolution.json`;
- SHA-256:
  `sha256:b5348aa135082da6a2d07510125ffde4b67b4f327a522597301782d3b2e37a03`;
- resolved semantic-key SHA-256:
  `sha256:2dec9e57b3e6927b9c387764e2bcbfe0955cb450e9a546dfb900bcd9c8e92827`.

## Frozen subtraction rule

Subtract exactly the one HSDT semantic key from the immutable residual-33
scope. No other row or field may be changed.

Expected result:
- residual rows: **32**;
- scope-key SHA-256:
  `sha256:4b8d0df8ff1d06f018fdcbdf281b9fa2be05f21e77b57682012b36b419049e34`;
- `PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED`: **22**;
- `LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED`: **10**;
- prior-security long-gap candidates: **0**.

## Frozen next-wave partition

The 22 provider rows are partitioned by their already-frozen provider audit
shape, without looking at performance:

1. **Stock-dividend wave — 5 rows**
   - FGBI;
   - LARK;
   - ATAX;
   - AROW;
   - HWBK.

2. **Incomplete stock-merger terms wave — 8 rows**
   - SPRT ×2;
   - APO ×2;
   - TSE;
   - DKNG ×2;
   - AEI.

3. **Name-change + stock-merger/reorganization wave — 8 rows**
   - TBA;
   - SAII ×2;
   - LEGO ×2;
   - DDMX;
   - VOSO;
   - SV.

4. **Standalone name-change wave — 1 row**
   - CBTX.

The 10 long-gap rows remain a separate primary-evidence wave:
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

These partitions are routing aids only. They do not predetermine security
continuity or holder consideration.

## Boundary

- researchOnly=true;
- performanceRead=false;
- priceFieldsRead=[];
- featureOutcomesRead=false;
- validationOpened=false;
- validationPerformanceOpened=false;
- oosOpened=false;
- productionScoringChanged=false.

Validation performance remains blocked until the residual reaches zero.
