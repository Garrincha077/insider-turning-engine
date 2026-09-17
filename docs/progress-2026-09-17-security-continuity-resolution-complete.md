# Phase-1 B1 security continuity resolution complete — 2026-09-17

## Status

The performance-blind security-continuity resolution gate is complete for the frozen Phase-1 B1 development cohort.

- Branch: `research/security-continuity-resolution`
- Authoritative handoff checkpoint: `8c6046293b7b631d3d3355f9e8654d25b10362ea`
- Green resolution implementation commit: `6402291e1a16b644e4e310bb1d16268fefee8290`
- Resolution workflow run: `35275669277`
- Resolution artifact: `phase1-security-continuity-resolution-35275669277`
- Resolution artifact digest: `sha256:f5d1dbbb2978bf495d439dfaa0981f4f0d987260e85e96f266866647b0d65f8c`
- Frozen resolution contract: `research/b1-security-continuity-resolution-v1.json`
- Frozen resolution contract SHA-256: `sha256:88325d71dd9da1f18bdc2c2695933860e087addd586def8b4271ed768d121430`

## Frozen upstream evidence

- Source continuity workflow run: `35272112415`
- Source artifact: `phase1-security-continuity-ledger-35272112415`
- Source artifact digest: `sha256:7e67aa271d60f8f3837e3db76f3a8a0e20312fdea5baf7f031e387d25349c4b8`
- Source continuity-ledger CSV SHA-256: `sha256:06de0c4cd7a827d9886c962dba3a220bde1a7030773f61c73e408a49e8880cd0`
- Frozen gap diagnostic run: `35272945732`
- Gap diagnostic artifact: `phase1-security-gap-diagnostics-35272945732`
- Gap diagnostic artifact digest: `sha256:f203552b0b52e51ec91338827ea8d87b2989fe5bbe462a4e36b3862f36ccee08`
- Frozen unresolved-row key digest: `sha256:2f82b7354f8a9262064b215dcfd060a1432ed46cd9273f4d1da097d5aa91198c`

## Green gate result

The workflow independently verified the frozen upstream artifact digests, downloaded only the authoritative continuity ledger, applied the frozen overlay, verified the source ledger remained byte-identical, and passed all regression guards.

- Source event-horizon rows: `24,376`
- Source `UNRESOLVED_CONTINUITY`: `54`
- Resolution contract rows: `54`
- Rows resolved by frozen contract: `54`
- Same-security continuity rows: `33`
- Holder-transformation rows: `21`
- Final `UNRESOLVED_CONTINUITY`: `0`
- `performanceStageBlocked=false`

Final continuity-state counts:

- `PRICE_CONTINUOUS_ADJUSTED`: `24,232`
- `SYMBOL_CHANGED_SAME_SECURITY`: `66`
- `TRANSFORMED_HOLDER_CONSIDERATION`: `75`
- `DISCONTINUOUS_NO_COMPLETE_VALUATION`: `3`

## Guardrails preserved

- Development cohort remains `2016–2020`.
- Outcomes remain bounded through `2022-12-31`.
- `2023+` remains sealed.
- Horizons remain `21/63/126/252` XNYS sessions; primary horizon remains `126`.
- Long-gap threshold remains `10` XNYS sessions.
- `researchOnly=true`.
- `oosOpened=false`.
- `productionScoringChanged=false`.
- `performanceRead=false`.
- `performanceFieldsRead=[]`.
- `priceFieldsRead=[]`.
- `sourceLedgerUntouched=true`.
- `frozenScopeExpanded=false`.
- No B1/B2/B4 definition was changed.
- No resolution rule was selected or altered using realized performance.

## Implemented files

- `research/b1-security-continuity-resolution-v1.json`
- `scripts/research_phase1_security_continuity_resolution.py`
- `tests/test_research_phase1_security_continuity_resolution.py`
- `.github/workflows/research-phase1-security-continuity-resolution.yml`

Regression coverage includes strict effective-date semantics, a 2023+ hard fail, rejection of performance/OHLC fields before row use, fail-closed handling of unmatched unresolved rows, and prohibition of automatic frozen-scope expansion.

## Next gate

Corrected performance may now be implemented only as a separate research workflow consuming this zero-unresolved continuity result. It must keep the `126`-session primary horizon, preserve `21/63/126/252`, compare B0/B1/B2/B4, keep `2023+` sealed, and label outputs research/descriptive rather than formal alpha. P0 remains exploratory until dependence-aware/calendar-time/HAC robustness is implemented.
