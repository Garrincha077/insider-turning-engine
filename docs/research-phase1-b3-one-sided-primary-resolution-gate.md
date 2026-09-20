# Phase-1 B3 one-sided identity primary-source resolution gate

Frozen: 2026-09-20 after the residual-83 scope was frozen and before any row in
the one-sided P/S identity bucket is resolved.

## Exact scope

This gate applies only to the 20 residual-83 rows in evidence bucket:

`BEFORE_ONLY_EXPECTED_TICKER|ONE_SIDED_ACCESSION_ONLY|EXPECTED_TICKER_BOTH_SIDES`

The 20 rows reduce to exactly four issuer/ticker identities:

- CIK 0000865058 — NSEC — 7 rows
- CIK 0001122063 — FTNW — 5 rows
- CIK 0001314475 — LOV — 7 rows
- CIK 0001330421 — BV — 1 row

The exact 20-row key SHA-256 is:

`sha256:6380297ba23e117849914bb4e2f9e1956a53c22c65a6514d99e992537294861f`

No other residual row may be resolved by this gate.

## Frozen identity-specific semantics

### NSEC — same security continuity

Primary SEC filings continue to identify the same common stock, par value
$1.00, under ticker `NSEC` through the relevant 2020-2021 period. The later
cash acquisition was not announced until January 2022, after every scoped
target exit.

All seven NSEC rows therefore resolve to:

- `SAME_SECURITY_CONTINUITY`
- `PRICE_CONTINUOUS_ADJUSTED`
- successor ticker `NSEC`
- 1.0 shares per entry share
- 0 cash consideration

### FTNW — same security continuity, including later trading suspension

Primary SEC filings around the May 2019 long-gap pivot continue to register the
same $0.001 par common stock under ticker `FTNW` on NYSE American. The
December 17, 2019 event was a trading suspension/delisting proceeding, not a
merger, cancellation, exchange or holder transformation.

All five FTNW rows therefore resolve security identity as:

- `SAME_SECURITY_CONTINUITY`
- `PRICE_CONTINUOUS_ADJUSTED`
- successor ticker `FTNW`
- 1.0 shares per entry share
- 0 cash consideration

This security-identity classification does **not** invent an exact target price
after a trading suspension. A later corrected-performance stage must retain
ordinary exact-session missing-data rules if no valid exit bar exists.

### LOV — holder transformation

The November 2, 2017 Spark Networks merger converted each old Spark Networks,
Inc. common share into the right to receive **0.1 American Depositary Share**
of Spark Networks SE. The new ADS retained ticker `LOV`, but it is a new
successor security/issuer; the identical ticker string must not be treated as
same-security continuity.

All seven LOV rows therefore resolve to:

- `TRANSFORMED_HOLDER_CONSIDERATION`
- transformation kind `ADS_EXCHANGE`
- effective date 2017-11-02
- successor issuer CIK 0001705338
- successor ticker `LOV`
- 0.1 successor ADS per old entry share
- 0 cash consideration

### BV — cash merger

Bazaarvoice's acquisition closed on February 1, 2018. Each outstanding BV
common share was converted into the right to receive **$5.50 cash**.

The single BV row therefore resolves to:

- `TRANSFORMED_HOLDER_CONSIDERATION`
- transformation kind `CASH_MERGER`
- effective date 2018-02-01
- no successor share quantity
- $5.50 cash per entry share

The later target exit remains the original frozen XNYS target date. The cash is
carried at the already frozen 0% nominal convention through that target.

## Performance-blind boundary

No rule in this gate may inspect:

- raw or excess returns;
- OHLC values;
- MAE;
- tail membership;
- robustness output;
- validation outcomes;
- 2023+ OOS.

The primary SEC evidence and exact 20-row scope are frozen before any corrected
B3 performance is opened.

## Fail-closed behavior

Any mismatch in row keys, CIKs, tickers, effective dates, exchange ratios, cash
terms, or primary-source identity facts must fail the gate. No fallback
same-ticker assumption is allowed.
