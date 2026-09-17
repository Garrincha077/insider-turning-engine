"""Build the bounded CMP history view used by Phase-1 B1/B4.

Research only. The frozen yearly CMP release intentionally preserves the SEC bulk
source, including cross-year transaction dates. A very small number of historical
SEC rows contain impossible future transaction dates (for example, a 2013 filing
with a 2023 or 2031 transaction year). Those source anomalies must not be allowed
to create an opportunistic/routine history event.

This script derives a reproducible analysis view without modifying the frozen
source release:

* only the predeclared B1 classifier history years 2013-2019 are retained;
* a transaction month later than its first filing month is excluded as impossible;
* any filing date in the sealed 2023+ period is a hard failure, not a filter;
* output columns are unchanged so the canonical B1 loader consumes the view
  without any special-case research logic.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

HISTORY_START_YEAR = 2013
HISTORY_END_YEAR = 2019
SEALED_YEAR = 2023
REQUIRED_FIELDS = (
    "ownerCik",
    "tradeYear",
    "tradeMonth",
    "firstFiledDate",
    "distinctAccessions",
    "ownerTransactionRows",
    "purchaseRows",
    "saleRows",
)


def _validate_row(row: dict[str, str]) -> tuple[int, int, date]:
    owner = str(row.get("ownerCik", "")).strip()
    if not owner.isdigit() or len(owner) != 10:
        raise ValueError("invalid owner CIK in CMP history")

    trade_year = int(row["tradeYear"])
    trade_month = int(row["tradeMonth"])
    if not 1 <= trade_month <= 12:
        raise ValueError("invalid trade month in CMP history")

    filed = date.fromisoformat(row["firstFiledDate"])
    if filed.year >= SEALED_YEAR:
        raise ValueError("sealed OOS filing date found in CMP history")
    return trade_year, trade_month, filed


def _decision(trade_year: int, trade_month: int, filed: date) -> str:
    if not HISTORY_START_YEAR <= trade_year <= HISTORY_END_YEAR:
        return "OUTSIDE_PREDECLARED_CLASSIFIER_HISTORY"
    if (trade_year, trade_month) > (filed.year, filed.month):
        return "IMPOSSIBLE_FUTURE_TRADE_MONTH"
    return "KEEP"


def run(*, source_root: Path, output_root: Path) -> dict[str, Any]:
    paths = sorted(source_root.glob("cmp-owner-month-20??.csv"))
    if not paths:
        raise ValueError("no frozen CMP yearly CSVs found")

    output_root.mkdir(parents=True, exist_ok=True)
    totals: Counter[str] = Counter()
    yearly: dict[str, dict[str, int]] = {}

    for source in paths:
        year_counts: Counter[str] = Counter()
        target = output_root / source.name
        with source.open(encoding="utf-8", newline="") as inp:
            reader = csv.DictReader(inp)
            if tuple(reader.fieldnames or ()) != REQUIRED_FIELDS:
                raise ValueError(f"unexpected CMP schema: {source}")
            rows = list(reader)

        with target.open("w", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=list(REQUIRED_FIELDS))
            writer.writeheader()
            for row in rows:
                trade_year, trade_month, filed = _validate_row(row)
                decision = _decision(trade_year, trade_month, filed)
                year_counts[decision] += 1
                totals[decision] += 1
                if decision == "KEEP":
                    writer.writerow(row)

        yearly[source.name] = dict(sorted(year_counts.items()))

    summary: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "dataset": "Bounded CMP owner-month analysis view",
        "source": "frozen research-cmp-history-v1 yearly CSVs",
        "historyYears": [HISTORY_START_YEAR, HISTORY_END_YEAR],
        "futureTradeMonthRule": "exclude trade year/month later than first filed year/month",
        "sealedFilingYear": SEALED_YEAR,
        "yearly": yearly,
        "totals": dict(sorted(totals.items())),
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    (output_root / "window-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    run(source_root=args.source_root, output_root=args.output_root)


if __name__ == "__main__":
    main()
