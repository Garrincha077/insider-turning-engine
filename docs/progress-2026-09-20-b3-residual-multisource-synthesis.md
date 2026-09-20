# Phase-1 B3 residual multi-source synthesis — 2026-09-20

## Status

The strict performance-blind residual synthesis gate is complete and green.

- Branch: `research/b3-ps-pit-history`
- Gate freeze commit: `8c92d7a9304eba575ace4b7fc22655ac6f657a9b`
- Runner commit: `fca8e6b0848a7d1f16fd2c8f4dd1d862d8fa4f26`
- Tests commit: `31dd4da489d47442d79179875c957ceecfdf85bf`
- First green workflow commit: `c11f62123fc671f8dca1f31c9949ca4d6da7b976`
- Workflow run: `35507255962` — SUCCESS
- Checkpoint-pin commit: `5d1d461953fdc10a68030cd09f641e15d9d588dd`
- Persistent release: `research-phase1-b3-residual-multisource-v1`
- Asset: `b3-residual-multisource-synthesis.json`
- Asset SHA-256: `sha256:b88512259b21b31b1defa63328cba4f2e56ba32f6fbf071452ff32251777f56a`

## Frozen input state

- frozen unresolved B3 rows: **264**
- deterministic candidates before this gate: **102**
- residual rows entering this gate: **162**
- 2023+ OOS remained sealed
- no corrected performance, price fields, validation, or OOS data were read

The 102 pre-existing deterministic candidates consisted of:

- 42 prior frozen B1 continuity-evidence matches
- 50 explicit stock-dividend terms
- 8 paired stock-and-cash merger terms
- 2 direct same-CUSIP provider cases

## Multi-source promotion result

The gate promoted a residual row only when all of the following agreed:

- source was a frozen long internal gap
- no provider identity-changing candidate action
- same issuer CIK and same expected ticker on both sides in bounded P/S PIT
- exact non-empty SEC security-title set on both pinned accessions
- same issuer CIK and same expected ticker on both sides in bounded all-Form345 evidence
- all evidence remained pre-2023

Result:

- new deterministic candidates: **71**
- combined deterministic candidates: **173 / 264**
- residual unresolved rows: **91**
- residual issuers/tickers: **35 / 35**

Frozen key digests:

- new 71 candidate keys: `sha256:e16d0d769af8d6151fe8cbb570db9ea78ec38f5682615531156e3b4bc79f5348`
- combined 173 candidate keys: `sha256:12101a4d11415b1c8a212024baf8cf4febdd05c23e26e70e38a28e1af00451c5`
- residual 91 keys: `sha256:46eeaa05a83960c1ef9537dd88972351b8c984c996ccddffa23f7da8d294ab58`

The workflow has now been pinned to these exact counts and digests.

## Residual 91 structure

- 87 rows are `long_internal_gap`
- 4 rows are provider ambiguity
- 20: P/S one-sided, Form345 same expected ticker on both sides
- 16: ticker changed and security-title set changed
- 15: same ticker both sides but title sets only overlap
- 10: same ticker both sides but title sets changed
- 8: ticker changed but exact title set
- 7: one-sided P/S and one-sided Form345
- 5: ticker changed with title overlap
- 3: ticker changed/title changed, Form345 same different ticker on both sides
- 3: expected ticker only after pivot with changed title
- 2: P/S same ticker/exact title but Form345 reports ticker change
- 1: different tickers across pivot with title overlap
- 1: P/S same ticker/exact title but Form345 expected ticker only after

## Guardrails preserved

- `researchOnly=true`
- `performanceRead=false`
- `priceFieldsRead=[]`
- `oosOpened=false`
- `productionScoringChanged=false`
- `finalResolutionContractCreated=false`
- `correctedPerformanceOpened=false`

The B3 definition, production configuration, frozen development cohort, horizons,
and OOS boundary were not changed.

## Next gate

Do **not** create the final B3 continuity contract yet. The remaining 91 rows
must be resolved or explicitly classified from performance-blind primary
security/corporate-action evidence.

Priority order:

1. freeze the exact 91-row residual scope and evidence-class buckets;
2. resolve the 4 provider ambiguities and ticker-change cases using pinned
   primary issuer/SEC/exchange evidence and exact holder/security terms;
3. investigate one-sided/title-change residuals without using realized returns;
4. only when the unresolved count reaches zero, create the final B3 continuity
   overlay;
5. only after a zero-unresolved continuity gate may corrected B3 performance be
   recomputed;
6. reapply the already frozen B3 robustness semantics. The current uncorrected
   robustness result remains `BLOCK_HAC_AND_OOS` because the 126-session
   top-1%-removed excess-return mean is non-positive.
