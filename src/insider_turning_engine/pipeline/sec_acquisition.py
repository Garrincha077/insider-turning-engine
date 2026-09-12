"""Bounded scheduled SEC acquisition, independently of scoring/publication gates."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from insider_turning_engine.ingestion.sec.checkpoint import build_checkpoint, restore_checkpoint
from insider_turning_engine.ingestion.sec.daily_history import ingest_day
from insider_turning_engine.ingestion.sec.daily_index import SECDailyIndexSource
from insider_turning_engine.ingestion.sec.historical import _write_json


class CheckpointStore(Protocol):
    def latest(self, day: date) -> dict[str, Any] | None: ...
    def persist(self, checkpoint: dict[str, Any]) -> dict[str, str]: ...


def acquire_range(
    source: SECDailyIndexSource, store: CheckpointStore, *, start: date, end: date,
    root: Path, max_days: int = 3, max_filings: int = 750,
    newest_first: bool = False,
) -> dict[str, Any]:
    """Restore, extend and verify each day's checkpoint before reporting storage success.

    Quarantines are retained, not re-fetched with a later observation time on
    every runner. They still block acquisition completeness and all signal use.
    Explicit parser repair/replay is separate. No score state or cursor is written.
    """
    if not 1 <= max_days <= 10 or not 1 <= max_filings <= 5000:
        raise ValueError("invalid SEC acquisition budget")
    deadline = time.monotonic() + 900
    root.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schemaVersion": "1.0.0", "requestedStart": start.isoformat(),
        "requestedEnd": end.isoformat(), "storageStatus": "INCOMPLETE",
        "acquisitionStatus": "INCOMPLETE", "publishable": False, "alertsAllowed": False,
        "signalReady": False, "days": [], "deferredDays": [],
        "issues": ["ACQUISITION_ONLY_NOT_SIGNAL_HISTORY"],
    }
    report_path = root / "acquisition-status.json"
    _write_json(report_path, report)
    try:
        days = source.discover_days(start, end)
    except (RuntimeError, OSError, ValueError, KeyError, TypeError):
        report["issues"].append("SEC_DIRECTORY_DISCOVERY_FAILED")
        _write_json(report_path, report)
        return report
    report["discoveredDays"] = [day.isoformat() for day in days]
    if not days:
        report["issues"].append("NO_PUBLISHED_INDEX_IN_REQUESTED_RANGE")
    attempted_days = 0
    for day in sorted(days, reverse=newest_first):
        day_root = root / "days" / day.isoformat()
        try:
            if time.monotonic() >= deadline:
                report["deferredDays"].append(day.isoformat())
                continue
            previous = store.latest(day)
            if previous is not None:
                entries = source.discover_day(day)
                if (source.last_index_hash != previous["indexHash"]
                    or sorted(item.accession_number for item in entries)
                    != previous["discoveredAccessions"]):
                    raise ValueError("SEC index revision requires explicit replay")
            # Fully fetched (even with quarantines) needs no filing requests.
            # Verify remote bytes above on every run; never confuse this with readiness.
            reused = previous is not None and not previous["failures"]
            if not reused and attempted_days >= max_days:
                report["deferredDays"].append(day.isoformat())
                continue
            if reused:
                checkpoint = previous
                assert checkpoint is not None
            else:
                attempted_days += 1
                if previous is not None:
                    restore_checkpoint(previous, day=day, root=day_root)
                ingest_day(source, day=day, output_root=root / "days",
                           max_filings=max_filings, retry_quarantined=False, max_seconds=240)
                checkpoint = build_checkpoint(day_root, day=day)
            receipt = store.persist(checkpoint)
            if receipt.get("storageStatus") != "VERIFIED":
                raise ValueError("checkpoint storage was not verified")
            quarantines = sum(len(item["quarantines"]) for item in checkpoint["filings"])
            failures = len(checkpoint["failures"])
            report["days"].append({
                "day": day.isoformat(), "storageStatus": "VERIFIED", "reused": reused,
                "acquisitionStatus": (
                    "ACQUIRED" if not quarantines and not failures else "INCOMPLETE"
                ),
                "discoveredFilings": len(checkpoint["discoveredAccessions"]),
                "storedFilings": len(checkpoint["filings"]), "quarantineCount": quarantines,
                "pendingFilings": sum(item["status"] == "PENDING_BUDGET"
                                      for item in checkpoint["failures"]),
                "failureCount": sum(item["status"] != "PENDING_BUDGET"
                                     for item in checkpoint["failures"]),
                "recordCount": sum(len(item["records"]) for item in checkpoint["filings"]),
                "receipt": receipt,
            })
        except (RuntimeError, OSError, ValueError, KeyError, TypeError):
            report["days"].append({"day": day.isoformat(), "storageStatus": "FAILED",
                                   "acquisitionStatus": "INCOMPLETE",
                                   "reason": "ACQUISITION_OR_CHECKPOINT_FAILED"})
        _write_json(report_path, report)
    if days and not report["deferredDays"] and all(
        item["storageStatus"] == "VERIFIED" for item in report["days"]
    ):
        report["storageStatus"] = "VERIFIED"
        if all(item["acquisitionStatus"] == "ACQUIRED" for item in report["days"]):
            report["acquisitionStatus"] = "ACQUIRED"
    _write_json(report_path, report)
    return report
