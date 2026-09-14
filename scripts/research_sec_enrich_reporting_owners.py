"""Research-only enrichment of SEC candidate accessions with reporting-owner CIKs.

The SEC quarterly insider data sets expose reporting-owner CIKs in the
REPORTINGOWNER table. Historical accession-archive lookup needs those CIKs
because the EDGAR archive directory is not reliably the issuer CIK or the
accession-number prefix. This helper enriches only the requested historical
quarter and fails closed if any selected candidate lacks reporting-owner
metadata.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import polars as pl


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def enrich(*, candidate_path: Path, history_root: Path, year: int, quarter: int) -> dict[str, Any]:
    if year < 2006 or quarter not in {1, 2, 3, 4}:
        raise ValueError("invalid historical quarter")
    if not candidate_path.exists():
        raise FileNotFoundError(candidate_path)

    reporting_paths = list(
        history_root.rglob(f"year={year}/quarter={quarter}/REPORTINGOWNER.parquet")
    )
    if len(reporting_paths) != 1:
        raise ValueError(
            f"expected one REPORTINGOWNER.parquet for {year}Q{quarter}, found {len(reporting_paths)}"
        )

    candidates = _read_jsonl(candidate_path)
    selected = {
        str(row["accession"])
        for row in candidates
        if int(row["sourceYear"]) == year and int(row["sourceQuarter"]) == quarter
    }
    if not selected:
        raise ValueError("selected historical candidate quarter is empty")

    reporting = pl.read_parquet(reporting_paths[0]).select(
        "ACCESSION_NUMBER", "RPTOWNERCIK"
    )
    owner_ciks: dict[str, set[str]] = {}
    for item in reporting.iter_rows(named=True):
        accession = str(item["ACCESSION_NUMBER"])
        if accession not in selected:
            continue
        cik = str(item["RPTOWNERCIK"]).strip()
        if not cik.isdigit() or len(cik) > 10:
            raise ValueError(f"invalid reporting-owner CIK {cik!r} for {accession}")
        owner_ciks.setdefault(accession, set()).add(cik.zfill(10))

    missing = sorted(selected - owner_ciks.keys())
    if missing:
        preview = ", ".join(missing[:10])
        raise ValueError(
            f"{len(missing)} selected candidates lack reporting-owner CIK evidence: {preview}"
        )

    enriched = 0
    for row in candidates:
        accession = str(row["accession"])
        if accession not in selected:
            continue
        row["reportingOwnerCiks"] = sorted(owner_ciks[accession])
        enriched += 1

    temporary = candidate_path.with_suffix(candidate_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in candidates:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, candidate_path)

    summary = {
        "schemaVersion": "1.0.0",
        "source": "verified-sec-quarterly-bulk-reportingowner",
        "year": year,
        "quarter": quarter,
        "selectedCandidateAccessions": len(selected),
        "enrichedCandidateAccessions": enriched,
        "distinctReportingOwnerCiks": len(
            {cik for values in owner_ciks.values() for cik in values}
        ),
        "missingReportingOwnerAccessions": 0,
        "oosOpened": False,
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-path", type=Path, required=True)
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--quarter", type=int, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            enrich(
                candidate_path=args.candidate_path,
                history_root=args.history_root,
                year=args.year,
                quarter=args.quarter,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
