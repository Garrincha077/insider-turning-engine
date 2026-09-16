"""Research-only Stooq market-data pilot bounded to pre-2023 history.

This script intentionally does not change the production market provider.  It
asks Stooq to apply the date bounds server-side so sealed 2023+ market history
is not retrieved during the pilot.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import deque
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx

from insider_turning_engine.ingestion.market.quality import probe_market_coverage
from insider_turning_engine.ingestion.market.stooq import StooqMarketDataProvider

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
BASE_URL = "https://stooq.com/q/d/l/"


def _bounded_url(symbol: str, start: date, end: date) -> str:
    query = urlencode(
        {
            "s": StooqMarketDataProvider.map_symbol(symbol),
            "d1": start.strftime("%Y%m%d"),
            "d2": end.strftime("%Y%m%d"),
            "i": "d",
        }
    )
    return f"{BASE_URL}?{query}"


def _fetch_symbol(client: httpx.Client, symbol: str, start: date, end: date):
    url = _bounded_url(symbol, start, end)
    response = client.get(url, headers={"Accept": "text/csv"})
    if response.history or response.status_code in {301, 302, 303, 307, 308}:
        raise ValueError("Stooq redirects are not accepted")
    if urlparse(str(response.url)).hostname not in {"stooq.com", "www.stooq.com"}:
        raise ValueError("Stooq response host is outside the allow-list")
    response.raise_for_status()
    bars = StooqMarketDataProvider._parse(response.text, symbol, str(response.url))
    if any(bar.date < start or bar.date > end for bar in bars):
        raise ValueError(f"Stooq returned an out-of-bounds row for {symbol}")
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
        raise ValueError("sealed OOS boundary: Stooq pilot end date must be <= 2022-12-31")
    if start > end:
        raise ValueError("start must be on or before end")

    output.mkdir(parents=True, exist_ok=True)
    bars_by_symbol = {}
    failures: dict[str, str] = {}
    with httpx.Client(timeout=30.0, follow_redirects=False) as client:
        for symbol in symbols:
            try:
                bars_by_symbol[symbol] = _fetch_symbol(client, symbol, start, end)
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                failures[symbol] = str(exc)

    coverage = probe_market_coverage(
        bars_by_symbol,
        symbols,
        as_of=end,
        stale_after_days=5,
    )

    canonical_path = output / "canonical-market.csv"
    with canonical_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "date",
                "symbol",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "dollar_volume",
                "adv63_usd",
                "provider",
                "is_adjusted",
                "adjustment_basis",
                "available_at",
            ),
        )
        writer.writeheader()
        for symbol in sorted(bars_by_symbol):
            bars = bars_by_symbol[symbol]
            adv63 = _rolling_adv63(bars)
            for bar in bars:
                writer.writerow(
                    {
                        "date": bar.date.isoformat(),
                        "symbol": bar.symbol,
                        "open": str(bar.open),
                        "high": str(bar.high),
                        "low": str(bar.low),
                        "close": str(bar.close),
                        "volume": bar.volume,
                        "dollar_volume": str(bar.close * bar.volume),
                        "adv63_usd": str(adv63[bar.date]) if adv63[bar.date] is not None else "",
                        "provider": bar.provider,
                        "is_adjusted": str(bar.is_adjusted).lower(),
                        "adjustment_basis": bar.adjustment_basis,
                        "available_at": bar.available_at.isoformat() if bar.available_at else "",
                    }
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
                "split_discontinuity",
                "failure",
            ),
        )
        writer.writeheader()
        split_symbols = set(coverage.split_discontinuity_symbols)
        for symbol in symbols:
            bars = bars_by_symbol.get(symbol, ())
            last_adv = _rolling_adv63(bars).get(bars[-1].date) if bars else None
            writer.writerow(
                {
                    "symbol": symbol,
                    "rows": len(bars),
                    "first_date": bars[0].date.isoformat() if bars else "",
                    "last_date": bars[-1].date.isoformat() if bars else "",
                    "last_adv63_usd": str(last_adv) if last_adv is not None else "",
                    "split_discontinuity": str(symbol in split_symbols).lower(),
                    "failure": failures.get(symbol, ""),
                }
            )

    summary: dict[str, object] = {
        "schemaVersion": "1.0.0",
        "dataset": "Stooq unadjusted historical market pilot",
        "period": f"{start.isoformat()}..{end.isoformat()}",
        "provider": "stooq",
        "researchOnly": True,
        "serverSideDateBoundsRequested": True,
        "requestedSymbols": list(symbols),
        "coveredSymbols": list(coverage.covered_symbols),
        "missingSymbols": list(coverage.missing_symbols),
        "splitDiscontinuitySymbols": list(coverage.split_discontinuity_symbols),
        "quarantinedSymbols": list(coverage.quarantined_symbols),
        "coverageRate": coverage.coverage_rate,
        "observedRows": coverage.observed_rows,
        "spyCovered": "SPY" in coverage.covered_symbols,
        "adjustedPricesAvailable": False,
        "delistedCoverageValidated": False,
        "historicalIdentityValidated": False,
        "marketDataJoined": False,
        "canonicalReady": False,
        "signalReady": False,
        "oosOpened": False,
        "failures": failures,
        "status": (
            "STOOQ_UNADJUSTED_PILOT_PASS"
            if "SPY" in coverage.covered_symbols and coverage.coverage_rate >= 0.90
            else "STOOQ_UNADJUSTED_PILOT_FAIL"
        ),
        "nextGate": "adjusted/delisted provider and PIT security-identity validation",
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
    parser.add_argument("--output", type=Path, default=Path("work/stooq-pilot"))
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
