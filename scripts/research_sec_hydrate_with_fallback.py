"""Research-only SEC historical hydration with an accession-archive fallback.

The primary path remains the official EDGAR daily index. If and only if that
path cannot find a verified quarterly-bulk accession within the bounded search
window, this adapter derives the canonical EDGAR complete-submission path from
the accession number and fetches that exact submission. The fallback still
must pass accession-header, issuer-CIK, ownership-XML, exact accepted_at and
PIT-clock validation. Its provenance is explicitly marked as a fallback and is
never represented as daily-index discovery.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from insider_turning_engine.ingestion.sec.daily_index import DailyIndexEntry, SECDailyIndexSource
from insider_turning_engine.ingestion.sec.parser import parse_sec_filing

from research_sec_hydrate import (
    _load_candidates,
    _sha256,
    _write_jsonl,
    hydrate as hydrate_daily_first,
    normalize_legacy_transaction_dates,
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _direct_entry(candidate: dict[str, Any]) -> DailyIndexEntry:
    accession = str(candidate["accession"])
    prefix = accession.split("-", 1)[0]
    if len(prefix) != 10 or not prefix.isdigit():
        raise ValueError("accession filer prefix is invalid")
    compact = accession.replace("-", "")
    form_type = str(candidate["documentType"]).upper()
    filed = candidate["_filed"]
    if not isinstance(filed, date):
        raise ValueError("candidate filing date is not normalized")
    return DailyIndexEntry(
        filer_cik=prefix,
        company_name="RESEARCH_ACCESSION_ARCHIVE_FALLBACK",
        form_type=form_type,
        filing_date=filed,
        submission_path=f"edgar/data/{int(prefix)}/{compact}.txt",
        accession_number=accession,
        index_date=None,
    )


def _fallback_one(
    *,
    candidate: dict[str, Any],
    source: SECDailyIndexSource,
    candidate_run_id: str,
) -> dict[str, Any]:
    accession = str(candidate["accession"])
    try:
        entry = _direct_entry(candidate)
        raw = source.fetch_entry(entry, index_hash="research-accession-archive-fallback")
        if raw.payload is None:
            raise ValueError("complete submission did not yield ownership XML")
        if raw.issuer_cik != str(candidate["issuerCik"]):
            raise ValueError("fallback issuer CIK disagrees with quarterly bulk")

        clean_provenance = {
            key: value
            for key, value in raw.provenance.items()
            if key not in {"discovery", "daily_index_url", "daily_index_hash"}
        }
        clean_provenance.update(
            {
                "discovery": "accession_archive_fallback",
                "fallback_reason": "not_found_in_daily_index_within_10_days",
                "submission_path_derived_from_accession": True,
                "candidate_filing_date": candidate["_filed"].isoformat(),
            }
        )
        raw = replace(raw, provenance=clean_provenance)

        raw_hash = _sha256(raw.payload)
        normalized_payload, legacy_date_transforms = normalize_legacy_transaction_dates(raw.payload)
        normalized_hash = _sha256(normalized_payload)
        run_id = "run_hist_" + hashlib.sha256(accession.encode()).hexdigest()[:24]
        parsed = parse_sec_filing(
            normalized_payload,
            {
                "provider": "sec",
                "provider_record_id": raw.provider_record_id,
                "accession_number": raw.accession_number,
                "form_type": raw.form_type,
                "source_url": raw.source_url,
                "accepted_at": raw.accepted_at,
                "observed_at": raw.accepted_at,
                "recorded_at": raw.retrieved_at,
                "run_id": run_id,
            },
        )
        if parsed.quarantines:
            return {
                "ok": False,
                "accession": accession,
                "stage": "FALLBACK_PARSE",
                "reason": "QUARANTINE",
                "quarantines": [item.model_dump(mode="json") for item in parsed.quarantines],
            }
        records = list(parsed.records)
        if not records:
            raise ValueError("fallback ownership parser emitted no canonical records")

        dumped: list[dict[str, Any]] = []
        purchases = 0
        for record in records:
            if record.timestamps.accepted_at != raw.accepted_at:
                raise ValueError("fallback canonical accepted_at disagrees with raw evidence")
            if record.timestamps.knowledge_at != raw.accepted_at:
                raise ValueError("fallback historical knowledge_at does not equal SEC accepted_at")
            if record.timestamps.recorded_at != raw.retrieved_at:
                raise ValueError("fallback canonical recorded_at lost actual retrieval time")
            item = record.canonical_dump()
            item["researchBackfill"] = {
                "historicalAvailabilityBasis": "SEC_ACCEPTANCE_DATETIME",
                "actualRetrievedAt": raw.retrieved_at.astimezone(UTC).isoformat(),
                "indexDate": None,
                "bulkFilingDate": candidate["_filed"].isoformat(),
                "candidateRunId": candidate_run_id,
                "rawOwnershipXmlHash": raw_hash,
                "normalizedOwnershipXmlHash": normalized_hash,
                "legacyTransactionDateOffsetTransforms": legacy_date_transforms,
                "normalizationPolicy": (
                    "transactionDate YYYY-MM-DD[+-]HH:MM -> YYYY-MM-DD only"
                    if legacy_date_transforms
                    else "none"
                ),
                "discoveryMethod": "ACCESSION_ARCHIVE_FALLBACK",
                "canonicalReady": False,
            }
            dumped.append(item)
            if item.get("transaction", {}).get("economicClassification") == "OPEN_MARKET_PURCHASE":
                purchases += 1

        return {
            "ok": True,
            "accession": accession,
            "manifest": {
                "accession": accession,
                "issuerCik": raw.issuer_cik,
                "formType": raw.form_type,
                "acceptedAt": raw.accepted_at.astimezone(UTC).isoformat(),
                "actualRetrievedAt": raw.retrieved_at.astimezone(UTC).isoformat(),
                "indexDate": None,
                "bulkFilingDate": candidate["_filed"].isoformat(),
                "sourceUrl": raw.source_url,
                "replayLocator": raw.replay_locator,
                "primaryDocument": raw.primary_document,
                "rawOwnershipXmlHash": raw_hash,
                "normalizedOwnershipXmlHash": normalized_hash,
                "legacyTransactionDateOffsetTransforms": legacy_date_transforms,
                "discoveryMethod": "ACCESSION_ARCHIVE_FALLBACK",
                "provenance": dict(raw.provenance),
                "canonicalRecordCount": len(records),
            },
            "records": dumped,
            "purchaseRows": purchases,
            "legacyDateTransforms": legacy_date_transforms,
        }
    except (ET.ParseError, RuntimeError, ValueError, OSError, TypeError) as exc:
        return {
            "ok": False,
            "accession": accession,
            "stage": "ACCESSION_ARCHIVE_FALLBACK",
            "reason": type(exc).__name__,
            "message": str(exc)[:300],
        }


def hydrate(
    *,
    candidate_path: Path,
    output: Path,
    year: int,
    quarter: int,
    offset: int,
    limit: int,
    workers: int,
    user_agent: str,
    candidate_run_id: str,
) -> dict[str, Any]:
    summary = hydrate_daily_first(
        candidate_path=candidate_path,
        output=output,
        year=year,
        quarter=quarter,
        offset=offset,
        limit=limit,
        workers=workers,
        user_agent=user_agent,
        candidate_run_id=candidate_run_id,
    )

    original_failures = _read_jsonl(output / "failures.jsonl")
    summary["fallbackArchiveFilings"] = 0
    summary["discoveredFilings"] = int(summary["hydratedAndParsedFilings"])
    summary["discoveryPolicy"] = "daily index primary; exact accession archive path fallback"
    if not original_failures:
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return summary

    eligible_for_fallback = [
        row
        for row in original_failures
        if row.get("stage") == "DISCOVERY"
        and row.get("reason") == "ACCESSION_NOT_FOUND_WITHIN_10_DAYS"
    ]
    untouched_failures = [row for row in original_failures if row not in eligible_for_fallback]
    if not eligible_for_fallback:
        return summary

    all_candidates = _load_candidates(candidate_path, year, quarter)
    selected = all_candidates[offset : offset + limit]
    by_accession = {str(row["accession"]): row for row in selected}
    targets = []
    for failure in eligible_for_fallback:
        candidate = by_accession.get(str(failure["accession"]))
        if candidate is None:
            untouched_failures.append(
                {
                    "ok": False,
                    "accession": failure["accession"],
                    "stage": "ACCESSION_ARCHIVE_FALLBACK",
                    "reason": "CANDIDATE_NOT_IN_SELECTED_SLICE",
                }
            )
        else:
            targets.append(candidate)

    source = SECDailyIndexSource(user_agent, cache_dir=output / "sec-cache-fallback")
    fallback_results: list[dict[str, Any]] = []
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(
                    _fallback_one,
                    candidate=row,
                    source=source,
                    candidate_run_id=candidate_run_id,
                )
                for row in targets
            ]
            for future in as_completed(futures):
                fallback_results.append(future.result())
    finally:
        source.close()

    fallback_good = sorted(
        (row for row in fallback_results if row["ok"]), key=lambda row: row["accession"]
    )
    fallback_bad = sorted(
        (row for row in fallback_results if not row["ok"]), key=lambda row: row["accession"]
    )
    existing_manifests = _read_jsonl(output / "raw-manifest.jsonl")
    existing_records = _read_jsonl(output / "canonical-research.jsonl")
    manifests = existing_manifests + [row["manifest"] for row in fallback_good]
    records = existing_records + [item for row in fallback_good for item in row["records"]]
    remaining_failures = sorted(
        untouched_failures + fallback_bad, key=lambda row: str(row.get("accession", ""))
    )

    _write_jsonl(output / "raw-manifest.jsonl", sorted(manifests, key=lambda row: row["accession"]))
    _write_jsonl(
        output / "canonical-research.jsonl",
        sorted(
            records,
            key=lambda row: (
                row["source"]["accessionNumber"],
                int(row["source"]["rowSequence"]),
                row["transactionId"],
            ),
        ),
    )
    _write_jsonl(output / "failures.jsonl", remaining_failures)

    fallback_purchase_rows = sum(int(row["purchaseRows"]) for row in fallback_good)
    fallback_legacy_filings = sum(int(row["legacyDateTransforms"]) > 0 for row in fallback_good)
    fallback_legacy_values = sum(int(row["legacyDateTransforms"]) for row in fallback_good)
    summary.update(
        {
            "fallbackArchiveFilings": len(fallback_good),
            "discoveredFilings": len(manifests),
            "hydratedAndParsedFilings": len(manifests),
            "failureCount": len(remaining_failures),
            "canonicalRecordCount": len(records),
            "openMarketPurchaseRecordCount": int(summary["openMarketPurchaseRecordCount"])
            + fallback_purchase_rows,
            "legacyDateTransformFilings": int(summary["legacyDateTransformFilings"])
            + fallback_legacy_filings,
            "legacyDateTransformValues": int(summary["legacyDateTransformValues"])
            + fallback_legacy_values,
            "allCanonicalKnowledgeEqualAccepted": all(
                item["timestamps"]["knowledgeAt"] == item["timestamps"]["acceptedAt"]
                for item in records
            ),
        }
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--quarter", type=int, required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--candidate-run-id", required=True)
    args = parser.parse_args()
    summary = hydrate(
        candidate_path=args.candidate_path,
        output=args.output,
        year=args.year,
        quarter=args.quarter,
        offset=args.offset,
        limit=args.limit,
        workers=args.workers,
        user_agent=os.environ.get("SEC_USER_AGENT", ""),
        candidate_run_id=args.candidate_run_id,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
