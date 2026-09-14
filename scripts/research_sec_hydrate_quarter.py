"""Research-only quarter runner for historical SEC ownership PIT hydration.

This orchestration layer deliberately stays outside the production package. It
runs the already-audited ``research_sec_hydrate`` logic in bounded shards,
validates every shard fail-closed, then emits one deterministic quarter package
with hashes and quality statistics. It can also finalize an already-completed
set of shard artifacts (used for the 2016 Q1 reference run) without re-fetching
SEC data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from research_sec_hydrate import _load_candidates, hydrate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        raise ValueError(f"missing required shard file: {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _positive_price(value: object) -> bool:
    if value in (None, ""):
        return False
    try:
        return Decimal(str(value)) > 0
    except (InvalidOperation, ValueError):
        return False


def _validate_shard(summary: dict[str, Any], expected_total: int) -> None:
    selected = int(summary["selectedOriginalBuyFilings"])
    if selected <= 0:
        raise ValueError("empty hydration shard")
    if int(summary["eligibleOriginalBuyFilingsInQuarter"]) != expected_total:
        raise ValueError("shard eligible-quarter count disagrees with candidate universe")
    if int(summary["matchedInDailyIndex"]) != selected:
        raise ValueError("daily-index discovery is incomplete")
    if int(summary["hydratedAndParsedFilings"]) != selected:
        raise ValueError("hydration/parser coverage is incomplete")
    if int(summary["failureCount"]) != 0:
        raise ValueError("shard contains failures")
    if summary.get("allCanonicalKnowledgeEqualAccepted") is not True:
        raise ValueError("historical PIT clock gate failed")
    if summary.get("oosOpened") is not False:
        raise ValueError("OOS boundary was opened unexpectedly")
    if summary.get("signalReady") is not False:
        raise ValueError("research hydration must never mark signalReady")


def _find_existing_shards(root: Path) -> list[Path]:
    summaries = sorted(root.rglob("summary.json"))
    shard_dirs = [item.parent for item in summaries]
    if not shard_dirs:
        raise ValueError(f"no shard summaries found below {root}")
    return shard_dirs


def _finalize(
    *,
    shard_dirs: list[Path],
    output: Path,
    candidate_path: Path,
    year: int,
    quarter: int,
    candidate_run_id: str,
) -> dict[str, Any]:
    candidates = _load_candidates(candidate_path, year, quarter)
    expected_total = len(candidates)
    if expected_total == 0:
        raise ValueError("quarter has no eligible original buy filings")

    shard_payloads: list[tuple[dict[str, Any], Path]] = []
    for directory in shard_dirs:
        summary_path = directory / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if int(summary["year"]) != year or int(summary["quarter"]) != quarter:
            continue
        if str(summary.get("candidateRunId")) != candidate_run_id:
            raise ValueError("candidate run ID differs across shard evidence")
        _validate_shard(summary, expected_total)
        shard_payloads.append((summary, directory))
    if not shard_payloads:
        raise ValueError("no shard evidence matched requested quarter")

    shard_payloads.sort(key=lambda item: int(item[0]["offset"]))
    cursor = 0
    manifests: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    shard_summaries: list[dict[str, Any]] = []
    legacy_filings = 0
    legacy_values = 0

    for summary, directory in shard_payloads:
        offset = int(summary["offset"])
        selected = int(summary["selectedOriginalBuyFilings"])
        if offset != cursor:
            raise ValueError(f"non-contiguous shard coverage: expected offset {cursor}, got {offset}")
        cursor += selected
        shard_summaries.append(summary)
        shard_manifests = _read_jsonl(directory / "raw-manifest.jsonl")
        shard_records = _read_jsonl(directory / "canonical-research.jsonl")
        shard_failures = _read_jsonl(directory / "failures.jsonl")
        if shard_failures:
            raise ValueError("failure rows present despite a passing shard summary")
        if len(shard_manifests) != selected:
            raise ValueError("raw manifest count differs from selected filing count")
        manifests.extend(shard_manifests)
        records.extend(shard_records)
        legacy_filings += int(summary.get("legacyDateTransformFilings", 0))
        legacy_values += int(summary.get("legacyDateTransformValues", 0))

    if cursor != expected_total:
        raise ValueError(f"quarter coverage incomplete: {cursor} of {expected_total}")

    accessions = [str(row["accession"]) for row in manifests]
    if len(accessions) != len(set(accessions)):
        raise ValueError("duplicate accession in merged raw manifests")
    expected_accessions = {str(row["accession"]) for row in candidates}
    if set(accessions) != expected_accessions:
        missing = sorted(expected_accessions - set(accessions))[:10]
        extra = sorted(set(accessions) - expected_accessions)[:10]
        raise ValueError(f"merged accession set mismatch; missing={missing}, extra={extra}")

    transaction_ids = [str(row["transactionId"]) for row in records]
    revision_ids = [str(row["revisionId"]) for row in records]
    exact_row_ids = [
        f"{row['source']['accessionNumber']}::{row['source']['sourceRowKey']}" for row in records
    ]
    if len(transaction_ids) != len(set(transaction_ids)):
        raise ValueError("duplicate canonical transactionId in quarter")
    if len(revision_ids) != len(set(revision_ids)):
        raise ValueError("duplicate canonical revisionId in quarter")
    if len(exact_row_ids) != len(set(exact_row_ids)):
        raise ValueError("duplicate accession/sourceRowKey in quarter")
    if not all(
        row["timestamps"]["knowledgeAt"] == row["timestamps"]["acceptedAt"]
        for row in records
    ):
        raise ValueError("merged quarter violates knowledge_at == accepted_at")

    purchases = [
        row
        for row in records
        if row.get("transaction", {}).get("economicClassification") == "OPEN_MARKET_PURCHASE"
    ]
    ticker_present = sum(bool(row.get("issuer", {}).get("ticker")) for row in purchases)
    missing_price = sum(
        not _positive_price(row.get("transaction", {}).get("pricePerShare")) for row in purchases
    )
    unresolved_ticker_ciks = sorted(
        {
            str(row.get("issuer", {}).get("cik"))
            for row in purchases
            if not row.get("issuer", {}).get("ticker")
        }
    )

    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "raw-manifest.jsonl"
    canonical_path = output / "canonical-research.jsonl"
    failure_path = output / "failures.jsonl"
    _write_jsonl(manifest_path, sorted(manifests, key=lambda row: row["accession"]))
    _write_jsonl(
        canonical_path,
        sorted(
            records,
            key=lambda row: (
                row["source"]["accessionNumber"],
                int(row["source"]["rowSequence"]),
                row["transactionId"],
            ),
        ),
    )
    failure_path.write_text("", encoding="utf-8")

    summary: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "source": "sec-historical-pit-quarter-research",
        "year": year,
        "quarter": quarter,
        "candidateRunId": candidate_run_id,
        "candidateFileHash": _sha256(candidate_path),
        "eligibleOriginalBuyFilings": expected_total,
        "hydratedOriginalBuyFilings": len(manifests),
        "canonicalRecordCount": len(records),
        "openMarketPurchaseRecordCount": len(purchases),
        "uniqueIssuerCiks": len({row["issuer"]["cik"] for row in records}),
        "uniqueReportingOwnerCiks": len({row["reportingOwner"]["cik"] for row in records}),
        "purchaseTickerCoverage": (
            round(ticker_present / len(purchases), 6) if purchases else None
        ),
        "purchaseRowsMissingPositivePrice": missing_price,
        "unresolvedPurchaseTickerIssuerCiks": unresolved_ticker_ciks,
        "legacyDateTransformFilings": legacy_filings,
        "legacyDateTransformValues": legacy_values,
        "shardCount": len(shard_summaries),
        "shards": [
            {
                "offset": int(row["offset"]),
                "selected": int(row["selectedOriginalBuyFilings"]),
                "canonicalRecords": int(row["canonicalRecordCount"]),
                "purchaseRecords": int(row["openMarketPurchaseRecordCount"]),
            }
            for row in shard_summaries
        ],
        "qualityGates": {
            "completeAccessionCoverage": True,
            "zeroFailures": True,
            "uniqueTransactionIds": True,
            "uniqueRevisionIds": True,
            "uniqueExactSecRows": True,
            "knowledgeEqualsAccepted": True,
            "oosOpened": False,
            "amendmentsReconciled": False,
            "canonicalReady": False,
            "signalReady": False,
        },
        "amendmentPolicy": "original forms only; 4/A and 5/A remain a separate PIT enrichment gate",
    }
    summary_path = output / "quarter-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    checksums = {
        "raw-manifest.jsonl": _sha256(manifest_path),
        "canonical-research.jsonl": _sha256(canonical_path),
        "failures.jsonl": _sha256(failure_path),
        "quarter-summary.json": _sha256(summary_path),
    }
    (output / "checksums.json").write_text(
        json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--quarter", type=int, required=True)
    parser.add_argument("--candidate-run-id", required=True)
    parser.add_argument("--shard-size", type=int, default=500)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--existing-shards-root", type=Path)
    args = parser.parse_args()

    if not 2006 <= args.year <= 2022:
        raise SystemExit("research quarter runner is deliberately bounded to pre-OOS years <= 2022")
    if args.quarter not in {1, 2, 3, 4}:
        raise SystemExit("quarter must be 1..4")
    if not 1 <= args.shard_size <= 1000:
        raise SystemExit("shard-size must be 1..1000")
    if not 1 <= args.workers <= 6:
        raise SystemExit("workers must be 1..6")

    candidates = _load_candidates(args.candidate_path, args.year, args.quarter)
    if not candidates:
        raise SystemExit("no eligible original buy candidates for requested quarter")

    if args.existing_shards_root is not None:
        shard_dirs = _find_existing_shards(args.existing_shards_root)
    else:
        shard_dirs = []
        shard_root = args.output.parent / f".{args.output.name}-shards"
        shard_root.mkdir(parents=True, exist_ok=True)
        user_agent = os.environ.get("SEC_USER_AGENT", "")
        for shard_index, offset in enumerate(range(0, len(candidates), args.shard_size)):
            limit = min(args.shard_size, len(candidates) - offset)
            shard_output = shard_root / f"shard-{shard_index:03d}"
            summary = hydrate(
                candidate_path=args.candidate_path,
                output=shard_output,
                year=args.year,
                quarter=args.quarter,
                offset=offset,
                limit=limit,
                workers=args.workers,
                user_agent=user_agent,
                candidate_run_id=args.candidate_run_id,
            )
            _validate_shard(summary, len(candidates))
            shard_dirs.append(shard_output)

    summary = _finalize(
        shard_dirs=shard_dirs,
        output=args.output,
        candidate_path=args.candidate_path,
        year=args.year,
        quarter=args.quarter,
        candidate_run_id=args.candidate_run_id,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
