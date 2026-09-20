# Phase-1 B3 ordinary common-security continuity gate

Frozen: 2026-09-20 after the residual-43 scope was frozen and before any row in
this exact ordinary-common subset is resolved.

## Exact scope

This gate applies only to 19 residual-43 rows:

- PAVM / CIK 0001624326 — 6
- UNAM / CIK 0000100716 — 3
- APDN / CIK 0000744452 — 3
- HSDT / CIK 0001610853 — 3
- SGBX / CIK 0001023994 — 2
- CYCC / CIK 0001130166 — 1
- LMFA / CIK 0001640384 — 1

Exact key SHA-256:

`sha256:a99206160529fc915c30b9859307e1cd603f7f4fab5d24278519af18919bc430`

## Frozen rule

A row in this exact identity set resolves as same-security continuity only
because primary SEC evidence establishes that the frozen ticker continues to
identify the same issuer's common stock through the target horizon.

The changing/overlapping title sets are attributable to one or more of:

- separate warrant/preferred classes being present in one accession but not
  another;
- normalized wording such as `Class A Common Stock` vs `Common Stock`;
- a reverse split that leaves the same common security/ticker in place;
- exchange/uplisting history already completed before the event entry.

None of those facts permits stitching to a different security. Conversely,
none constitutes a mandatory holder transformation for these scoped rows.

## Identity notes

- PAVM: PAVM common and PAVMW/PAVMZ warrants are separately identified;
  common remains PAVM.
- UNAM: same no-par-value common stock remains UNAM.
- APDN: common remains APDN; warrants are separate and the 2019 reverse split
  is a split-adjustment event, not a new security.
- HSDT: Class A/common wording changes, minimum-bid compliance issues and the
  2020 1-for-35 reverse split do not change the HSDT security identity.
- SGBX: scoped entries occur after the June 2017 Nasdaq common-stock listing;
  SGBX remains the common security through both target horizons.
- CYCC: common stock remains outstanding while preferred/warrants are distinct
  instruments.
- LMFA: common and warrant separated from the old unit before the scoped event;
  LMFA common and LMFAW warrants remain distinct.

## Resolution semantics

All 19 rows resolve to:

- `SAME_SECURITY_CONTINUITY`
- `PRICE_CONTINUOUS_ADJUSTED`
- unchanged event ticker
- 1.0 successor shares per entry share
- 0 cash consideration
- effective date = frozen long-gap pivot

Ordinary forward/reverse splits remain handled only by the existing adjusted
market-data convention; this gate does not apply a second split adjustment.

## Guardrails

The gate is performance-blind and may not read price values, returns, MAE,
tail/robustness output, validation or 2023+ OOS. Any mismatch in the exact
19-row keys or issuer/ticker set fails closed.
