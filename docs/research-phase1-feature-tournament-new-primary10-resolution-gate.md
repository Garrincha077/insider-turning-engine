# Phase-1 feature tournament new-primary10 resolution gate

Frozen: 2026-09-21 after long-gap7 resolution and before any feature outcome,
validation selection or 2023+ OOS value is opened.

## Purpose

Resolve the final ten Stage-B continuity rows from primary SEC evidence.

The frozen scope contains four historical identities:

- AVGR: 3 event-horizon rows;
- SNES: 2;
- HMG: 2;
- OAS: 3.

The first three are primary-evidence same-security cases. OAS is a bankruptcy
reorganization discontinuity and must not be mapped to the post-emergence OAS
common stock.

## Immutable scope

Release:
`research-phase1-feature-tournament-long-gap7-resolution-v1`.

Asset:
`new-primary10-scope.json`.

SHA-256:
`sha256:b508811617035eb569d359ee9f5cad97f403f8bd0e51e2413150eaf44630a936`.

Rows: **10**.

## Exact Stage-B gap source

Release:
`research-phase1-feature-tournament-stage-b-gap-diagnostics-v1`.

Asset:
`gap-diagnostics.csv`.

SHA-256:
`sha256:7d0bdd8e6fa4fa43ab4d7ee731a8cb00380659a89d3b2626a472ea7d0fb73afa`.

The resolver must reproduce the full frozen gap tuple for every row. A changed
first/last missing session, next observed session or gap size is a hard
failure.

## Frozen SEC evidence

Repository contract:
`research/phase1-feature-tournament-new-primary10-evidence-v1.json`.

Git blob:
`ef2c6874c610532cdbcb4c983ea06cace0ba4936`.

### AVGR — event 1373, horizons 63/126/252

Frozen gap:

- previous observed: 2016-05-03;
- first missing: 2016-05-04;
- last missing: 2016-05-31;
- next observed: 2016-06-01;
- gap sessions: 19.

SEC filings before, during and after the gap preserve the same Avinger Inc.
registrant and common-stock capitalization. The June 2016 quarter reports the
same common stock and ordinary at-the-market common-share issuance, with no
holder exchange, cancellation, merger or reverse split in the gap.

Authorized result for all three horizons:

- `SAME_SECURITY_CONTINUITY`;
- successor AVGR;
- 1.0 successor share per entry share;
- $0 cash.

### SNES — event 8974, horizons 126/252

Frozen gap:

- previous observed: 2018-04-18;
- first missing: 2018-04-19;
- last missing: 2018-05-04;
- next observed: 2018-05-07;
- gap sessions: 12.

The April 2018 proxy states that SenesTech common stock was currently listed
on Nasdaq under SNES while a reverse split was only a proposed compliance
option. The May 2018 10-K/A and later Q2 10-Q preserve the same registrant and
common-stock class.

Authorized result:

- `SAME_SECURITY_CONTINUITY`;
- successor SNES;
- 1.0 share;
- $0 cash.

### HMG — event 21896, horizons 126/252

Two distinct frozen gaps must each be supported.

126-session row:

- previous observed: 2020-09-21;
- first missing: 2020-09-22;
- last missing: 2020-10-07;
- next observed: 2020-10-08;
- gap sessions: 12.

252-session row:

- previous observed: 2021-05-20;
- first missing: 2021-05-21;
- last missing: 2021-06-10;
- next observed: 2021-06-11;
- gap sessions: 14.

SEC 10-Q filings bracketing both gaps identify the same HMG/Courtland
Properties Inc. common stock, par value $1.00, trading as HMG. The 2021
common-stock roll-forward shows ordinary option exercise and treasury-share
retirement, not a replacement security.

Authorized result:

- `SAME_SECURITY_CONTINUITY`;
- successor HMG;
- 1.0 share;
- $0 cash.

### OAS — event 23221, horizons 63/126/252

Frozen gap:

- previous observed: 2020-10-09;
- first missing: 2020-10-12;
- last missing: **2020-11-19**;
- next observed: **2020-11-20**;
- gap sessions: 29.

Primary SEC evidence establishes:

1. Legacy Oasis entered Chapter 11 on 2020-09-30.
2. On the 2020-11-19 emergence date all existing Legacy Oasis equity
   interests were cancelled.
3. 20,000,000 shares of new OAS common stock were issued to allowed notes
   claim holders, not to predecessor common holders.
4. Former predecessor common holders received their pro-rata share of
   1,621,622 warrants.
5. Each warrant was initially exercisable for one successor common share at
   $94.57 and expired 2024-11-19.

The frozen daily common-stock corpus cannot provide a complete mark-to-market
path for that warrant consideration through the later event horizons. The
project already has a B3 precedent that an unvalued warrant leg cannot be
silently discarded.

Authorized OAS result for all three horizons:

- `DISCONTINUOUS_NO_COMPLETE_VALUATION`;
- `BANKRUPTCY_REORG_UNVALUED_WARRANT`;
- no successor common-stock mapping;
- no fabricated stock-return continuation.

## Expected final10 partition

A successful stage must produce exactly:

- 7 `PRICE_CONTINUOUS_ADJUSTED` rows:
  - AVGR 3;
  - SNES 2;
  - HMG 2.
- 3 `DISCONTINUOUS_NO_COMPLETE_VALUATION` rows:
  - OAS 3.
- unresolved rows: **0**.

## Progression boundary

Success of this gate resolves the last ten rows and brings Stage-B continuity
coverage to **210 / 210**.

That does **not** itself open feature outcomes. The next required step is an
immutable merged 210-row final Stage-B continuity contract that:

- reconciles all resolution sources;
- proves no duplicate event-horizon key;
- proves zero unresolved;
- preserves performanceRead=false;
- preserves validationOpened=false;
- preserves oosOpened=false.

Only after that merged contract is green may the feature-tournament discovery
outcomes be opened.
