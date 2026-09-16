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

## Stooq status

Stooq remains useful as an optional cross-check, but its CSV endpoint currently requires access/API-key handling on the GitHub runner. The bounded Stooq workflow is therefore diagnostic-only and is not a blocking research gate.

Do not spend additional engineering effort on Stooq unless access becomes convenient.

## Remaining hard gate

Only two material items remain before the market layer can be certified:

1. **Delisted-security coverage** — historical prices must include securities that disappeared during 2013–2022 so the backtest does not silently introduce survivorship bias.
2. **Historical/PIT security identity** — SEC issuer/CIK evidence must map to the correct historical security/ticker without using today's ticker identity as if it were historically constant.

The final provider should export or be converted into the existing canonical CSV contract rather than introducing provider-specific logic into the backtester.

## Provider approach

Keep this simple:

- primary delisted-capable source: one provider only;
- canonical output: existing CSV market contract;
- SPY included as benchmark;
- adjusted daily OHLCV required;
- trailing dollar ADV derived locally;
- IBKR used only as a spot/audit/execution cross-check where helpful;
- optional second provider only for sample verification, not a parallel full pipeline.

A currently available candidate is Financial Datasets because it advertises historical coverage for active and delisted U.S. tickers. It should be evaluated for the remaining hard gate if connected.

## Gate definition

Do **not** set `marketDataJoined=true` until:

- adjusted daily OHLCV coverage is sufficient for development 2016–2020 and validation 2021–2022;
- delisted coverage is quantified and acceptable;
- historical identity mapping is auditable;
- SPY benchmark is complete;
- missing/stale/invalid bars are reported rather than silently dropped;
- no 2023+ data are opened.

## Next step

Connect one delisted-capable historical provider, run a bounded 2013–2022 coverage/identity probe, convert the result to the existing canonical CSV format, and stop adding market-data infrastructure once that gate passes.
