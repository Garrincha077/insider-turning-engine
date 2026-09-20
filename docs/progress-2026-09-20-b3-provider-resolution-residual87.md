# Phase-1 B3 provider primary resolution + residual-87 checkpoint — 2026-09-20

## Status

The four frozen provider-ambiguity rows are resolved from pinned primary SEC
evidence, and the next exact residual continuity scope is frozen at 87 rows.

### Residual-91 scope

- workflow run: `35507445541` — SUCCESS
- release: `research-phase1-b3-residual91-scope-v1`
- asset: `b3-residual91-scope.json`
- asset SHA-256:
  `sha256:f6ac0a711148af6229e7461b64c3034d3272646fbb7490219947f16b14267891`
- rows: **91**
- issuer/tickers: **35**
- key SHA-256:
  `sha256:46eeaa05a83960c1ef9537dd88972351b8c984c996ccddffa23f7da8d294ab58`

### Provider primary-source resolution

- first run 35507578248 stopped at lint before resolution;
- corrected green workflow run: **35507604004**
- release: `research-phase1-b3-provider-primary-resolution-v1`
- asset: `b3-provider-primary-resolution.json`
- asset SHA-256:
  `sha256:4f37195c3fda7a2db119f7391c8dbad4571d928aca80b78bc6e5630cdc48dfc1`
- resolved rows: **4 / 4 provider ambiguities**
- resolution-key SHA-256:
  `sha256:8db525671fcc4381ca8b5e906f132df28fe64f5d6c7d5000699b48730cfc5f2c`

Resolved security facts:

1. CIK 0001679688: CLNY -> DBRG, effective 2021-06-22
   - SEC 8-K accession 0001679688-21-000065
   - same Maryland corporation, corporate name change
   - Class A common stock symbol changed CLNY -> DBRG
   - official new Class A CUSIP 25401T108
   - provider reported a conflicting new CUSIP 25401T603; the primary SEC
     filing controls
2. CIK 0001717547: CLNC -> BRSP, effective 2021-06-25
   - SEC 8-K accession 0001717547-21-000024
   - same Maryland corporation formerly known as Colony Credit Real Estate
   - Class A common stock continues publicly traded on NYSE under BRSP
   - new CUSIP 10949T109

All four event-horizon rows are frozen as:

- `SYMBOL_CHANGED_SAME_SECURITY`
- 1.0 successor shares per entry share
- 0.0 cash per entry share
- no corrected performance opened

### Residual-87 scope

- workflow run: **35507696537** — SUCCESS
- release: `research-phase1-b3-residual87-scope-v1`
- asset: `b3-residual87-scope.json`
- asset SHA-256:
  `sha256:e1e2086f4e535721dd8697d810318164c6fe77f85de8c4409adc46afbe5f939f`
- rows: **87**
- issuer/tickers: **33**
- all remaining rows: `long_internal_gap`
- all remaining residual reasons: `NO_MATCHING_PRIOR_B1_EVIDENCE`
- residual key SHA-256:
  `sha256:c28829aa56204db04633546d91b06b938d06f897cd022d2c8147f488415d2742`

## Guardrails

Throughout these gates:

- `researchOnly=true`
- `performanceRead=false`
- `priceFieldsRead=[]`
- `oosOpened=false`
- `productionScoringChanged=false`
- final continuity contract remains not created
- corrected performance remains closed
- 2023+ remains sealed

## Next work

The remaining 87 rows should now be investigated only from the frozen residual
scope, starting with bounded primary security/corporate-action evidence for
ticker-change and one-sided identity buckets.

Do not infer continuity from same ticker alone. Do not use the existing
uncorrected return outcome to choose or relax a resolution rule.
