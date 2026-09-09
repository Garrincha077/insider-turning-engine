"""Resumable bulk history inventory, deliberately separate from canonical signals.

Quarterly TSVs have filing dates, not proven acceptance timestamps or amendment
predecessors. These artifacts are acquisition/enrichment inputs, never a score or
backtest-ready canonical history. Owner addresses never enter the public summary.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from .historical import (
    MIN_YEAR,
    _write_json,
    download_quarter,
    fetch_quarter_catalog,
    sha256_file,
    stage_quarter,
    validate_quarter,
)

TABLES = frozenset({
    "SUBMISSION", "REPORTINGOWNER", "NONDERIV_TRANS", "DERIV_TRANS",
    "NONDERIV_HOLDING", "DERIV_HOLDING", "FOOTNOTES", "OWNER_SIGNATURE",
})


def quarter_of(day: date) -> tuple[int, int]:
    return day.year, (day.month - 1) // 3 + 1


def quarter_range(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    validate_quarter(*start)
    validate_quarter(*end)
    if start > end:
        raise ValueError("start quarter is after end quarter")
    return [(y, q) for y in range(start[0], end[0] + 1) for q in range(1, 5)
            if start <= (y, q) <= end]


def last_completed_quarter(today: date) -> tuple[int, int]:
    year, quarter = quarter_of(today)
    return (year - 1, 4) if quarter == 1 else (year, quarter - 1)


def partition_path(root: Path, year: int, quarter: int) -> Path:
    validate_quarter(year, quarter)
    return root / f"year={year}" / f"quarter={quarter}"


def validate_partition(
    root: Path, year: int, quarter: int, *, archive_sha256: str | None = None,
) -> dict[str, pl.DataFrame]:
    """Verify the complete table set, hashes, counts, keys and parent joins."""
    manifest = json.loads((root / "manifest.json").read_text("utf-8"))
    if (manifest.get("schema_version"), manifest.get("source"),
        manifest.get("year"), manifest.get("quarter")) != ("1.0", "sec", year, quarter):
        raise ValueError("incompatible SEC partition manifest")
    if archive_sha256 is not None and manifest.get("archive_sha256") != archive_sha256:
        raise ValueError("staged archive checksum mismatch")
    if manifest.get("quarantined_rows") != 0:
        raise ValueError("SEC partition contains quarantined rows")
    tables: dict[str, pl.DataFrame] = {}
    for entry in manifest["tables"]:
        name = entry["name"]
        if name not in TABLES or name in tables or entry["path"] != f"{name}.parquet":
            raise ValueError("unexpected or duplicate SEC table path")
        path = root / entry["path"]
        if path.is_symlink() or sha256_file(path) != entry["sha256"]:
            raise ValueError("SEC table checksum mismatch")
        frame = pl.read_parquet(path)
        if frame.height != entry["rows"]:
            raise ValueError("SEC table row count mismatch")
        tables[name] = frame
    if set(tables) != TABLES:
        raise ValueError("incomplete SEC table set")
    rows = sum(frame.height for frame in tables.values())
    if (rows <= 0 or rows != manifest.get("parsed_rows")
        or rows != manifest.get("total_rows") or manifest.get("parse_success_rate") != 1.0):
        raise ValueError("SEC partition counts are inconsistent")
    parents = tables["SUBMISSION"]
    for name, key in (("SUBMISSION", "ACCESSION_NUMBER"),
                      ("NONDERIV_TRANS", "NONDERIV_TRANS_SK"),
                      ("DERIV_TRANS", "DERIV_TRANS_SK")):
        frame = tables[name]
        keys = list(dict.fromkeys(["ACCESSION_NUMBER", key]))
        if any(k not in frame.columns for k in keys):
            raise ValueError(f"missing {name} key columns")
        if frame.select(keys).is_duplicated().any() or frame.select(
            pl.any_horizontal([pl.col(k).is_null() | (pl.col(k) == "") for k in keys]).any()
        ).item():
            raise ValueError(f"invalid or duplicate {name} keys")
    for name, frame in tables.items():
        if "ACCESSION_NUMBER" not in frame.columns:
            raise ValueError(f"missing {name} accession column")
        if frame.join(parents.select("ACCESSION_NUMBER"), on="ACCESSION_NUMBER", how="anti").height:
            raise ValueError(f"orphan SEC rows in {name}")
    return tables


def backfill_history(
    *, cache_dir: Path, staging_dir: Path, user_agent: str,
    start: tuple[int, int] = (MIN_YEAR, 1), end: tuple[int, int] | None = None,
    today: date | None = None, catalog: Mapping[tuple[int, int], str] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Sequential, restartable ingestion; never advance the incremental SEC cursor."""
    today = today or datetime.now(UTC).date()
    completed = last_completed_quarter(today)
    end = end or completed
    if end > completed:
        raise ValueError("cannot backfill an incomplete quarter")
    periods = quarter_range(start, end)
    catalog = catalog if catalog is not None else fetch_quarter_catalog(user_agent)
    report: dict[str, Any] = {
        "schemaVersion": "1.0.0", "source": "sec-quarterly-bulk",
        "ingestedAt": datetime.now(UTC).isoformat(),
        "runId": "run_sec_history_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f"),
        "canonicalReady": False, "status": "INCOMPLETE", "quarters": [],
    }
    report_path = staging_dir / "history-inventory.json"
    _write_json(report_path, report)
    for year, quarter in periods:
        entry: dict[str, Any] = {"year": year, "quarter": quarter}
        try:
            archive = download_quarter(year, quarter, cache_dir, user_agent, catalog=catalog)
            root = partition_path(staging_dir, year, quarter)
            resumed = False
            try:
                tables = validate_partition(root, year, quarter, archive_sha256=archive.sha256)
                resumed = True
            except (OSError, ValueError, KeyError, TypeError, pl.exceptions.PolarsError):
                stage_quarter(year, quarter, cache_dir, staging_dir, archive_path=archive.path)
                tables = validate_partition(root, year, quarter, archive_sha256=archive.sha256)
            entry.update({
                "status": "STAGED", "archiveUrl": archive.url, "archiveSha256": archive.sha256,
                "manifestSha256": sha256_file(root / "manifest.json"),
                "rows": sum(t.height for t in tables.values()),
                "filings": tables["SUBMISSION"].height,
            })
            if progress:
                progress(f"{year}Q{quarter}: {'verified cache' if resumed else 'staged'}")
        except (OSError, ValueError, RuntimeError, KeyError, TypeError,
                pl.exceptions.PolarsError) as exc:
            # Stable safe reason, no raw row content, recipients or request headers.
            entry.update({"status": "FAILED", "reason": type(exc).__name__})
            if progress:
                progress(f"{year}Q{quarter}: FAILED ({type(exc).__name__})")
        report["quarters"].append(entry)
        _write_json(report_path, report)
    report["status"] = (
        "STAGED" if all(row["status"] == "STAGED" for row in report["quarters"]) else "INCOMPLETE"
    )
    _write_json(report_path, report)
    return report


def activity_inventory(staging_dir: Path, *, as_of: date) -> dict[str, Any]:
    """Conservative 365-day acquisition candidates, NOT the PIT common-stock universe.

    Same-day filings are excluded because the archive lacks intraday availability.
    Unlinked amendments are excluded. No owner join can multiply transaction rows.
    """
    start = as_of - timedelta(days=365)
    expected = quarter_range(quarter_of(start), quarter_of(as_of))
    missing: list[str] = []
    frames: list[pl.DataFrame] = []
    inputs: list[dict[str, Any]] = []
    excluded_amendments = 0
    for year, quarter in expected:
        root = partition_path(staging_dir, year, quarter)
        if not (root / "manifest.json").exists():
            missing.append(f"{year}Q{quarter}")
            continue
        tables = validate_partition(root, year, quarter)
        submission = tables["SUBMISSION"].select(
            "ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE", "ISSUERCIK"
        )
        joined = tables["NONDERIV_TRANS"].select(
            "ACCESSION_NUMBER", "NONDERIV_TRANS_SK", "TRANS_DATE", "TRANS_CODE",
            "TRANS_SHARES", "TRANS_PRICEPERSHARE", "TRANS_ACQUIRED_DISP_CD",
        ).join(submission, on="ACCESSION_NUMBER", validate="m:1")
        frames.append(joined)
        inputs.append({"year": year, "quarter": quarter,
                       "manifestSha256": sha256_file(root / "manifest.json")})
    candidates: list[str] = []
    row_count = 0
    if frames:
        joined = pl.concat(frames).unique()
        if joined.select("ACCESSION_NUMBER", "NONDERIV_TRANS_SK").is_duplicated().any():
            raise ValueError("conflicting cross-quarter transaction rows")
        joined = joined.with_columns(
            pl.col("FILING_DATE").str.to_date("%d-%b-%Y", strict=True).alias("filed"),
            pl.col("TRANS_DATE").str.to_date("%d-%b-%Y", strict=False).alias("traded"),
            pl.col("TRANS_SHARES").cast(pl.Float64, strict=False).alias("shares"),
            pl.col("TRANS_PRICEPERSHARE").cast(pl.Float64, strict=False).alias("price"),
        ).filter(
            (pl.col("filed") < as_of) & pl.col("traded").is_between(start, as_of)
        )
        excluded_amendments = joined.filter(pl.col("DOCUMENT_TYPE").str.ends_with("/A")).height
        eligible = joined.filter(
            pl.col("DOCUMENT_TYPE").is_in(["3", "4", "5"])
            & (((pl.col("TRANS_CODE") == "P") & (pl.col("TRANS_ACQUIRED_DISP_CD") == "A"))
               | ((pl.col("TRANS_CODE") == "S") & (pl.col("TRANS_ACQUIRED_DISP_CD") == "D")))
            & (pl.col("shares") > 0) & pl.col("shares").is_finite()
            & (pl.col("price") > 0) & pl.col("price").is_finite()
        )
        if eligible.filter(~pl.col("ISSUERCIK").str.contains(r"^\d{1,10}$")
                           | pl.col("ISSUERCIK").is_null()).height:
            raise ValueError("invalid issuer CIK in activity candidates")
        candidates = sorted({str(cik).zfill(10) for cik in eligible["ISSUERCIK"].to_list()})
        row_count = eligible.height
    return {
        "schemaVersion": "1.0.0", "source": "sec-quarterly-bulk", "asOf": as_of.isoformat(),
        "windowStart": start.isoformat(), "canonicalReady": False, "eligibleUniverseReady": False,
        "inputs": inputs, "missingQuarters": missing,
        "pricedPSCandidateRows": row_count, "candidateIssuerCiks": candidates,
        "candidateIssuerCount": len(candidates), "excludedAmendmentRows": excluded_amendments,
        "qualityFlags": ["FILING_DATE_ONLY", "ACCEPTANCE_ENRICHMENT_REQUIRED",
                         "AMENDMENT_RESOLUTION_REQUIRED", "PIT_SECURITY_IDENTITY_REQUIRED"]
                        + (["INCOMPLETE_QUARTER_COVERAGE"] if missing else []),
    }
