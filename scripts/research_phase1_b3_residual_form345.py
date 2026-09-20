"""Bounded all-Form345 issuer/ticker corroboration for residual B3 continuity."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl

SEALED_YEAR = 2023


def _bulk_date(value: str) -> date:
    return date.fromisoformat(
        pl.Series([value]).str.to_date("%d-%b-%Y", strict=True)[0].isoformat()
    )


def _submissions(
    history_root: Path,
    wanted_issuers: set[str],
) -> dict[str, list[dict[str, str]]]:
    by_issuer: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for path in sorted(history_root.rglob("SUBMISSION.parquet")):
        frame = pl.read_parquet(
            path,
            columns=[
                "ACCESSION_NUMBER",
                "FILING_DATE",
                "DOCUMENT_TYPE",
                "ISSUERCIK",
                "ISSUERNAME",
                "ISSUERTRADINGSYMBOL",
            ],
        )
        frame = frame.with_columns(
            pl.col("ISSUERCIK").cast(pl.String).str.zfill(10).alias("CIK"),
            pl.col("ISSUERTRADINGSYMBOL").cast(pl.String).str.to_uppercase().str.strip_chars().alias("TICKER"),
            pl.col("FILING_DATE").cast(pl.String).alias("FILED"),
            pl.col("DOCUMENT_TYPE").cast(pl.String).str.to_uppercase().alias("FORM"),
        ).filter(
            pl.col("CIK").is_in(sorted(wanted_issuers))
            & pl.col("FORM").is_in(["3", "3/A", "4", "4/A", "5", "5/A"])
        )
        for row in frame.iter_rows(named=True):
            filed = _bulk_date(str(row["FILED"]))
            if filed.year >= SEALED_YEAR:
                raise ValueError("sealed OOS boundary violated by SEC bulk submission")
            accession = str(row["ACCESSION_NUMBER"] or "")
            if not accession:
                raise ValueError("bulk SEC submission missing accession")
            cik = str(row["CIK"])
            observation = {
                "issuerCik": cik,
                "ticker": str(row["TICKER"] or ""),
                "filingDate": filed.isoformat(),
                "form": str(row["FORM"]),
                "accession": accession,
                "issuerName": str(row["ISSUERNAME"] or ""),
            }
            prior = by_issuer[cik].get(accession)
            if prior is not None and prior != observation:
                raise ValueError("conflicting bulk identity within one accession")
            by_issuer[cik][accession] = observation

    return {
        cik: sorted(values.values(), key=lambda r: (r["filingDate"], r["accession"]))
        for cik, values in by_issuer.items()
    }


def _nearest(
    rows: list[dict[str, str]],
    pivot: str,
) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    pivot_date = date.fromisoformat(pivot)
    before = None
    after = None
    for row in rows:
        filed = date.fromisoformat(row["filingDate"])
        if filed <= pivot_date:
            before = row
        elif after is None:
            after = row
            break
    return before, after


def _status(
    expected: str,
    before: dict[str, str] | None,
    after: dict[str, str] | None,
) -> str:
    if before is None and after is None:
        return "NO_BOUNDED_FORM345_OBSERVATION"
    if before is None:
        return (
            "AFTER_ONLY_EXPECTED_TICKER"
            if after and after["ticker"] == expected
            else "AFTER_ONLY_DIFFERENT_TICKER"
        )
    if after is None:
        return (
            "BEFORE_ONLY_EXPECTED_TICKER"
            if before["ticker"] == expected
            else "BEFORE_ONLY_DIFFERENT_TICKER"
        )
    bm = before["ticker"] == expected
    am = after["ticker"] == expected
    if bm and am:
        return "EXPECTED_TICKER_BOTH_SIDES"
    if bm and not am:
        return "TICKER_CHANGED_AFTER_PIVOT"
    if not bm and am:
        return "EXPECTED_TICKER_ONLY_AFTER"
    if before["ticker"] == after["ticker"]:
        return "SAME_DIFFERENT_TICKER_BOTH_SIDES"
    return "DIFFERENT_TICKERS_ACROSS_PIVOT"


def run(
    *,
    source_path: Path,
    history_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    if len(source) != 162:
        raise ValueError("unexpected residual source row count")
    wanted = {str(row["issuerCik"]) for row in source}
    submissions = _submissions(history_root, wanted)

    output: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    upgraded = 0
    for row in source:
        before, after = _nearest(
            submissions.get(str(row["issuerCik"]), []),
            str(row["pivotDate"]),
        )
        status = _status(str(row["ticker"]).upper(), before, after)
        counts[status] += 1
        if (
            row["corroborationStatus"] == "BEFORE_ONLY_EXPECTED_TICKER"
            and status == "EXPECTED_TICKER_BOTH_SIDES"
        ):
            upgraded += 1
        output.append(
            {
                **row,
                "form345BeforeObservation": before,
                "form345AfterObservation": after,
                "form345CorroborationStatus": status,
                "form345DatePrecision": "FILING_DATE_ONLY",
                "continuityStateChanged": False,
                "finalResolutionAllowedFromThisStage": False,
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "b3-residual-form345-corroboration.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {
        "schemaVersion": "1.0.0",
        "status": "B3_RESIDUAL_FORM345_CORROBORATION_COMPLETE",
        "source": "SEC_QUARTERLY_BULK_SUBMISSION_2016_2022",
        "datePrecision": "FILING_DATE_ONLY",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "transactionFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceRows": len(source),
        "targetIssuers": len(wanted),
        "issuersWithSubmissionEvidence": len(submissions),
        "statusCounts": dict(sorted(counts.items())),
        "psOneSidedUpgradedToBothSides": upgraded,
        "continuityStatesChanged": 0,
        "finalResolutionContractCreated": False,
        "correctedPerformanceOpened": False,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(
        source_path=args.source,
        history_root=args.history_root,
        output_dir=args.output_dir,
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
