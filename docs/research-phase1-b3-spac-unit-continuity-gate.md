# Phase-1 B3 SPAC-unit continuity primary-source gate

Frozen: 2026-09-20 after the residual-87 scope was frozen and before any row in
the exact-title/ticker-change bucket is resolved.

## Scope

This gate applies to exactly four residual-87 event-horizon rows in evidence
bucket:

`TICKER_CHANGED_AFTER_PIVOT|TITLE_SET_EXACT_MATCH|TICKER_CHANGED_AFTER_PIVOT`

The four rows reduce to exactly two issuer/unit identities:

- CIK 0001705771 — Draper Oakwood Technology Acquisition, Inc. — `DOTAU`
- CIK 0001735041 — Greenland Acquisition Corporation — `GLACU`

No other residual row may be resolved by this gate.

## Why the Form345/PIT ticker change is not a unit-security symbol change

For both issuers, primary SEC filings establish that the issuer had concurrent
listed securities:

- a SPAC **unit** under the frozen event ticker; and
- separately trading common/ordinary shares, rights and warrants under distinct
  component tickers.

The Form 3/4/5 `issuerTradingSymbol` later moved from the unit ticker to the
component common/ordinary-share ticker. That issuer-level reporting-symbol
change does not establish that the original unit security changed ticker or was
replaced.

A row may be resolved as same-security continuity only when primary SEC
evidence proves all of the following:

1. the frozen event ticker identifies the listed SPAC unit;
2. the unit and component common/ordinary share are concurrently listed under
   distinct symbols;
3. the SEC filing explicitly states that units not separated continue under the
   original unit ticker, or later SEC filings continue to list that original
   unit ticker;
4. primary filings bracket the relevant frozen gap/target period sufficiently
   to establish that the unit security remained outstanding/listed through the
   event horizon;
5. there is no business-combination conversion, redemption, cancellation or
   holder transformation effective before the target exit;
6. all evidence is pre-2023.

## Pinned primary evidence

### DOTAU — CIK 0001705771

SEC Form 8-K accession `0001213900-17-010446` states that holders may separate
the units beginning 2017-10-12, that unseparated units **continue to trade**
under `DOTAU`, and that component Class A common stock, warrants and rights
trade separately as `DOTA`, `DOTAW`, and `DOTAR`.

SEC filings in September 2018 still identify the issuer with concurrent NASDAQ
symbols `DOTA`, `DOTAU`, `DOTAR`, and `DOTAW`, including accession
`0001213900-18-012101` and the 2018-09-26 filing/exhibit under accession
`0001213900-18-013065`.

The later business-combination conversion did not occur until December 2018,
after both frozen target exits in this gate.

### GLACU — CIK 0001735041

SEC Form 8-K accession `0001615774-18-007661` states that commencing
2018-08-08 holders may separately trade the securities included in the units,
while units not separated **continue** under `GLACU`; component ordinary
shares, rights and warrants use `GLAC`, `GLACR`, and `GLACW`.

The Form 10-Q filed under accession `0001213900-19-012745` still registers
ordinary shares as `GLAC` and units as `GLACU` concurrently. Later 2019 SEC
filings, including accession `0001213900-19-017866`, continue to list the unit
as `GLACU`, after both frozen target exits in this gate.

## Frozen resolution semantics

For the exact four scoped rows:

- `resolutionDecision=SAME_SECURITY_CONTINUITY`
- `resultState=PRICE_CONTINUOUS_ADJUSTED`
- `transformationKind=""`
- successor symbol remains the original unit ticker
- `successorSharesPerEntryShare=1.0`
- `cashPerEntryShare=0.0`
- effective date is the frozen long-gap pivot date

The resolver must never stitch `DOTAU` to `DOTA` or `GLACU` to `GLAC`.
Those are different listed security classes that coexisted.

## Guardrails

This gate is performance-blind. It may not read market returns, OHLC values,
MAE, tail membership, robustness results, validation data, or 2023+ OOS.

If any of the exact four keys, issuer CIKs, unit symbols, SEC evidence, target
dates, or concurrent-listing facts differ from this contract, fail closed.
