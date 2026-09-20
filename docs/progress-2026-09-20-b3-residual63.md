# Phase-1 B3 SPAC-unit + one-sided resolutions and residual-63 checkpoint — 2026-09-20

## Status

Two additional performance-blind primary-source resolution gates are complete,
and the exact remaining B3 continuity scope is frozen at 63 rows.

### SPAC-unit primary resolution

- workflow run: **35507997799** — SUCCESS
- release: `research-phase1-b3-spac-unit-primary-resolution-v1`
- asset SHA-256:
  `sha256:0a6e5f9b271508959f3628babc86965254fe715720790958fd5883202e612065`
- resolved rows: **4**
- identities: **DOTAU**, **GLACU**
- resolution-key SHA-256:
  `sha256:2d93f63e9002ef10c913315a7a30bde9377bebf95a7e0442ade39b496e12beba`
- result: same-security continuity under the original unit ticker; the Form345
  reporting-symbol drift to component common ticker is not a security stitch.

### One-sided primary resolution

- workflow run: **35508257853** — SUCCESS
- release: `research-phase1-b3-one-sided-primary-resolution-v1`
- asset SHA-256:
  `sha256:2b4e30dcac2d032e9f27495f72e67ed1cb70fc14d11ed58abe8d4e2a73d5c45b`
- resolved rows: **20**
- resolution-key SHA-256:
  `sha256:6380297ba23e117849914bb4e2f9e1956a53c22c65a6514d99e992537294861f`

Identity-specific results:

- NSEC: 7 same-security rows
- FTNW: 5 same-security rows; later trading suspension is not a holder
  transformation and does not waive exact-session missing-data rules
- LOV: 7 holder-transformation rows; 10 old shares -> 1 successor ADS
- BV: 1 cash-merger row; $5.50 cash per old share

Decision totals:

- `SAME_SECURITY_CONTINUITY`: **12**
- `TRANSFORMED_HOLDER_CONSIDERATION`: **8**

### Residual-63 scope

- workflow run: **35508340176** — SUCCESS
- release: `research-phase1-b3-residual63-scope-v1`
- asset: `b3-residual63-scope.json`
- asset SHA-256:
  `sha256:c217df79265aeb16bd9cf2abe78b9e4573311b52dfd377b5b706e63417f21f39`
- rows: **63**
- issuer/tickers: **27**
- residual-key SHA-256:
  `sha256:ed13976872da6522da2973a450a1f1c39e22cc19e2ffcc8367b9cc1a1b016b50`

## Aggregate continuity progress

Starting unresolved rows: **264**.

Deterministically resolved/candidate rows now: **201 / 264**.

Remaining unresolved: **63 / 264**.

No corrected B3 performance has been opened.

## Guardrails preserved

- development cohort: 2016-2020
- evidence/outcomes through 2022 only
- 2023+ OOS sealed
- 21/63/126/252 horizons unchanged; 126 primary
- `performanceRead=false`
- `priceFieldsRead=[]`
- `oosOpened=false`
- `productionScoringChanged=false`
- final continuity contract not created
- corrected performance closed

## Next work

The 63-row scope contains heterogeneous security-change patterns. The next
primary-source work must remain identity-specific. The largest next bucket has
16 ticker-change/title-change rows across eight issuer/ticker identities and
must not be resolved by a generic ticker-change rule.
