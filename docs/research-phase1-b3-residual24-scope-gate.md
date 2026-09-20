# Phase-1 B3 frozen residual-24 continuity scope gate

Frozen: 2026-09-20 after the residual-43 scope and the 19-row ordinary
common-security primary-source resolution were frozen.

## Authoritative inputs

Residual-43 scope:

- release: `research-phase1-b3-residual43-scope-v1`
- asset: `b3-residual43-scope.json`
- asset SHA-256:
  `sha256:eeb929e959cfe606764d251ad9f9a262c80336e79f395a6c701b84fdbed4cbe3`
- key SHA-256:
  `sha256:be82164c63ed8c8528017ff3201d5172e818655e5c7a8fa48bd7576c7cb02cd6`

Ordinary common-security primary resolution:

- workflow run: `35539681337`
- release: `research-phase1-b3-common-security-primary-resolution-v1`
- asset: `b3-common-security-primary-resolution.json`
- asset SHA-256:
  `sha256:fec6e91a78c665686d5a00baa1baef9a9c6493c4bf53841e8b39bc0e20cc2ac4`
- exact resolution-key SHA-256:
  `sha256:a99206160529fc915c30b9859307e1cd603f7f4fab5d24278519af18919bc430`

## Frozen residual-24 result

Subtracting only those 19 exact ordinary-common resolution keys must produce:

- **24 rows**
- **12 issuer/ticker identities**
- residual key SHA-256:
  `sha256:cd190ed2cfbd8147b5f8c3b3c3f562e4b20093e775b88dfc9a6f0f57dc1167f5`

The exact remaining issuer/ticker set is:

- ARWA
- AAPC
- WYIG
- ATACU
- TPGE
- GIG.U
- TWLVU
- TZACU
- LOACU
- ZGYHU
- SRACU
- NBA.U

These are predominantly SPAC/unit lifecycle or reorganization cases and must
not be resolved by the ordinary-common rule.

## Guardrails

- development cohort remains 2016-2020
- evidence/outcome ceiling remains 2022-12-31
- 2023+ OOS remains sealed
- no prices, returns, MAE, tail membership, robustness output, validation or
  OOS data may be read
- production scoring stays unchanged
- corrected performance stays closed
- no automatic scope expansion

Any later resolution must prove membership in this exact residual-24 scope.
