"""Build a compact PIT-safe owner/month history for CMP classification.

Research only.  Input is the official SEC quarterly bulk staging layer, which retains
all source tables.  We use non-derivative open-market P/A and S/D transactions from
non-amendment Forms 3/4/5 and join reporting-owner CIKs only to establish whether an
owner traded in a calendar month.  The output never contains owner names or addresses.

The SEC bulk layer exposes FILING_DATE rather than exact acceptance time.  That is
sufficient for the Cohen-Malloy-Pomorski annual classifier used here because labels
are frozen at the start of a calendar year and only filings with FILING_DATE strictly
before January 1 enter that year's history.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import polars as pl

from insider_turning_engine.ingestion.sec.history import partition_path, validate_partition

OPEN_MARKET_CODES = frozenset({("P", "A"), ("S", "D")})
ORIGINAL_FORMS = frozenset({"3", "4", "5"})
SEALED_YEAR = 2023


def _valid_cik_expr(column: str) -> pl.Expr:
    return pl.col(column).is_not_null() & pl.col(column).str.contains(r"^\d{1,10}$")


def extract_year(staging_root: Path, year: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if year >= SEALED_YEAR:
        raise ValueError("sealed OOS boundary violated")

    frames: list[pl.DataFrame] = []
    diag: dict[str, int] = defaultdict(int)
    for quarter in range(1, 5):
        root = partition_path(staging_root, year, quarter)
        tables = validate_partition(root, year, quarter)
        submission = tables["SUBMISSION"].select(
            "ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE"
        )
        owners = tables["REPORTINGOWNER"].select(
            "ACCESSION_NUMBER", "RPTOWNERCIK"
        ).unique()
        trans = tables["NONDERIV_TRANS"].select(
            "ACCESSION_NUMBER",
            "NONDERIV_TRANS_SK",
            "TRANS_DATE",
            "TRANS_CODE",
            "TRANS_ACQUIRED_DISP_CD",
        )
        diag["submissionRows"] += submission.height
        diag["reportingOwnerRows"] += owners.height
        diag["nonDerivativeTransactionRows"] += trans.height

        joined = (
            trans.join(submission, on="ACCESSION_NUMBER", how="inner", validate="m:1")
            .filter(pl.col("DOCUMENT_TYPE").is_in(sorted(ORIGINAL_FORMS)))
            .filter(
                ((pl.col("TRANS_CODE") == "P") & (pl.col("TRANS_ACQUIRED_DISP_CD") == "A"))
                | ((pl.col("TRANS_CODE") == "S") & (pl.col("TRANS_ACQUIRED_DISP_CD") == "D"))
            )
            .join(owners, on="ACCESSION_NUMBER", how="inner", validate="m:m")
            .with_columns(
                pl.col("FILING_DATE").str.to_date("%d-%b-%Y", strict=True).alias("filed"),
                pl.col("TRANS_DATE").str.to_date("%d-%b-%Y", strict=True).alias("traded"),
            )
            .filter(_valid_cik_expr("RPTOWNERCIK"))
            .with_columns(pl.col("RPTOWNERCIK").str.zfill(10).alias("ownerCik"))
        )
        diag["eligibleOwnerTransactionRows"] += joined.height
        frames.append(
            joined.select(
                "ownerCik",
                "ACCESSION_NUMBER",
                "NONDERIV_TRANS_SK",
                "TRANS_CODE",
                "filed",
                "traded",
            )
        )

    if not frames:
        return [], dict(diag)

    all_rows = pl.concat(frames)
    if all_rows.filter(pl.col("traded").dt.year() != year).height:
        # Quarterly archives can contain corrections or late-reported transactions from
        # earlier trade years.  Keep them: CMP uses transaction year, not archive year.
        diag["crossYearTradeRows"] = all_rows.filter(pl.col("traded").dt.year() != year).height

    grouped = (
        all_rows.with_columns(
            pl.col("traded").dt.year().alias("tradeYear"),
            pl.col("traded").dt.month().alias("tradeMonth"),
        )
        .group_by("ownerCik", "tradeYear", "tradeMonth")
        .agg(
            pl.col("filed").min().alias("firstFiledDate"),
            pl.col("ACCESSION_NUMBER").n_unique().alias("distinctAccessions"),
            pl.len().alias("ownerTransactionRows"),
            pl.col("TRANS_CODE").filter(pl.col("TRANS_CODE") == "P").len().alias("purchaseRows"),
            pl.col("TRANS_CODE").filter(pl.col("TRANS_CODE") == "S").len().alias("saleRows"),
        )
        .sort("ownerCik", "tradeYear", "tradeMonth")
    )

    result = [
        {
            "ownerCik": str(row["ownerCik"]),
            "tradeYear": int(row["tradeYear"]),
            "tradeMonth": int(row["tradeMonth"]),
            "firstFiledDate": row["firstFiledDate"].isoformat(),
            "distinctAccessions": int(row["distinctAccessions"]),
            "ownerTransactionRows": int(row["ownerTransactionRows"]),
            "purchaseRows": int(row["purchaseRows"]),
            "saleRows": int(row["saleRows"]),
        }
        for row in grouped.iter_rows(named=True)
    ]
    diag["ownerMonthRows"] = len(result)
    diag["distinctOwners"] = len({row["ownerCik"] for row in result})
    return result, dict(diag)


def run(*, staging_root: Path, start_year: int, end_year: int, output: Path) -> dict[str, Any]:
    if start_year > end_year or start_year < 2006 or end_year >= SEALED_YEAR:
        raise ValueError("invalid or sealed SEC history range")

    output.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    yearly: dict[str, Any] = {}
    for year in range(start_year, end_year + 1):
        year_rows, diag = extract_year(staging_root, year)
        rows.extend(year_rows)
        yearly[str(year)] = diag

    fieldnames = [
        "ownerCik",
        "tradeYear",
        "tradeMonth",
        "firstFiledDate",
        "distinctAccessions",
        "ownerTransactionRows",
        "purchaseRows",
        "saleRows",
    ]
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "schemaVersion": "1.0.0",
        "dataset": "CMP open-market P/S owner-month history",
        "period": f"{start_year}-{end_year}",
        "definition": "non-derivative original-form P/A and S/D; owner CIK x transaction year x month",
        "availabilityRule": "first SEC FILING_DATE retained; annual classifier uses only dates < Jan 1",
        "amendmentsIncluded": False,
        "ownerMonthRows": len(rows),
        "distinctOwners": len({row["ownerCik"] for row in rows}),
        "yearly": yearly,
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    output.with_suffix(".summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-root", type=Path, required=True)
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(
        staging_root=args.staging_root,
        start_year=args.start_year,
        end_year=args.end_year,
        output=args.output,
    )


if __name__ == "__main__":
    main()
