# Phase-1 B3 frozen residual-43 continuity scope gate

Frozen: 2026-09-20 after the residual-55 scope and the exact 12-row
multi-class/reorganization primary-source resolution were independently frozen.

## Authoritative inputs

Residual-55 scope:

- release: `research-phase1-b3-residual55-scope-v1`
- asset: `b3-residual55-scope.json`
- asset SHA-256:
  `sha256:6d767895389c63b2397cf39121b05370408070c31b37877416945da5c96e88b6`
- key SHA-256:
  `sha256:378820b3ab1a31441aa5b6a3e0faa54c51961e08aa5747d502a5638000e5a6dc`

Multi-class/reorganization resolution:

- workflow run: `35508859857`
- release: `research-phase1-b3-multiclass-reorg-primary-resolution-v1`
- asset: `b3-multiclass-reorg-primary-resolution.json`
- asset SHA-256:
  `sha256:a844ea830b9503a045b55a490c30b9e3cd77456974b741a696f16617caf75969`
- resolution-key SHA-256:
  `sha256:d9103eb5d9b5e04e18f955f4f6361ba39932ad285dff823a1046f72b613c2e91`

## Frozen residual-43 result

Subtracting only those exact 12 keys must produce:

- **43 rows**
- **19 issuer/ticker identities**
- residual-key SHA-256:
  `sha256:be82164c63ed8c8528017ff3201d5172e818655e5c7a8fa48bd7576c7cb02cd6`

GGO, TAGS, EAGL and FMCIU must be absent after subtraction.

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

## Next work

The residual-43 set is the only permitted continuity work queue. Before any
further classification, inspect its evidence-bucket and identity composition
and freeze each next primary-evidence rule before applying it.
