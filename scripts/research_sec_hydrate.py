"""Research-only historical SEC ownership hydration.

This script is deliberately outside the production package. It reconstructs
point-in-time ownership observations from verified candidate accessions and the
SEC daily index/complete-submission evidence without enabling scoring, alerts,
or OOS evaluation.

Historical SEC ownership XML occasionally encodes a transaction *date* as
``YYYY-MM-DD-05:00`` (or another numeric UTC offset). The canonical production
parser correctly expects a date, so this research adapter applies one narrow,
audited normalization before parsing: when and only when a ``transactionDate``
``value`` exactly matches ``YYYY-MM-DD[+-]HH:MM``, the offset suffix is removed.
The source payload hash, normalized payload hash, and transform count are kept
in the research provenance. No other XML values are changed intentionally.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from insider_turning_engine.ingestion.sec.daily_index import SECDailyIndexSource
from insider_turning_engine.ingestion.sec.parser import parse_sec_filing

_OFFSET_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})([+-]\d{2}:\d{2})$")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _bulk_date(value: object) -> date:
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unsupported SEC bulk date {text!r}")


def normalize_legacy_transaction_dates(payload: bytes) -> tuple[bytes, int]:
    """Remove numeric timezone suffixes from SEC transaction *date* values only.

    The function is intentionally fail-closed. XML must parse, only
    ``transactionDate/value`` nodes are considered, and the text must match the
    exact ``YYYY-MM-DD[+-]HH:MM`` pattern. If nothing matches, the original bytes
    are returned unchanged so the production parser sees the exact SEC payload.
    """

    root = ET.fromstring(payload)
    changed = 0
    for transaction_date in root.iter():
        if _local(transaction_date.tag) != "transactionDate":
            continue
        for child in transaction_date.iter():
            if _local(child.tag) != "value" or child.text is None:
                continue
            text = child.text.strip()
            match = _OFFSET_DATE_RE.fullmatch(text)
            if match is None:
                continue
            # Validate the date independently before transforming it.
            date.fromisoformat(match.group(1))
            child.text = match.group(1)
            changed += 1
    if changed == 0:
        return payload, 0
    normalized = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return normalized, changed


def _load_candidates(path: Path, year: int, quarter: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        filed = _bulk_date(row["filingDate"])
        if (
            int(row["sourceYear"]) == year
            and int(row["sourceQuarter"]) == quarter
            and int(row["buyCount"]) > 0
            and not str(row["documentType"]).upper().endswith("/A")
        ):
            row["_filed"] = filed
            candidates.append(row)
    candidates.sort(key=lambda row: (row["_filed"], row["accession"]))
    return candidates


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")


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
    if year < 2006 or quarter not in {1, 2, 3, 4}:
        raise ValueError("invalid historical quarter")
    if offset < 0 or limit < 1 or limit > 1000:
        raise ValueError("offset/limit outside research safety bounds")
    if workers < 1 or workers > 6:
        raise ValueError("workers outside SEC research safety bounds")
    if not user_agent.strip():
        raise ValueError("SEC_USER_AGENT is required")

    output.mkdir(parents=True, exist_ok=True)
    candidates = _load_candidates(candidate_path, year, quarter)
    selected = candidates[offset : offset + limit]
    if not selected:
        raise ValueError("selected historical buy slice is empty")
    targets = {str(row["accession"]): row for row in selected}

    started = time.monotonic()
    discovery = SECDailyIndexSource(
        user_agent,
        cache_dir=output / "sec-cache-discovery",
    )
    matches: dict[str, tuple[Any, date, str]] = {}
    try:
        first_day = min(row["_filed"] for row in selected)
        last_day = max(row["_filed"] for row in selected) + timedelta(days=10)
        published: list[date] = []
        cursor = first_day
        while cursor <= last_day:
            end = min(last_day, cursor + timedelta(days=30))
            published.extend(discovery.discover_days(cursor, end))
            cursor = end + timedelta(days=1)
        for index_day in sorted(set(published)):
            entries = discovery.discover_day(index_day)
            index_hash = discovery.last_index_hash
            for entry in entries:
                candidate = targets.get(entry.accession_number)
                if candidate is None:
                    continue
                lag = (index_day - candidate["_filed"]).days
                if not 0 <= lag <= 10:
                    continue
                prior = matches.get(entry.accession_number)
                if prior is None or index_day < prior[1]:
                    matches[entry.accession_number] = (entry, index_day, index_hash)
    finally:
        discovery.close()

    local = threading.local()
    sources: list[SECDailyIndexSource] = []
    sources_lock = threading.Lock()

    def worker_source() -> SECDailyIndexSource:
        source = getattr(local, "source", None)
        if source is None:
            source = SECDailyIndexSource(
                user_agent,
                cache_dir=output / "sec-cache-filings",
            )
            local.source = source
            with sources_lock:
                sources.append(source)
        return source

    def hydrate_one(candidate: dict[str, Any]) -> dict[str, Any]:
        accession = str(candidate["accession"])
        match = matches.get(accession)
        if match is None:
            return {
                "ok": False,
                "accession": accession,
                "stage": "DISCOVERY",
                "reason": "ACCESSION_NOT_FOUND_WITHIN_10_DAYS",
            }
        entry, index_day, index_hash = match
        try:
            raw = worker_source().fetch_entry(entry, index_hash=index_hash)
            if raw.payload is None:
                raise ValueError("complete submission did not yield ownership XML")
            if raw.issuer_cik != str(candidate["issuerCik"]):
                raise ValueError("hydrated issuer CIK disagrees with quarterly bulk")

            raw_hash = _sha256(raw.payload)
            normalized_payload, legacy_date_transforms = normalize_legacy_transaction_dates(
                raw.payload
            )
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
                    # Current canonical schema uses observed_at to compute knowledge_at.
                    # For historical reconstruction, the public SEC acceptance instant is
                    # the evidence-availability clock; actual 2026 retrieval is retained
                    # separately in recorded_at and research provenance.
                    "observed_at": raw.accepted_at,
                    "recorded_at": raw.retrieved_at,
                    "run_id": run_id,
                },
            )
            if parsed.quarantines:
                return {
                    "ok": False,
                    "accession": accession,
                    "stage": "PARSE",
                    "reason": "QUARANTINE",
                    "legacyDateTransformCount": legacy_date_transforms,
                    "quarantines": [q.model_dump(mode="json") for q in parsed.quarantines],
                }
            records = list(parsed.records)
            if not records:
                raise ValueError("ownership parser emitted no canonical records")

            dumped: list[dict[str, Any]] = []
            purchases = 0
            for record in records:
                if record.timestamps.accepted_at != raw.accepted_at:
                    raise ValueError("canonical accepted_at disagrees with raw evidence")
                if record.timestamps.knowledge_at != raw.accepted_at:
                    raise ValueError("historical knowledge_at does not equal SEC accepted_at")
                if record.timestamps.recorded_at != raw.retrieved_at:
                    raise ValueError("canonical recorded_at lost actual retrieval time")
                item = record.canonical_dump()
                item["researchBackfill"] = {
                    "historicalAvailabilityBasis": "SEC_ACCEPTANCE_DATETIME",
                    "actualRetrievedAt": raw.retrieved_at.astimezone(UTC).isoformat(),
                    "indexDate": index_day.isoformat(),
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
                    "canonicalReady": False,
                }
                dumped.append(item)
                if (
                    item.get("transaction", {}).get("economicClassification")
                    == "OPEN_MARKET_PURCHASE"
                ):
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
                    "indexDate": index_day.isoformat(),
                    "bulkFilingDate": candidate["_filed"].isoformat(),
                    "sourceUrl": raw.source_url,
                    "replayLocator": raw.replay_locator,
                    "primaryDocument": raw.primary_document,
                    "rawOwnershipXmlHash": raw_hash,
                    "normalizedOwnershipXmlHash": normalized_hash,
                    "legacyTransactionDateOffsetTransforms": legacy_date_transforms,
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
                "stage": "HYDRATE_PARSE_VALIDATE",
                "reason": type(exc).__name__,
                "message": str(exc)[:300],
            }

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(hydrate_one, row) for row in selected]
        for future in as_completed(futures):
            results.append(future.result())
    for source in sources:
        source.close()

    good = sorted((row for row in results if row["ok"]), key=lambda row: row["accession"])
    bad = sorted((row for row in results if not row["ok"]), key=lambda row: row["accession"])
    manifests = [row["manifest"] for row in good]
    records = [item for row in good for item in row["records"]]
    purchase_rows = sum(int(row["purchaseRows"]) for row in good)
    legacy_transform_filings = sum(int(row["legacyDateTransforms"]) > 0 for row in good)
    legacy_transform_values = sum(int(row["legacyDateTransforms"]) for row in good)
    elapsed = time.monotonic() - started

    _write_jsonl(output / "raw-manifest.jsonl", manifests)
    _write_jsonl(output / "canonical-research.jsonl", records)
    _write_jsonl(output / "failures.jsonl", bad)

    summary: dict[str, Any] = {
        "schemaVersion": "1.1.0",
        "source": "sec-historical-pit-hydration-research",
        "candidateRunId": candidate_run_id,
        "year": year,
        "quarter": quarter,
        "offset": offset,
        "requestedLimit": limit,
        "selectedOriginalBuyFilings": len(selected),
        "eligibleOriginalBuyFilingsInQuarter": len(candidates),
        "matchedInDailyIndex": len(matches),
        "hydratedAndParsedFilings": len(good),
        "failureCount": len(bad),
        "canonicalRecordCount": len(records),
        "openMarketPurchaseRecordCount": purchase_rows,
        "legacyDateTransformFilings": legacy_transform_filings,
        "legacyDateTransformValues": legacy_transform_values,
        "workers": workers,
        "elapsedSeconds": round(elapsed, 3),
        "filingsPerSecond": round(len(good) / elapsed, 3) if elapsed else None,
        "allCanonicalKnowledgeEqualAccepted": all(
            item["timestamps"]["knowledgeAt"] == item["timestamps"]["acceptedAt"]
            for item in records
        ),
        "historicalClockPolicy": {
            "availability": "SEC accepted_at recovered from complete submission",
            "canonicalObservedAtForResearch": "accepted_at",
            "actualResearchRetrieval": "preserved separately as recorded_at/provenance",
        },
        "amendmentPolicy": "original forms only; cross-accession amendments remain a later gate",
        "canonicalReady": False,
        "signalReady": False,
        "oosOpened": False,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
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
