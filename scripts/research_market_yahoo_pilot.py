"""Research-only adjusted market-data plumbing pilot using Yahoo chart data.

The request is server-side bounded to 2013-2022.  Yahoo remains experimental
and is not the final delisted-security research provider.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import deque
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

import httpx

from insider_turning_engine.ingestion.market.csv_provider import CsvMarketDataProvider
from insider_turning_engine.ingestion.market.quality import probe_market_coverage
from insider_turning_engine.ingestion.market.yahoo_chart import YAHOO_CHART_ROOT, YahooChartProvider

DEFAULT_SYMBOLS = (
    "SPY",
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOGL",
    "JPM",
    "XOM",
    "JNJ",
    "WMT",
    "CAT",
    "IBM",
    "CSCO",
    "PFE",
)


def _bounded_url(symbol: str, start: date, end: date) -> str:
    normalized, yahoo_symbol = YahooChartProvider._symbol(symbol)
    del normalized
    period1 = int(datetime.combine(start, datetime.min.time(), tzinfo=UTC).timestamp())
    period2_date = end + timedelta(days=1)
    period2 = int(datetime.combine(period2_date, datetime.min.time(), tzinfo=UTC).timestamp())
    query = urlencode(
        {
            "period1": period1,
            "period2": period2,
            "interval": "1d",
            "events": "div,splits",
            "includeAdjustedClose": "true",
        }
    )
    return f"{YAHOO_CHART_ROOT}/{quote(yahoo_symbol, safe='-')}?{query}"


def _fetch_symbol(client: httpx.Client, symbol: str, start: date, end: date):
    normalized, _ = YahooChartProvider._symbol(symbol)
    url = _bounded_url(symbol, start, end)
    response = client.get(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 InsiderTurningEngineResearch/1.0",
        },
    )
    host = (urlparse(str(response.url)).hostname or "").lower()
    if response.history or response.is_redirect or host != "query1.finance.yahoo.com":
        raise ValueError("Yahoo chart redirect or response host is not accepted")
    response.raise_for_status()
    bars = YahooChartProvider._parse(response.content, normalized, str(response.url))
    if any(bar.date < start or bar.date > end for bar in bars):
        raise ValueError(f"Yahoo returned an out-of-bounds row for {symbol}")
    return bars


def _rolling_adv63(bars):
    window: deque[Decimal] = deque(maxlen=63)
    result: dict[date, Decimal | None] = {}
    for bar in bars:
        window.append(bar.close * bar.volume)
        result[bar.date] = sum(window, Decimal("0")) / len(window) if window else None
    return result


def run(*, symbols: tuple[str, ...], start: date, end: date, output: Path) -> dict[str, object]:
    if end.year >= 2023:
        raise ValueError("sealed OOS boundary: Yahoo pilot end date must be <= 2022-12-31")
    if start > end:
        raise ValueError("start must be on or before end")

    output.mkdir(parents=True, exist_ok=True)
    bars_by_symbol = {}
    failures: dict[str, str] = {}
    with httpx.Client(timeout=45.0, follow_redirects=False) as client:
        for symbol in symbols:
            try:
                bars_by_symbol[symbol] = _fetch_symbol(client, symbol, start, end)
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                failures[symbol] = str(exc)

    canonical_path = output / "canonical-market.csv"
    with canonical_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "date",
                "ticker",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "adj_close",
                "is_adjusted",
                "adjustment_basis",
                "split_factor",
            ),
        )
        writer.writeheader()
        for symbol in sorted(bars_by_symbol):
            for bar in bars_by_symbol[symbol]:
                writer.writerow(
                    {
                        "date": bar.date.isoformat(),
                        "ticker": bar.symbol,
                        "open": str(bar.open),
                        "high": str(bar.high),
                        "low": str(bar.low),
                        "close": str(bar.close),
                        "volume": bar.volume,
                        "adj_close": str(bar.adj_close),
                        "is_adjusted": "true",
                        "adjustment_basis": bar.adjustment_basis,
                        "split_factor": "",
                    }
                )

    csv_provider = CsvMarketDataProvider(
        canonical_path,
        as_of_date=end,
        provider="yahoo-active-adjusted-pilot",
    )
    coverage = probe_market_coverage(
        csv_provider.bars,
        symbols,
        as_of=end,
        stale_after_days=5,
    )

    symbol_summary_path = output / "symbol-summary.csv"
    with symbol_summary_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "symbol",
                "rows",
                "first_date",
                "last_date",
                "last_adv63_usd",
                "failure",
            ),
        )
        writer.writeheader()
        for symbol in symbols:
            bars = csv_provider.get_daily_bars(symbol)
            last_adv = _rolling_adv63(bars).get(bars[-1].date) if bars else None
            writer.writerow(
                {
                    "symbol": symbol,
                    "rows": len(bars),
                    "first_date": bars[0].date.isoformat() if bars else "",
                    "last_date": bars[-1].date.isoformat() if bars else "",
                    "last_adv63_usd": str(last_adv) if last_adv is not None else "",
                    "failure": failures.get(symbol, ""),
                }
            )

    summary: dict[str, object] = {
        "schemaVersion": "1.0.0",
        "dataset": "Yahoo active adjusted market plumbing pilot",
        "period": f"{start.isoformat()}..{end.isoformat()}",
        "provider": "yahoo-chart-experimental",
        "researchOnly": True,
        "serverSideDateBoundsRequested": True,
        "providerNeutralCsvReload": True,
        "requestedSymbols": list(symbols),
        "coveredSymbols": list(coverage.covered_symbols),
        "missingSymbols": list(coverage.missing_symbols),
        "coverageRate": coverage.coverage_rate,
        "observedRows": coverage.observed_rows,
        "spyCovered": "SPY" in coverage.covered_symbols,
        "adjustedPricesAvailable": all(bar.is_adjusted for bar in csv_provider.bars),
        "delistedCoverageValidated": False,
        "historicalIdentityValidated": False,
        "marketDataJoined": False,
        "canonicalReady": False,
        "signalReady": False,
        "oosOpened": False,
        "failures": failures,
        "status": (
            "YAHOO_ACTIVE_ADJUSTED_PILOT_PASS"
            if "SPY" in coverage.covered_symbols
            and coverage.coverage_rate >= 0.90
            and bool(csv_provider.bars)
            else "YAHOO_ACTIVE_ADJUSTED_PILOT_FAIL"
        ),
        "nextGate": "delisted provider plus PIT security-identity mapping",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "failures.json").write_text(
        json.dumps(failures, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--start", type=date.fromisoformat, default=date(2013, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2022, 12, 30))
    parser.add_argument("--output", type=Path, default=Path("work/yahoo-market-pilot"))
    args = parser.parse_args()
    symbols = tuple(
        dict.fromkeys(
            item.strip().upper()
            for item in args.symbols.split(",")
            if item.strip()
        )
    )
    summary = run(symbols=symbols, start=args.start, end=args.end, output=args.output)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
