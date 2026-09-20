# Phase-1 B3 surviving-unit primary-source continuity gate

Frozen: 2026-09-20 after the residual-24 scope was frozen and before any row in
this exact surviving-unit subset is resolved.

## Exact scope

This gate applies only to 11 residual-24 rows:

- GIG.U / CIK 0001719489 — 1
- TWLVU / CIK 0001726146 — 4
- TZACU / CIK 0001742927 — 2
- LOACU / CIK 0001743858 — 1
- ZGYHU / CIK 0001773086 — 2
- SRACU / CIK 0001781162 — 1

Exact key SHA-256:

`sha256:a59cce3f542956da1d04b11ebcf783732ac0513668ef7fff3e4f40fa95a55371`

## Frozen semantics

### Same unit under unchanged symbol

Primary SEC filings after each scoped target continue to register the same unit
security for:

- GIG.U
- TZACU
- LOACU
- ZGYHU
- SRACU

Those rows resolve to `SAME_SECURITY_CONTINUITY`,
`PRICE_CONTINUOUS_ADJUSTED`, unchanged ticker, 1.0 unit per entry unit, and
0 cash consideration.

### TWLVU -> BROGU symbol change

Twelve Seas Investment Company announced that effective 2019-04-15 its unit
ticker changed from `TWLVU` to `BROGU`; the unit composition remained one
ordinary share, one right, and one warrant.

Therefore:

- the two scoped targets before 2019-04-15 remain
  `SAME_SECURITY_CONTINUITY` under TWLVU;
- the two scoped targets after 2019-04-15 resolve
  `SYMBOL_CHANGED_SAME_SECURITY` with successor symbol BROGU, 1.0 unit per
  entry unit, and 0 cash consideration.

This gate must not treat the unit ticker change as a holder transformation and
must not stitch a unit to its separately traded component share.

## Primary evidence

- GIG: 2019 Form 10-Q accession `0001564590-19-030864` continues to register
  GIG.U units after the 2018-12-14 scoped target.
- TWLV: 2019-04-12 Form 8-K accession `0001213900-19-006239` states the unit
  ticker changes TWLVU -> BROGU effective 2019-04-15; later Form 10-Q accession
  `0001213900-19-015746` registers BROGU units.
- TZAC: Form 10-Q accession `0001104659-20-003044` continues to register TZACU
  after both 2019 scoped targets.
- LOAC: September 2019 Form 8-K accession `0001144204-19-044586` continues to
  register LOACU after the 2019-09-10 scoped target.
- ZGYH: 2021 Form 10-Q accession `0001104659-21-026308` and later 8-K
  accession `0001104659-21-067520` continue to register ZGYHU through and
  after both scoped targets.
- SRAC: 2021-03-24 Form 8-K accession `0001213900-21-017762` still registers
  SRACU, proving the unit remained outstanding after the 2020-11-18 target.

## Guardrails

The gate is performance-blind. It may not read market prices, returns, MAE,
tail membership, robustness output, validation, or 2023+ OOS. Any mismatch in
the exact keys, symbols, dates, or SEC evidence fails closed.
