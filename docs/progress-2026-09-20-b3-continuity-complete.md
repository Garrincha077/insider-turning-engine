# Phase-1 B3 continuity resolution complete — 2026-09-20

## Final status

The performance-blind B3 security-continuity program is complete for the
original frozen 264 unresolved event-horizon rows.

Final residual-13 resolution:

- workflow run: **35540472056** — SUCCESS
- release: `research-phase1-b3-final-residual13-resolution-v1`
- asset: `b3-final-residual13-resolution.json`
- asset SHA-256:
  `sha256:6ac4dc4adee77e32747ad4e536fec3036c99c23bb664f3ccf5be2b4ab5b4981e`
- resolved rows: **13 / 13**
- unresolved after gate: **0**

Final 264-row continuity contract:

- workflow run: **35540610883** — SUCCESS
- release: `research-phase1-b3-final-continuity-contract-v1`
- asset: `b3-final-continuity-contract.json`
- asset SHA-256:
  `sha256:22e1af6713eb0c0f73604a150787ac9248f044eef63e1f88b70b31697aede163`
- source unresolved rows: **264**
- classified rows: **264**
- unresolved rows: **0**
- final classified key SHA-256:
  `sha256:6125fe42a9559ce937d385b4f49d1a74d33ce1caad7f5ec8487ce72bf854082b`
- final key digest equals the frozen upstream scope digest: **yes**
- final resolution contract created: **true**
- corrected performance opened: **false**

## Final classification counts

- `SAME_SECURITY_CONTINUITY`: **180**
- `SYMBOL_CHANGED_SAME_SECURITY`: **11**
- `TRANSFORMED_HOLDER_CONSIDERATION`: **71**
- `TRANSFORMED_MULTI_COMPONENT_CONSIDERATION`: **1**
- `DISCONTINUOUS_NO_COMPLETE_VALUATION`: **1**

Total: **264**.

The single multi-component row preserves the NBA.U holder basket rather than
discarding the public-warrant component.

## Exact source coverage

The contract is the union of:

- 173 deterministic classifications from the frozen multisource stage;
- 4 provider-primary resolutions;
- 4 first-wave SPAC-unit resolutions;
- 20 one-sided primary resolutions;
- 8 second-wave SPAC-unit resolutions;
- 12 multi-class/reorganization resolutions;
- 19 ordinary common-security resolutions;
- 11 surviving-unit resolutions;
- 13 final residual resolutions.

The eight later resolution releases contain exactly **91** unique keys, and
that key set equals the frozen residual-91 set from the multisource stage.
The 173 base and 91 later keys are disjoint and reproduce the exact original
264-row scope.

## Guardrails preserved

Across the complete resolution program:

- `researchOnly=true`
- `performanceRead=false`
- `priceFieldsRead=[]`
- `oosOpened=false`
- `productionScoringChanged=false`
- development cohort remains 2016-2020
- evidence/outcomes remain bounded through 2022-12-31
- 2023+ OOS remains sealed
- production scoring/weights/thresholds were not changed

## Next gate

Corrected B3 development performance may now be implemented only under a new
predeclared gate.

That next gate must:

1. consume the immutable final continuity contract above;
2. preserve the already frozen 21/63/126/252 XNYS target dates and 126-session
   primary horizon;
3. preserve exact-session missing-data behavior and never substitute a later
   market bar;
4. apply holder transformations only from the final contract;
5. value multi-component consideration only when every required component has
   an exact target-session value, otherwise fail closed / mark incomplete;
6. preserve the frozen nominal convention for cash consideration;
7. leave 2023+ OOS sealed;
8. after corrected development results, reapply the already frozen B3
   robustness semantics without retuning.

The existing uncorrected robustness result remains
`BLOCK_HAC_AND_OOS` until and unless the separately recomputed corrected
development/robustness gates establish otherwise under those frozen rules.
