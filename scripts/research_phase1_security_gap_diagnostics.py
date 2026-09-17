"""Diagnose frozen Phase-1 continuity gaps without reading prices or returns.

The runner consumes the already frozen continuity ledger and bounded market files,
reads only session-presence fields (date/ticker/volume/trade_count/terminal), and
reports the exact observed sessions bracketing each predeclared long-gap candidate.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import exchange_calendars as xcals

import research_market_event_audit as market_audit

SEALED_YEAR = 2023
FROZEN_GAP_THRESHOLD = 10


def _bool(value: object) -> bool:
    return str(value).strip().lower() == "true"


def _load_frozen_gap_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {
            "eventNumber",
            "issuerCik",
            "ticker",
            "entrySession",
            "horizon",
            "targetExitSession",
            "state",
            "resolutionSource",
            "maxInternalGapSessions",
            "longInternalGapCandidate",
        }
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("continuity ledger missing required gap fields")
        rows: list[dict[str, str]] = []
        for raw in reader:
            if raw.get("state") != "UNRESOLVED_CONTINUITY":
                continue
            if raw.get("resolutionSource") != "long_internal_gap":
                continue
            if not _bool(raw.get("longInternalGapCandidate")):
                raise ValueError("frozen long-gap row lost candidate flag")
            row = {field: str(raw.get(field) or "").strip() for field in required}
            for field in ("entrySession", "targetExitSession"):
                value = row[field]
                if not value or int(value[:4]) >= SEALED_YEAR:
                    raise ValueError("sealed OOS boundary violated by gap metadata")
            if int(row["maxInternalGapSessions"]) < FROZEN_GAP_THRESHOLD:
                raise ValueError("frozen gap row is below predeclared threshold")
            rows.append(row)
    if not rows:
        raise ValueError("no frozen long-gap rows found")
    return rows


def _regular_observed_indices(
    market_root: Path,
    wanted_tickers: set[str],
    session_index: dict[str, int],
) -> dict[str, list[int]]:
    observed: dict[str, list[int]] = defaultdict(list)
    for path in market_audit._market_files(market_root):
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"date", "ticker", "volume", "trade_count", "terminal_candidate"}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError(f"market file missing presence fields: {path}")
            for raw in reader:
                ticker = str(raw.get("ticker") or "").strip().upper()
                if ticker not in wanted_tickers:
                    continue
                day = str(raw.get("date") or "")[:10]
                if not day or int(day[:4]) >= SEALED_YEAR:
                    raise ValueError("sealed OOS boundary violated by market row")
                if _bool(raw.get("terminal_candidate")):
                    continue
                if int(float(raw.get("volume") or 0)) <= 0:
                    continue
                if int(float(raw.get("trade_count") or 0)) <= 0:
                    continue
                index = session_index.get(day)
                if index is not None:
                    observed[ticker].append(index)
    for ticker in observed:
        observed[ticker] = sorted(set(observed[ticker]))
    return observed


def _max_gap_detail(
    observed_indices: list[int], start_index: int, end_index: int
) -> tuple[int, int | None, int | None]:
    left = bisect.bisect_left(observed_indices, start_index)
    right = bisect.bisect_right(observed_indices, end_index)
    bounded = observed_indices[left:right]
    if len(bounded) < 2:
        return 0, None, None

    best_gap = -1
    best_previous: int | None = None
    best_next: int | None = None
    for previous, following in zip(bounded, bounded[1:], strict=False):
        gap = following - previous - 1
        if gap > best_gap:
            best_gap = gap
            best_previous = previous
            best_next = following
    return max(best_gap, 0), best_previous, best_next


def run(*, ledger_path: Path, market_root: Path, output_dir: Path) -> dict[str, Any]:
    frozen_rows = _load_frozen_gap_rows(ledger_path)
    calendar = xcals.get_calendar("XNYS")
    sessions = [
        str(value.date())
        for value in calendar.sessions_in_range("2016-01-01", "2022-12-31")
    ]
    session_index = {day: index for index, day in enumerate(sessions)}

    wanted_tickers = {row["ticker"].upper() for row in frozen_rows}
    observed = _regular_observed_indices(market_root, wanted_tickers, session_index)

    diagnostics: list[dict[str, Any]] = []
    for row in frozen_rows:
        ticker = row["ticker"].upper()
        start_index = session_index.get(row["entrySession"])
        end_index = session_index.get(row["targetExitSession"])
        if start_index is None or end_index is None:
            raise ValueError("gap window outside bounded XNYS calendar")
        gap, previous_index, next_index = _max_gap_detail(
            observed.get(ticker, []), start_index, end_index
        )
        if gap != int(row["maxInternalGapSessions"]):
            raise ValueError(
                f"frozen gap mismatch for {ticker}: ledger={row['maxInternalGapSessions']} recomputed={gap}"
            )
        if previous_index is None or next_index is None:
            raise ValueError(f"cannot bracket frozen long gap for {ticker}")

        diagnostics.append(
            {
                "eventNumber": row["eventNumber"],
                "issuerCik": row["issuerCik"],
                "ticker": ticker,
                "horizon": int(row["horizon"]),
                "entrySession": row["entrySession"],
                "targetExitSession": row["targetExitSession"],
                "maxInternalGapSessions": gap,
                "previousObservedSession": sessions[previous_index],
                "firstMissingSession": sessions[previous_index + 1],
                "lastMissingSession": sessions[next_index - 1],
                "nextObservedSession": sessions[next_index],
                "barResumesAfterGap": True,
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "gap-diagnostics.csv"
    fieldnames = list(diagnostics[0])
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(diagnostics)

    unique_events = {row["eventNumber"] for row in diagnostics}
    unique_tickers = {row["ticker"] for row in diagnostics}
    summary: dict[str, Any] = {
        "schemaVersion": 1,
        "status": "PHASE1_FROZEN_LONG_GAP_DIAGNOSTICS_COMPLETE",
        "sourceLedgerState": "UNRESOLVED_CONTINUITY",
        "sourceResolution": "long_internal_gap",
        "gapThresholdSessions": FROZEN_GAP_THRESHOLD,
        "gapEventHorizonRows": len(diagnostics),
        "gapUniqueEvents": len(unique_events),
        "gapUniqueTickers": len(unique_tickers),
        "maxGapSessions": max(int(row["maxInternalGapSessions"]) for row in diagnostics),
        "allGapsBracketedByObservedBars": all(row["barResumesAfterGap"] for row in diagnostics),
        "marketFieldsRead": [
            "date",
            "ticker",
            "volume",
            "trade_count",
            "terminal_candidate",
        ],
        "priceFieldsRead": [],
        "performanceRead": False,
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                ledger_path=args.ledger,
                market_root=args.market_root,
                output_dir=args.output_dir,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
