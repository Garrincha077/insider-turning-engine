# Phase-1 B3 frozen residual-13 continuity scope gate

Frozen: 2026-09-20 after the residual-24 scope and the 11-row surviving-unit
primary-source resolution were frozen.

## Authoritative inputs

Residual-24 scope:

- release: `research-phase1-b3-residual24-scope-v1`
- asset: `b3-residual24-scope.json`
- asset SHA-256:
  `sha256:0ae68307aa7c28e366266c14896521b33391edc8093fb51c68546e76e3a31523`
- key SHA-256:
  `sha256:cd190ed2cfbd8147b5f8c3b3c3f562e4b20093e775b88dfc9a6f0f57dc1167f5`

Surviving-unit resolution:

- workflow run: `35540021748`
- release: `research-phase1-b3-surviving-unit-primary-resolution-v1`
- asset: `b3-surviving-unit-primary-resolution.json`
- asset SHA-256:
  `sha256:65ce412c1bee4abdb0e47851f13afa9c8cfa2abd33190c8ac401da29c5c5c8f9`
- exact resolution-key SHA-256:
  `sha256:a59cce3f542956da1d04b11ebcf783732ac0513668ef7fff3e4f40fa95a55371`

## Frozen residual-13 result

Subtracting only those 11 exact resolution keys must produce:

- **13 rows**
- **6 issuer/ticker identities**
- residual key SHA-256:
  `sha256:0183d2bb7d158cfa642cb02106eb1937d7e0a327db9e23efb4423188b13c5a18`

Exact remaining identities:

- ARWA / CIK 0001622577 — 3 rows
- AAPC / CIK 0001630940 — 3 rows
- WYIG / CIK 0001641398 — 3 rows
- ATACU / CIK 0001680873 — 2 rows
- TPGE / CIK 0001698990 — 1 row
- NBA.U / CIK 0001823882 — 1 row

These are the remaining target-specific transformation/lifecycle cases. They
must not inherit any same-unit or ordinary-common rule by analogy.

## Guardrails

- development cohort stays 2016-2020
- evidence/outcome ceiling stays 2022-12-31
- 2023+ OOS stays sealed
- no realized prices/returns/MAE/tail/robustness fields may be read
- production scoring stays unchanged
- corrected performance stays closed
- no automatic scope expansion

Any next resolution must prove exact membership in this residual-13 scope and
must use pinned primary transaction terms.
