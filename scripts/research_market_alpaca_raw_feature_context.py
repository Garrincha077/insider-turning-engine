"""Research-only Alpaca SIP raw-price context for Phase-1 feature formation.

This dataset exists only to make PIT price/basis/liquidity context economically
coherent. It does not compute forward returns or open validation/OOS.

The canonical 2016-2022 research market release uses adjustment=all and is
preserved unchanged. This parallel context uses adjustment=raw, asof="-", and
only 2016-2020. Earliest-2016 trailing context may therefore be missing and is measured by Stage A coverage.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from pathlib import Path

import httpx
import research_market_alpaca_backfill as base

MIN_YEAR = 2016
MAX_YEAR = 2020
SEALED_YEAR = 2023


def _load_context_symbols(source: Path, year: int) -> tuple[list[str], dict[str, int]]:
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError("raw feature-context year must be 2016-2020")

    if year < 2020:
        wanted_years = {year, year + 1}
    else:
        wanted_years = {2020}

    symbols: set[str] = set()
    rows_by_year: dict[int, int] = defaultdict(int)
    missing_ticker_rows = 0

    with source.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            knowledge = str((row.get("timestamps") or {}).get("knowledgeAt") or "")
            if len(knowledge) < 4:
                raise ValueError("SEC source row missing knowledgeAt")
            knowledge_year = int(knowledge[:4])
            if knowledge_year >= SEALED_YEAR:
                raise ValueError("sealed OOS boundary violated by SEC input")
            if knowledge_year not in wanted_years:
                continue
            rows_by_year[knowledge_year] += 1
            ticker = (row.get("issuer") or {}).get("ticker")
            if not ticker:
                missing_ticker_rows += 1
                continue
            symbols.add(str(ticker).strip().upper())

    if not symbols:
        raise ValueError(f"no symbols found for raw context year {year}")

    return sorted(symbols), {
        "sourceKnowledgeYears": sorted(wanted_years),
        "secRowsInScope": sum(rows_by_year.values()),
        "missingTickerRowsInScope": missing_ticker_rows,
        "requestedSymbols": len(symbols),
    }


def run(*, source: Path, year: int, output: Path) -> dict[str, object]:
    api_key = os.environ.get("ALPACA_API_KEY_ID", "").strip()
    api_secret = os.environ.get("ALPACA_API_SECRET_KEY", "").strip()
    if not api_key or not api_secret:
        raise ValueError("ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY are required")

    symbols, diagnostics = _load_context_symbols(source, year)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / f"raw-feature-market-{year}.csv"
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
        "User-Agent": "InsiderTurningEngine-Research-FeatureContext/1.0",
    }

    fieldnames = (
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
    )

    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
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
                        "adjustment": "raw",
                        "feed": "sip",
                        "asof": "-",
                        "sort": "asc",
                    }
                    if page_token:
                        params["page_token"] = page_token

                    try:
                        payload = base._request_page(client, headers, params)
                    except base.DeterministicRequestError as exc:
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
                                "error": "Alpaca bars payload is not an object",
                            }
                        )
                        return False

                    for symbol, values in bars.items():
                        normalized = str(symbol).strip().upper()
                        if normalized not in set(batch):
                            raise ValueError("Alpaca returned symbol outside requested batch")
                        if not isinstance(values, list):
                            raise ValueError("Alpaca symbol bars are not a list")
                        for bar in values:
                            day = str(bar["t"])[:10]
                            if int(day[:4]) != year:
                                raise ValueError(
                                    f"out-of-bounds raw context row: {normalized} {day}"
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
                                    "is_adjusted": "false",
                                    "adjustment_basis": "alpaca-adjustment-raw",
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

            for batch_index, batch in enumerate(base._batches(symbols)):
                if not fetch_batch(batch, batch_index):
                    break

    quarantined = {str(item["symbol"]) for item in symbol_quarantines}
    missing = sorted(set(symbols) - returned_symbols - quarantined)
    summary: dict[str, object] = {
        "schemaVersion": "1.0.0",
        "dataset": "Alpaca SIP raw feature-formation market context",
        "year": year,
        "feed": "sip",
        "adjustment": "raw",
        "symbolMapping": "disabled-with-asof-dash",
        **diagnostics,
        "returnedSymbols": len(returned_symbols),
        "symbolsWithoutBars": len(missing),
        "symbolsWithoutBarsSample": missing[:100],
        "symbolQuarantines": len(symbol_quarantines),
        "rows": total_rows,
        "zeroVolumeTerminalCandidateRows": zero_volume_rows,
        "firstDate": first_date,
        "lastDate": last_date,
        "requestFailures": failures,
        "featureContextOnly": True,
        "forwardReturnsComputed": False,
        "marketDataJoinedToOutcomes": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "status": (
            "ALPACA_RAW_FEATURE_CONTEXT_PASS"
            if not failures and total_rows
            else "ALPACA_RAW_FEATURE_CONTEXT_FAIL"
        ),
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
        raise RuntimeError(
            f"raw feature context failed closed with {len(failures)} request failures"
        )
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
