# Phase-1 B3 frozen residual-55 continuity scope gate

Frozen: 2026-09-20 after the residual-63 scope and the exact eight-row second
SPAC-unit primary-source resolution were independently frozen.

## Authoritative inputs

Residual-63 scope:

- release: `research-phase1-b3-residual63-scope-v1`
- asset: `b3-residual63-scope.json`
- asset SHA-256:
  `sha256:c217df79265aeb16bd9cf2abe78b9e4573311b52dfd377b5b706e63417f21f39`
- key SHA-256:
  `sha256:ed13976872da6522da2973a450a1f1c39e22cc19e2ffcc8367b9cc1a1b016b50`

Second SPAC-unit primary resolution:

- workflow run: `35508586692`
- release: `research-phase1-b3-spac-unit2-primary-resolution-v1`
- asset: `b3-spac-unit2-primary-resolution.json`
- asset SHA-256:
  `sha256:1a4e0b9fb67ce72a80d49b39ec827b3ad2ca8e5ce53ca36bcdf44470bf2ecb04`
- resolution-key SHA-256:
  `sha256:fae1020ef5d77cd93b885da6bc4e5c8b4a83ec1ded373f9ccc2148bf90add999`

## Frozen residual-55 result

Subtracting only those exact eight keys must produce:

- **55 rows**
- **23 issuer/ticker identities**
- residual-key SHA-256:
  `sha256:378820b3ab1a31441aa5b6a3e0faa54c51961e08aa5747d502a5638000e5a6dc`

The resolved MTECU/GRCYU/SBE.U/FSRVU rows must be absent.

## Guardrails

- development cohort remains 2016-2020
- evidence/outcome ceiling remains 2022-12-31
- 2023+ OOS remains sealed
- horizons remain 21/63/126/252, with 126 primary
- no prices, returns, MAE, tail membership, robustness output, validation or OOS
  data may be read
- production scoring remains unchanged
- corrected performance remains closed
- no automatic scope expansion

## Next evidence order

The remaining half of the ticker-change/title-change bucket contains genuine
issuer/security transformations and fund-class changes. It must be handled by
identity-specific primary evidence, not by the SPAC-unit rule.

Priority identities:

- GGO
- EAGL
- FMCIU
- TAGS

Then continue through the remaining changed/overlapping-title buckets.
