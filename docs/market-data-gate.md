# Historical Market-Data Gate

**Updated:** 2026-09-16  
**Scope:** research-only, 2013–2022  
**Sealed OOS 2023+:** not opened  
**Production scoring:** unchanged

## Current status

The SEC PIT transaction and amendment layers are complete enough to begin historical market-data work. The market-data implementation is intentionally kept minimal and provider-neutral.

### What already works

- Existing canonical `DailyBar` contract supports OHLCV, adjusted close, adjustment metadata, split factor, availability time, and provenance.
- Existing `CsvMarketDataProvider` provides the stable vendor-neutral ingestion boundary for backtests.
- Existing market quality probes cover missing symbols, stale data, and large unadjusted discontinuities.
- Existing Stooq adapter is explicitly unadjusted and therefore is not treated as the final research price source.
- A bounded Yahoo research pilot successfully proved the adjusted active-security plumbing for 2013–2022.
- SEC historical filings already preserve issuer CIK plus the filing-time `issuerTradingSymbol`, so PIT ticker identity does not need to be reconstructed from today's ticker.
- Alpaca SIP has been verified on multiple securities that are now inactive/delisted and can supply historical daily bars from 2016 onward.

### Adjusted active-security plumbing pilot

GitHub Actions run: `35117859983`

Result: `YAHOO_ACTIVE_ADJUSTED_PILOT_PASS`

Pilot universe:

- SPY
- AAPL
- MSFT
- AMZN
- GOOGL
- JPM
- XOM
- JNJ
- WMT
- CAT
- IBM
- CSCO
- PFE

Observed result:

- requested symbols: 13
- covered symbols: 13
- coverage: 100%
- observed daily rows: 32,734
- SPY covered: yes
- adjusted prices available: yes
- provider-neutral canonical CSV reload: PASS
- failures: 0
- server-side date range: 2013-01-01 through 2022-12-30
- `oosOpened=false`
- `marketDataJoined=false`
- `canonicalReady=false`
- `signalReady=false`

Yahoo remains an experimental plumbing source only. Passing this pilot does **not** certify the historical market dataset for formal backtesting.

## Yahoo delisted probe

GitHub Actions run: `35119766654`

A bounded pre-2023 probe used nine securities that disappeared from the public market universe during the historical period:

`TWTR, XLNX, CERN, WORK, FIT, CELG, MON, LNKD, RHT`

Result: **0/9 usable historical series**. Yahoo therefore cannot be the delisted-security layer for this project.

The failure was useful because it established the survivorship limitation before any formal backtest was run.

## Stooq status

Stooq remains useful as an optional cross-check, but its CSV endpoint currently requires access/API-key handling on the GitHub runner. The bounded Stooq workflow is therefore diagnostic-only and is not a blocking research gate.

Do not spend additional engineering effort on Stooq unless access becomes convenient.

## Financial Datasets status

The connector was successfully authorized, but the connected Financial Datasets account currently has zero credits. A single company-facts request was rejected for insufficient balance.

No additional Financial Datasets requests should be made unless credits are intentionally purchased. It is no longer required for the current baseline path because Alpaca has demonstrated the needed delisted historical coverage from 2016 onward.

## Historical identity

The historical identity requirement is substantially simpler than originally expected.

SEC Form 4/5 observations preserve:

- issuer CIK;
- filing-time `issuerTradingSymbol`;
- SEC acceptance / knowledge time.

The SEC parser stores that historical ticker alongside issuer CIK. Therefore the baseline market join can use exact PIT SEC symbols rather than mapping every observation through a present-day security master.

Rows where SEC does not contain a ticker remain explicit missing/attrition observations. They must not be guessed or silently remapped.

## Alpaca delisted coverage findings

The connected Alpaca data source was tested directly before building any full backfill.

### TWTR

- Alpaca asset reference identifies `TWTR` / Twitter Inc as `inactive`.
- 2022 historical bars through the final trading period are available even though Yahoo no longer supplies the series.
- SIP returned all 252 daily sessions requested for 2016 with consolidated volume.
- 2014 returned no data, consistent with Alpaca historical stock coverage beginning around 2016.

### Additional inactive/delisted examples

A 2018 SIP sample returned historical bars for:

- `XLNX`: 125 rows for the requested half-year window;
- `CELG`: 125 rows;
- `RHT`: 125 rows.

`MON` was also available before its acquisition. The final normal market bar observed on 2018-06-06 was approximately 127.95 USD with substantial volume. Subsequent zero-volume constant-value rows must be treated as terminal candidates rather than ordinary trading sessions.

These checks are sufficient to justify Alpaca SIP as the primary 2016–2022 market-data candidate for the simple insider baseline, subject to the full coverage audit below.

## SEC ticker inventory for Alpaca

GitHub Actions run: `35120360146`

The amendment-reconciled `effective-end-2022.jsonl` was inventoried without opening 2023+.

Observed 2016–2022 universe:

- effective SEC rows: **405,098**;
- unique historical tickers: **7,046**;
- unique issuer + ticker pairs: **7,370**;
- rows missing a historical ticker: **3,392** (~0.84%).

Unique tickers by year:

| Year | Unique tickers |
| --- | ---: |
| 2016 | 2,873 |
| 2017 | 2,598 |
| 2018 | 2,795 |
| 2019 | 2,670 |
| 2020 | 2,980 |
| 2021 | 2,686 |
| 2022 | 2,859 |

This is small enough for a straightforward annual/resumable backfill. No additional market-data platform is needed for the baseline unless the coverage audit later exposes a material Alpaca gap.

## Alpaca backfill implementation

Research-only backfill code now exists:

- `scripts/research_market_alpaca_backfill.py`
- `.github/workflows/research-market-alpaca-backfill.yml`

The workflow is deliberately simple:

- annual jobs for 2016–2022;
- Alpaca SIP feed;
- daily bars;
- `adjustment=all`;
- exact historical SEC symbols with `asof=-` to avoid silent symbol remapping;
- SPY included;
- retry logic with fail-closed request handling;
- zero-volume / zero-trade rows marked as terminal candidates;
- output converted to the existing canonical CSV contract;
- 2023+ prohibited;
- annual evidence persisted only after all annual jobs pass.

The push-triggered lint preflight passed on run `35120906587`. The actual backfill is restricted to manual `workflow_dispatch`, so commits cannot accidentally launch thousands of market-data requests.

## Gate definition

Do **not** set `marketDataJoined=true` until the Alpaca 2016–2022 backfill is complete and the event-level audit confirms:

- sufficient adjusted daily OHLCV coverage for development 2016–2020 and validation 2021–2022;
- SPY benchmark completeness;
- delisted/inactive securities are represented rather than silently dropped;
- terminal / zero-volume synthetic rows are not treated as ordinary sessions;
- missing SEC tickers and missing market histories are quantified as attrition;
- no 2023+ data are opened.

The 2013–2015 warm-up market history is not required to run the predeclared **simple insider baseline** because that benchmark does not require backward-looking technical features. The older market-history problem can be revisited before the technical-feature tournament instead of blocking the baseline now.

## Next step

Add Alpaca API credentials to GitHub Actions secrets and manually run `Backfill Alpaca SIP market history 2016-2022`.

After it completes, run the event-level coverage and terminal-outcome audit. If that passes, close the market-data gate for the simple baseline and proceed to development 2016–2020 followed by validation 2021–2022.
