# Phase-1 B3 frozen residual-63 continuity scope gate

Frozen: 2026-09-20 after the residual-83 scope and the exact 20-row one-sided
primary-source resolution were independently frozen.

## Authoritative inputs

Residual-83 scope:

- release: `research-phase1-b3-residual83-scope-v1`
- asset: `b3-residual83-scope.json`
- asset SHA-256:
  `sha256:fa2818a00fa299b9838e6f45e2dab04d4da5512b7b4d8f71393908caf53ce7bc`
- key SHA-256:
  `sha256:d1758905bedc027e7f7448cbffed1bf9a35506b947bd8bdec77e48096f28adcd`

One-sided primary resolution:

- workflow run: `35508257853`
- release: `research-phase1-b3-one-sided-primary-resolution-v1`
- asset: `b3-one-sided-primary-resolution.json`
- asset SHA-256:
  `sha256:2b4e30dcac2d032e9f27495f72e67ed1cb70fc14d11ed58abe8d4e2a73d5c45b`
- exact resolution-key SHA-256:
  `sha256:6380297ba23e117849914bb4e2f9e1956a53c22c65a6514d99e992537294861f`

## Frozen residual-63 result

Subtracting only those exact 20 keys must produce:

- **63 rows**
- **27 issuer/ticker identities**
- residual-key SHA-256:
  `sha256:ed13976872da6522da2973a450a1f1c39e22cc19e2ffcc8367b9cc1a1b016b50`

The resolved one-sided evidence bucket must be absent.

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

1. ticker-change plus changed security-title cases;
2. same-ticker rows with overlapping or changed security titles;
3. remaining one-sided evidence;
4. contradictory Form345 cases.

Each later rule must prove membership in this exact residual-63 scope.
