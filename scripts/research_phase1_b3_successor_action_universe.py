"""Build an identity-only ticker universe for B3 successor action lookup."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

CHANGED = {
    "TICKER_CHANGED_AFTER_PIVOT",
    "DIFFERENT_TICKERS_ACROSS_PIVOT",
    "EXPECTED_TICKER_ONLY_AFTER",
    "SAME_DIFFERENT_TICKER_BOTH_SIDES",
}


def build(*, corroboration_path: Path, output_path: Path) -> dict[str, object]:
    rows = json.loads(corroboration_path.read_text(encoding="utf-8"))
    tickers: dict[str, dict[str, str]] = {}
    source_rows = 0
    for row in rows:
        if row.get("corroborationStatus") not in CHANGED:
            continue
        source_rows += 1
        for ticker in (
            str(row.get("ticker") or "").upper(),
            str((row.get("beforeObservation") or {}).get("ticker") or "").upper(),
            str((row.get("afterObservation") or {}).get("ticker") or "").upper(),
        ):
            if not ticker or ticker in tickers:
                continue
            tickers[ticker] = {
                "ticker": ticker,
                "evaluationSession": str(row["evaluationSession"]),
                "entrySession": str(row["entrySession"]),
            }

    if not tickers:
        raise ValueError("no successor/changed ticker universe")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["ticker", "evaluationSession", "entrySession"],
        )
        writer.writeheader()
        writer.writerows(tickers[key] for key in sorted(tickers))

    return {
        "sourceChangedRows": source_rows,
        "tickerCount": len(tickers),
        "tickers": sorted(tickers),
        "performanceRead": False,
        "oosOpened": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corroboration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(
        corroboration_path=args.corroboration,
        output_path=args.output,
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
