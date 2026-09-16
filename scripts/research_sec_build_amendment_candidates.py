"""Build a fail-closed 4/A and 5/A research universe from verified SEC bulk data.

The output is research-only.  It deliberately separates transaction-bearing
amendments (which need exact acceptance-time hydration) from zero-transaction
amendments, and emits a predecessor catalog for deterministic linkage using
SEC DATE_OF_ORIG_SUB plus issuer/reporting-owner identity.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import polars as pl

_ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_AMENDMENT_FORMS = {"4/A", "5/A"}
_ORIGINAL_FORMS = {"4", "5"}


def _date_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _cik(value: object) -> str:
    text = str(value).strip()
    if not text.isdigit() or len(text) > 10:
        raise ValueError(f"invalid CIK {text!r}")
    return text.zfill(10)


def _accession(value: object) -> str:
    text = str(value).strip()
    if not _ACCESSION_RE.fullmatch(text):
        raise ValueError(f"invalid accession {text!r}")
    return text


def _owners(path: Path) -> dict[str, list[str]]:
    frame = pl.read_parquet(path).select("ACCESSION_NUMBER", "RPTOWNERCIK")
    values: dict[str, set[str]] = defaultdict(set)
    for row in frame.iter_rows(named=True):
        values[_accession(row["ACCESSION_NUMBER"])].add(_cik(row["RPTOWNERCIK"]))
    return {key: sorted(items) for key, items in values.items()}


def _transaction_counts(qroot: Path) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    total: dict[str, int] = defaultdict(int)
    buys: dict[str, int] = defaultdict(int)
    sales: dict[str, int] = defaultdict(int)
    for filename in ("NONDERIV_TRANS.parquet", "DERIV_TRANS.parquet"):
        path = qroot / filename
        if not path.exists():
            continue
        frame = pl.read_parquet(path)
        columns = set(frame.columns)
        needed = ["ACCESSION_NUMBER"]
        if "TRANS_CODE" in columns:
            needed.append("TRANS_CODE")
        if "TRANS_ACQUIRED_DISP_CD" in columns:
            needed.append("TRANS_ACQUIRED_DISP_CD")
        for row in frame.select(*needed).iter_rows(named=True):
            accession = _accession(row["ACCESSION_NUMBER"])
            total[accession] += 1
            code = str(row.get("TRANS_CODE") or "").upper()
            ad = str(row.get("TRANS_ACQUIRED_DISP_CD") or "").upper()
            if code == "P" and ad == "A":
                buys[accession] += 1
            elif code == "S" and ad == "D":
                sales[accession] += 1
    return dict(total), dict(buys), dict(sales)


def build(*, history_root: Path, year: int, output: Path) -> dict[str, Any]:
    if not 2006 <= year <= 2022:
        raise ValueError("research amendment builder is bounded to pre-OOS years <= 2022")
    year_dirs = list(history_root.rglob(f"year={year}"))
    if len(year_dirs) != 1:
        raise ValueError(f"expected one year={year} directory, found {len(year_dirs)}")
    year_root = year_dirs[0]

    amendment_rows: list[dict[str, Any]] = []
    predecessor_rows: list[dict[str, Any]] = []
    zero_transaction_amendments: list[dict[str, Any]] = []
    quarter_summaries: list[dict[str, Any]] = []

    for quarter in range(1, 5):
        qroot = year_root / f"quarter={quarter}"
        sub_path = qroot / "SUBMISSION.parquet"
        owner_path = qroot / "REPORTINGOWNER.parquet"
        if not sub_path.exists() or not owner_path.exists():
            raise ValueError(f"missing verified SEC bulk tables for {year}Q{quarter}")

        sub = pl.read_parquet(sub_path).select(
            "ACCESSION_NUMBER",
            "FILING_DATE",
            "DATE_OF_ORIG_SUB",
            "DOCUMENT_TYPE",
            "ISSUERCIK",
        )
        owners = _owners(owner_path)
        total_counts, buy_counts, sale_counts = _transaction_counts(qroot)

        q_amendments = 0
        q_transaction_bearing = 0
        q_zero = 0
        for item in sub.iter_rows(named=True):
            accession = _accession(item["ACCESSION_NUMBER"])
            form = str(item["DOCUMENT_TYPE"]).strip().upper()
            issuer = _cik(item["ISSUERCIK"])
            filing_date = _date_text(item["FILING_DATE"])
            original_date = _date_text(item["DATE_OF_ORIG_SUB"])
            owner_ciks = owners.get(accession, [])
            if not owner_ciks:
                raise ValueError(f"{accession} lacks REPORTINGOWNER evidence")

            base = {
                "accession": accession,
                "issuerCik": issuer,
                "filingDate": filing_date,
                "documentType": form,
                "reportingOwnerCiks": owner_ciks,
                "transactionCount": int(total_counts.get(accession, 0)),
                "buyCount": int(buy_counts.get(accession, 0)),
                "saleCount": int(sale_counts.get(accession, 0)),
                "sourceYear": year,
                "sourceQuarter": quarter,
            }
            if form in _AMENDMENT_FORMS:
                q_amendments += 1
                row = {**base, "originalSubmissionDate": original_date}
                if row["transactionCount"] > 0:
                    amendment_rows.append(row)
                    q_transaction_bearing += 1
                else:
                    zero_transaction_amendments.append(row)
                    q_zero += 1
            elif form in _ORIGINAL_FORMS:
                predecessor_rows.append(base)

        quarter_summaries.append(
            {
                "quarter": quarter,
                "amendmentFilings": q_amendments,
                "transactionBearingAmendments": q_transaction_bearing,
                "zeroTransactionAmendments": q_zero,
            }
        )

    amendment_rows.sort(key=lambda row: (row["filingDate"] or "", row["accession"]))
    predecessor_rows.sort(key=lambda row: (row["filingDate"] or "", row["accession"]))
    zero_transaction_amendments.sort(
        key=lambda row: (row["filingDate"] or "", row["accession"])
    )
    if len({row["accession"] for row in amendment_rows}) != len(amendment_rows):
        raise ValueError("duplicate amendment accession")
    if len({row["accession"] for row in predecessor_rows}) != len(predecessor_rows):
        raise ValueError("duplicate predecessor accession")

    output.mkdir(parents=True, exist_ok=True)
    for filename, rows in (
        ("amendment-candidates.jsonl", amendment_rows),
        ("predecessor-catalog.jsonl", predecessor_rows),
        ("zero-transaction-amendments.jsonl", zero_transaction_amendments),
    ):
        with (output / filename).open("w", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, sort_keys=True) + "\n")

    summary = {
        "schemaVersion": "1.0.0",
        "source": "verified-sec-quarterly-bulk",
        "year": year,
        "transactionBearingAmendmentFilings": len(amendment_rows),
        "zeroTransactionAmendmentFilings": len(zero_transaction_amendments),
        "allAmendmentFilings": len(amendment_rows) + len(zero_transaction_amendments),
        "amendmentsMissingOriginalSubmissionDate": sum(
            row["originalSubmissionDate"] is None for row in amendment_rows
        ),
        "predecessorCatalogFilings": len(predecessor_rows),
        "quarters": quarter_summaries,
        "linkageEvidence": [
            "SUBMISSION.DATE_OF_ORIG_SUB",
            "ISSUERCIK",
            "REPORTINGOWNER.RPTOWNERCIK",
            "exact owner/table/row sequence after hydration",
        ],
        "fuzzyMatchingAllowed": False,
        "oosOpened": False,
        "canonicalReady": False,
        "signalReady": False,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(history_root=args.history_root, year=args.year, output=args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
