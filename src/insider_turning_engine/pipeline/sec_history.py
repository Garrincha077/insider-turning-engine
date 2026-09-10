"""Build immutable point-in-time history from verified daily checkpoints.

Incomplete acquisition never becomes a bare canonical input: blocked runs emit
only a diagnostic manifest, not a deceptively usable subset of transactions.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from insider_turning_engine.domain.models import CanonicalTransaction
from insider_turning_engine.ingestion.sec.checkpoint import encode_checkpoint, validate_checkpoint
from insider_turning_engine.normalization.amendments import resolve_amendments
from insider_turning_engine.pipeline.live_inputs import _merge_records


def assemble_history(
    checkpoints: list[dict[str, Any]], *, expected_days: tuple[date, ...],
    as_of: datetime, output: Path,
) -> dict[str, Any]:
    """Consume a source-derived published-day inventory, not guessed weekdays.

    Acquisition completeness refers ONLY to that inventory, never to 365-day
    coverage, PIT identity quality, scoring readiness, or the production gate.
    """
    if as_of.tzinfo is None or not expected_days or len(set(expected_days)) != len(expected_days):
        raise ValueError("history requires aware as_of and distinct published SEC days")
    as_of = as_of.astimezone(UTC)
    days = set(expected_days)
    if any(day > as_of.date() for day in days):
        raise ValueError("history day is later than as_of")
    selected: dict[date, dict[str, Any]] = {}
    for checkpoint in checkpoints:
        day = date.fromisoformat(checkpoint["day"])
        validate_checkpoint(checkpoint, day=day)
        if day not in days:
            raise ValueError("checkpoint lies outside the published-day inventory")
        if day in selected and selected[day] != checkpoint:
            raise ValueError("multiple conflicting checkpoint versions for one day")
        selected[day] = checkpoint
    missing = sorted(day.isoformat() for day in days - selected.keys())
    failures = sum(len(item["failures"]) for item in selected.values())
    quarantines = sum(len(filing["quarantines"]) for item in selected.values()
                      for filing in item["filings"])
    rows = []
    excluded = 0
    for day in sorted(selected):
        for filing in selected[day]["filings"]:
            for value in filing["records"]:
                row = CanonicalTransaction.model_validate(value)
                available = max(row.timestamps.knowledge_at, row.timestamps.recorded_at)
                if available > as_of or row.transaction.transaction_date > as_of.date():
                    excluded += 1
                else:
                    rows.append(row)
    unique = _merge_records(rows)
    resolution = resolve_amendments(unique, as_of=as_of)
    reasons = []
    if missing:
        reasons.append("MISSING_PUBLISHED_DAYS")
    if failures:
        reasons.append("INCOMPLETE_SEC_ACQUISITION")
    if quarantines:
        reasons.append("SEC_ROW_QUARANTINE")
    if resolution.quarantines:
        reasons.append("UNRESOLVED_AMENDMENTS")
    report: dict[str, Any] = {
        "schemaVersion": "1.0.0", "source": "sec-daily-checkpoints",
        "asOf": as_of.isoformat(), "status": "BLOCKED" if reasons else "HISTORY_READY",
        "signalReady": False, "publishable": False, "alertsAllowed": False,
        "publishedDays": sorted(day.isoformat() for day in days), "missingDays": missing,
        "coverageScope": "explicit published-day inventory only; not complete 365-day history",
        "sourceFailureCount": failures, "sourceQuarantineCount": quarantines,
        "amendmentQuarantineCount": len(resolution.quarantines),
        "eligibleObservations": len(rows), "uniqueObservations": len(unique),
        "effectiveTransactions": len(resolution.effective_records),
        "excludedAfterAsOf": excluded, "blockingReasons": reasons,
        "checkpoints": [{"day": day.isoformat(), "asset": encode_checkpoint(selected[day])[0]}
                        for day in sorted(selected)],
    }
    contents: dict[str, bytes] = {}
    if not reasons:
        contents["canonical.json"] = _json([row.canonical_dump() for row in unique])
        contents["effective.json"] = _json([
            row.canonical_dump() for row in sorted(resolution.effective_records,
                                                 key=lambda item: item.transaction_id)
        ])
    report["artifacts"] = {name: "sha256:" + hashlib.sha256(content).hexdigest()
                           for name, content in sorted(contents.items())}
    contents["history-manifest.json"] = _json(report)
    if output.exists():
        if (output.is_symlink() or not output.is_dir()
            or {path.name for path in output.iterdir()} != set(contents)
            or any((output / name).is_symlink() or (output / name).read_bytes() != content
                   for name, content in contents.items())):
            raise ValueError("immutable history output already exists with different evidence")
        return report
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sec-history-", dir=output.parent) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        for name, content in contents.items():
            with (staging / name).open("wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(staging, output)
    return report


def _json(value: Any) -> bytes:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return (text + "\n").encode()
