# Phase-1 B3 second SPAC-unit continuity primary-source gate

Frozen: 2026-09-20 after the residual-63 scope was frozen and before any row in
this exact SPAC-unit subset is resolved.

## Exact scope

This gate applies to exactly eight residual-63 rows from the
ticker-change/title-change evidence bucket, reducing to four identities:

- CIK 0001719893 — MTECU — 4 rows
- CIK 0001768910 — GRCYU — 2 rows
- CIK 0001777393 — SBE.U — 1 row
- CIK 0001785424 — FSRVU — 1 row

Exact 8-row key SHA-256:

`sha256:fae1020ef5d77cd93b885da6bc4e5c8b4a83ec1ded373f9ccc2148bf90add999`

No other residual row may be resolved by this gate.

## Frozen primary-source rule

For each identity, primary SEC filings must establish that:

1. the event ticker is the listed SPAC **unit**;
2. a distinct component common/ordinary-share ticker exists concurrently;
3. unseparated units continue under the original unit ticker, or a later
   pre-2023 SEC filing continues to register/list that unit ticker;
4. the original unit remains outstanding/listed through the frozen target exit;
5. no business-combination unit separation or other holder transformation is
   effective on or before that target exit.

A change in Form 3/4/5 `issuerTradingSymbol` from the unit ticker to the
component common ticker is therefore not a security-continuity stitch.

## Pinned evidence

### MTECU

MTech's February 2018 8-K states that unseparated units continue under
`MTECU`, while Class A common and warrants trade separately as `MTEC` and
`MTECW`. The 2018 Form 10-K reports MTECU, MTEC and MTECW as concurrently
traded and reports unit holders as of 2019-03-13, after the latest scoped target
exit of 2019-03-12.

### GRCYU

Greencity's Form 10-Q for the period ended 2021-09-30 registers units under
`GRCYU` and ordinary shares under `GRCY` concurrently. Both scoped targets
(2021-08-03 and 2021-09-01) precede that confirming period end, with no business
combination completed.

### SBE.U

Switchback's 2019 Form 10-K registers units under `SBE.U`, Class A common
under `SBE`, and warrants separately, and states that unseparated units
continue under `SBE.U`. It reports a unit holder of record as of 2020-03-27,
after the scoped 2020-03-04 target exit. The ChargePoint business combination
occurred later.

### FSRVU

FinServ's 2020 Q3 Form 10-Q concurrently registers units under `FSRVU`,
Class A common under `FSRV`, and warrants under `FSRVW`. The filing reports
share counts as of 2020-11-12, after the scoped 2020-11-10 target exit. The
Katapult business combination occurred later.

## Frozen resolution semantics

All eight rows resolve as:

- `SAME_SECURITY_CONTINUITY`
- `PRICE_CONTINUOUS_ADJUSTED`
- successor symbol remains the original unit ticker
- successor quantity 1.0
- cash consideration 0.0
- effective date = frozen long-gap pivot

The resolver must never substitute the component common ticker for the unit.

## Guardrails

The gate is performance-blind. It may not read prices, realized returns, MAE,
tail membership, robustness output, validation data or 2023+ OOS. Any mismatch
in exact keys, identities, target dates or primary evidence fails closed.
