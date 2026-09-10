"""Bounded, restartable canonical acquisition from a global SEC daily index.

The acquisition marker is not a scoring/cursor commit. Downstream amendment,
point-in-time identity, market coverage and methodology gates still apply.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from insider_turning_engine.domain.models import CanonicalTransaction

from .daily_index import SECDailyIndexSource
from .historical import _write_json, sha256_file
from .parser import parse_sec_filing

PARSER_VERSION = "ownership-eastern-v2.1"


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def _load_filing(path: Path, accession: str, index_hash: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        if path.is_symlink() or path.stat().st_size > 25 * 1024 * 1024:
            raise ValueError("invalid canonical filing cache")
        wrapper = json.loads(path.read_text("utf-8"))
        payload = wrapper["payload"]
        if (wrapper["sha256"] != _digest(payload) or payload["parserVersion"] != PARSER_VERSION
            or payload["accession"] != accession or payload["indexHash"] != index_hash
            or payload["quarantines"]):
            return None
        for record in payload["records"]:
            typed = CanonicalTransaction.model_validate(record)
            if typed.source.accession_number != accession:
                return None
        return dict(payload)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def ingest_day(
    source: SECDailyIndexSource, *, day: date, output_root: Path, max_filings: int = 250,
) -> dict[str, Any]:
    """Resume a completed filing day with a bounded number of new/retried filings.

    Completed filings keep their original observation/recording time and run id.
    Incomplete batches carry failures and no marker, so input preparation refuses
    them. Raw source payloads remain in the source's separate checksum cache.
    """
    if max_filings < 1:
        raise ValueError("max_filings must be positive")
    if day >= source.clock().astimezone(ZoneInfo("America/New_York")).date():
        raise ValueError("only completed SEC filing days may be acquired")
    root = output_root / day.isoformat()
    root.mkdir(parents=True, exist_ok=True)
    marker = root / "acquisition-complete.sha256"
    # A retry may expose new source errors; never leave an old success marker.
    marker.unlink(missing_ok=True)
    entries = source.discover_day(day)
    index_hash = source.last_index_hash
    rows: list[dict[str, Any]] = []
    quarantines: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    attempted = 0
    acquired = 0
    pending = 0
    proofs: list[dict[str, str]] = []
    for entry in entries:
        accession = entry.accession_number
        path = root / "filings" / f"{accession}.json"
        payload = _load_filing(path, accession, index_hash)
        if payload is None and attempted >= max_filings:
            pending += 1
            failures.append({"providerRecordId": accession, "status": "PENDING_BUDGET"})
            continue
        if payload is None:
            attempted += 1
            try:
                raw = source.fetch_entry(entry, index_hash=index_hash)
                if raw.payload is None:
                    raise ValueError("ownership XML is missing")
                parsed = parse_sec_filing(raw.payload, {
                    "accession_number": accession, "source_url": raw.source_url,
                    "accepted_at": raw.accepted_at, "observed_at": raw.retrieved_at,
                    "recorded_at": raw.retrieved_at,
                    "run_id": "run_sec_" + hashlib.sha256(accession.encode()).hexdigest()[:24],
                })
                payload = {
                    "schemaVersion": "1.0.0", "source": "sec-daily-index",
                    "parserVersion": PARSER_VERSION, "accession": accession,
                    "indexHash": index_hash, "provenance": dict(raw.provenance),
                    "records": [row.canonical_dump() for row in parsed.records],
                    "quarantines": [row.model_dump(mode="json") for row in parsed.quarantines],
                }
                _write_json(path, {"payload": payload, "sha256": _digest(payload)})
            except (RuntimeError, ValueError, OSError) as exc:
                failures.append({"providerRecordId": accession, "status": type(exc).__name__})
                continue
        rows.extend(payload["records"])
        quarantines.extend(payload["quarantines"])
        if not payload["quarantines"]:
            acquired += 1
        proofs.append({"accession": accession, "sha256": sha256_file(path)})
    rows.sort(key=lambda row: (row["transactionId"], row["revisionId"]))
    complete = not failures and not quarantines and acquired == len(entries)
    batch = {"records": rows, "quarantines": quarantines, "failures": failures}
    batch_path = root / "sec-batch.json"
    _write_json(batch_path, batch)
    report = {
        "schemaVersion": "1.0.0", "source": "sec-daily-index", "parserVersion": PARSER_VERSION,
        "day": day.isoformat(), "indexHash": index_hash, "discoveredFilings": len(entries),
        "acquiredFilings": acquired, "pendingFilings": pending, "recordCount": len(rows),
        "quarantineCount": len(quarantines),
        "failureCount": sum(item["status"] != "PENDING_BUDGET" for item in failures),
        "status": "ACQUIRED" if complete else "INCOMPLETE", "signalReady": False,
        "batchSha256": sha256_file(batch_path), "filings": proofs,
    }
    _write_json(root / "manifest.json", report)
    if complete:
        # Deliberately distinct from Gate 1's canonical batch commit marker.
        _write_json(marker, {"batchSha256": report["batchSha256"]})
    return report
