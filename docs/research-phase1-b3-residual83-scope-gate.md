# Phase-1 B3 frozen residual-83 continuity scope gate

Frozen: 2026-09-20 after the residual-87 scope and the four-row SPAC-unit
primary-source resolution were frozen.

## Authoritative inputs

Residual-87 scope:

- release: `research-phase1-b3-residual87-scope-v1`
- asset: `b3-residual87-scope.json`
- asset SHA-256:
  `sha256:e1e2086f4e535721dd8697d810318164c6fe77f85de8c4409adc46afbe5f939f`
- key SHA-256:
  `sha256:c28829aa56204db04633546d91b06b938d06f897cd022d2c8147f488415d2742`

SPAC-unit primary resolution:

- workflow run: `35507997799`
- release: `research-phase1-b3-spac-unit-primary-resolution-v1`
- asset: `b3-spac-unit-primary-resolution.json`
- asset SHA-256:
  `sha256:0a6e5f9b271508959f3628babc86965254fe715720790958fd5883202e612065`
- exact resolution-key SHA-256:
  `sha256:2d93f63e9002ef10c913315a7a30bde9377bebf95a7e0442ade39b496e12beba`

## Frozen residual-83 result

Subtracting only those four exact SPAC-unit keys must produce:

- **83 rows**
- **31 issuer/ticker identities**
- residual-key SHA-256:
  `sha256:d1758905bedc027e7f7448cbffed1bf9a35506b947bd8bdec77e48096f28adcd`

The exact-title/ticker-change SPAC-unit bucket must be absent after subtraction.

## Guardrails

- development cohort stays 2016-2020
- evidence/outcome ceiling stays 2022-12-31
- 2023+ OOS stays sealed
- horizons remain 21/63/126/252, with 126 primary
- no prices, returns, MAE, tail membership, robustness output, validation or OOS
  data may be read
- production scoring stays unchanged
- corrected performance stays closed
- no automatic scope expansion

## Next evidence order

After this freeze, prioritize:

1. one-sided P/S identity but Form345 expected ticker on both sides;
2. ticker-change plus changed/overlapping security-title sets;
3. same-ticker rows with overlapping/changed titles;
4. remaining contradictory Form345 cases.

Any later resolution must prove exact membership in this residual-83 scope.
