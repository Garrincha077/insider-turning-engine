"""Research-only Alpaca SIP historical market-data backfill.

The script is intentionally bounded to 2016-2022 and never requests 2023+.
It uses exact historical SEC trading symbols with ``asof=-`` so Alpaca does
not silently remap a symbol to a different current entity. Output is a simple
canonical CSV that the existing CsvMarketDataProvider can ingest later.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

API_URL = "https://data.alpaca.markets/v2/stocks/bars"
BATCH_SIZE = 50
MAX_ATTEMPTS = 6


class DeterministicRequestError(RuntimeError):
    """An Alpaca 4xx response that retries cannot fix."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"Alpaca HTTP {status_code}: {body}")
        self.status_code = status_code
        self.body = body


def _load_year_symbols(source: Path, year: int) -> tuple[list[str], dict[str, int]]:
    """Return symbols needed for one year plus inventory diagnostics.

    A market year includes SEC tickers observed in that year and the prior
    year. The prior-year carry is required for forward-return horizons from
    late prior-year insider events. SPY is always included as benchmark.
    """

    if not 2016 <= year <= 2022:
        raise ValueError("Alpaca research backfill year must be within 2016-2022")

    wanted_years = {year, year - 1} if year > 2016 else {2016}
    symbols: set[str] = {"SPY"}
    rows_by_year: dict[int, int] = defaultdict(int)
    missing_ticker_rows = 0

    with source.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            knowledge = str(row["timestamps"]["knowledgeAt"])
            knowledge_year = int(knowledge[:4])
            if knowledge_year >= 2023:
                raise ValueError("sealed OOS boundary violated by SEC input")
            if knowledge_year not in wanted_years:
                continue
            rows_by_year[knowledge_year] += 1
            ticker = row.get("issuer", {}).get("ticker")
            if not ticker:
                missing_ticker_rows += 1
                continue
            symbols.add(str(ticker).strip().upper())

    diagnostics = {
        "secRowsInScope": sum(rows_by_year.values()),
        "missingTickerRowsInScope": missing_ticker_rows,
        "requestedSymbols": len(symbols),
    }
    return sorted(symbols), diagnostics


def _request_page(
    client: httpx.Client,
    headers: dict[str, str],
    params: dict[str, str | int],
) -> dict[str, Any]:
    delay = 1.0
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.get(API_URL, headers=headers, params=params)
            if response.status_code == 429:
                retry_after = response.headers.get("retry-after")
                sleep_for = float(retry_after) if retry_after else delay
                time.sleep(max(0.5, min(sleep_for, 30.0)))
                delay = min(delay * 2, 30.0)
                continue
            if 400 <= response.status_code < 500:
                body = response.text[:1000].replace("\n", " ")
                raise DeterministicRequestError(response.status_code, body)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Alpaca response is not an object")
            return payload
        except DeterministicRequestError:
            raise
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt == MAX_ATTEMPTS:
                break
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
    raise RuntimeError(f"Alpaca request failed after {MAX_ATTEMPTS} attempts: {last_error}")


def _batches(items: list[str], size: int = BATCH_SIZE):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def run(*, source: Path, year: int, output: Path) -> dict[str, object]:
    api_key = os.environ.get("ALPACA_API_KEY_ID", "").strip()
    api_secret = os.environ.get("ALPACA_API_SECRET_KEY", "").strip()
    if not api_key or not api_secret:
        raise ValueError("ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY are required")

    symbols, diagnostics = _load_year_symbols(source, year)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / f"canonical-market-{year}.csv"
    failures: list[dict[str, object]] = []
    symbol_quarantines: list[dict[str, object]] = []
    returned_symbols: set[str] = set()
    total_rows = 0
    zero_volume_rows = 0
    first_date: str | None = None
    last_date: str | None = None

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
        "Accept": "application/json",
        "User-Agent": "InsiderTurningEngine-Research/1.0",
    }

    with csv_path.open("w", newline="", encoding="utf-8") as stream:
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
                "trade_count",
                "vwap",
                "terminal_candidate",
                "provider",
            ),
        )
        writer.writeheader()

        with httpx.Client(timeout=60.0, follow_redirects=False) as client:

            def fetch_batch(batch: list[str], batch_index: int) -> bool:
                nonlocal first_date, last_date, total_rows, zero_volume_rows
                page_token: str | None = None
                while True:
                    params: dict[str, str | int] = {
                        "symbols": ",".join(batch),
                        "timeframe": "1Day",
                        "start": f"{year}-01-01",
                        "end": f"{year}-12-31T23:59:59Z",
                        "limit": 10000,
                        "adjustment": "all",
                        "feed": "sip",
                        "asof": "-",
                        "sort": "asc",
                    }
                    if page_token:
                        params["page_token"] = page_token
                    try:
                        payload = _request_page(client, headers, params)
                    except DeterministicRequestError as exc:
                        if page_token is None and len(batch) > 1:
                            midpoint = len(batch) // 2
                            left_ok = fetch_batch(batch[:midpoint], batch_index)
                            right_ok = fetch_batch(batch[midpoint:], batch_index)
                            return left_ok and right_ok
                        if page_token is None and len(batch) == 1:
                            symbol_quarantines.append(
                                {
                                    "batchIndex": batch_index,
                                    "symbol": batch[0],
                                    "statusCode": exc.status_code,
                                    "error": exc.body,
                                }
                            )
                            return True
                        failures.append(
                            {
                                "batchIndex": batch_index,
                                "symbols": batch,
                                "pageToken": page_token,
                                "error": str(exc),
                            }
                        )
                        return False
                    except RuntimeError as exc:
                        failures.append(
                            {
                                "batchIndex": batch_index,
                                "symbols": batch,
                                "pageToken": page_token,
                                "error": str(exc),
                            }
                        )
                        return False

                    bars = payload.get("bars") or {}
                    if not isinstance(bars, dict):
                        failures.append(
                            {
                                "batchIndex": batch_index,
                                "symbols": batch,
                                "pageToken": page_token,
                                "error": "bars payload is not an object",
                            }
                        )
                        return False

                    for ticker, ticker_bars in bars.items():
                        if not isinstance(ticker_bars, list):
                            continue
                        normalized = str(ticker).upper()
                        for bar in ticker_bars:
                            timestamp = str(bar["t"])
                            day = timestamp[:10]
                            if not day.startswith(str(year)):
                                raise ValueError(
                                    f"out-of-bounds Alpaca row: {normalized} {day}"
                                )
                            volume = int(bar.get("v", 0) or 0)
                            trade_count = int(bar.get("n", 0) or 0)
                            terminal = volume == 0 and trade_count == 0
                            writer.writerow(
                                {
                                    "date": day,
                                    "ticker": normalized,
                                    "open": bar["o"],
                                    "high": bar["h"],
                                    "low": bar["l"],
                                    "close": bar["c"],
                                    "volume": volume,
                                    "adj_close": bar["c"],
                                    "is_adjusted": "true",
                                    "adjustment_basis": "alpaca-adjustment-all",
                                    "split_factor": "",
                                    "trade_count": trade_count,
                                    "vwap": bar.get("vw", ""),
                                    "terminal_candidate": str(terminal).lower(),
                                    "provider": "alpaca-sip",
                                }
                            )
                            returned_symbols.add(normalized)
                            total_rows += 1
                            if terminal:
                                zero_volume_rows += 1
                            if first_date is None or day < first_date:
                                first_date = day
                            if last_date is None or day > last_date:
                                last_date = day

                    page_token_raw = payload.get("next_page_token")
                    page_token = str(page_token_raw) if page_token_raw else None
                    if not page_token:
                        return True

            for batch_index, batch in enumerate(_batches(symbols)):
                if not fetch_batch(batch, batch_index):
                    break

    quarantined_symbols = {str(item["symbol"]) for item in symbol_quarantines}
    symbols_without_bars = sorted(set(symbols) - returned_symbols - quarantined_symbols)
    summary: dict[str, object] = {
        "schemaVersion": "1.1.0",
        "dataset": "Alpaca SIP adjusted historical market backfill",
        "year": year,
        "feed": "sip",
        "adjustment": "all",
        "symbolMapping": "disabled-with-asof-dash",
        "requestedSymbols": diagnostics["requestedSymbols"],
        "returnedSymbols": len(returned_symbols),
        "symbolsWithoutBars": len(symbols_without_bars),
        "symbolsWithoutBarsSample": symbols_without_bars[:100],
        "symbolQuarantines": len(symbol_quarantines),
        "rows": total_rows,
        "zeroVolumeTerminalCandidateRows": zero_volume_rows,
        "firstDate": first_date,
        "lastDate": last_date,
        "secRowsInScope": diagnostics["secRowsInScope"],
        "missingTickerRowsInScope": diagnostics["missingTickerRowsInScope"],
        "requestFailures": failures,
        "researchOnly": True,
        "marketDataJoined": False,
        "canonicalReady": False,
        "signalReady": False,
        "oosOpened": False,
        "status": "ALPACA_BACKFILL_PASS" if not failures and total_rows else "ALPACA_BACKFILL_FAIL",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "request-failures.json").write_text(
        json.dumps(failures, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "symbol-quarantines.json").write_text(
        json.dumps(symbol_quarantines, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if failures:
        raise RuntimeError(f"Alpaca backfill failed closed with {len(failures)} request failure(s)")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(source=args.source, year=args.year, output=args.output), indent=2))


if __name__ == "__main__":
    main()
