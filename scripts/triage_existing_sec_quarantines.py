"""Read-only audit of quarantined SEC parser rows in verified historical Releases.

Never fetch SEC, mutate Releases, advance cursors, retry acquisition, publish
scoring outputs, or deliver a message. Export aggregate codes only: no SEC
payloads, owner identities, accession IDs or filing content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from insider_turning_engine.ingestion.sec.checkpoint import (
    encode_checkpoint,
    validate_checkpoint,
)
from insider_turning_engine.ingestion.sec.release_store import ReleaseCheckpointStore

_DAY_KEYS = {"day", "discoveredFilings", "storedFilings", "quarantinedRows", "failures"}
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")


class SourceDriftError(ValueError):
    """A remote checkpoint cannot be reconciled to pinned historical evidence."""


def verify_expectation(value: Any) -> list[dict[str, Any]]:
    if (not isinstance(value, dict)
            or value.get("schemaVersion") != "sec-quarantine-triage-input-v1"
            or not isinstance(value.get("sourceRunId"), str)
            or not value["sourceRunId"].startswith("run_research_")
            or not isinstance(value.get("sourceResearchSha256"), str)
            or _DIGEST.fullmatch(value["sourceResearchSha256"]) is None):
        raise SourceDriftError("invalid pinned SEC reference")
    when = value.get("sourceAsOf")
    if not isinstance(when, str):
        raise SourceDriftError("missing sourceAsOf")
    try:
        stamp = datetime.fromisoformat(when.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceDriftError("invalid sourceAsOf") from exc
    if stamp.tzinfo is None:
        raise SourceDriftError("sourceAsOf must be timezone-aware")
    days = value.get("incompleteDays")
    if not isinstance(days, list) or not 1 <= len(days) <= 100:
        raise SourceDriftError("empty or oversized incomplete-day inventory")
    seen: set[str] = set()
    for item in days:
        if not isinstance(item, dict) or set(item) != _DAY_KEYS:
            raise SourceDriftError("invalid incomplete-day evidence shape")
        day = item["day"]
        if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day or day in seen:
            raise SourceDriftError("duplicate or malformed SEC date")
        seen.add(day)
        for field in _DAY_KEYS - {"day"}:
            if type(item[field]) is not int or item[field] < 0:
                raise SourceDriftError("negative or invalid SEC count")
        if (item["storedFilings"] > item["discoveredFilings"]
                or item["quarantinedRows"] + item["failures"]
                + item["discoveredFilings"] - item["storedFilings"] == 0):
            raise SourceDriftError("source day is not incomplete")
    return sorted(days, key=lambda row: row["day"])


def aggregate_verified_checkpoint(checkpoint: dict[str, Any], *, day: date,
                                  expected: dict[str, Any]) -> dict[str, Any]:
    verified = validate_checkpoint(checkpoint, day=day)
    filings = verified["filings"]
    actual = {
        "discoveredFilings": len(verified["discoveredAccessions"]),
        "storedFilings": len(filings),
        "quarantinedRows": sum(len(row["quarantines"]) for row in filings),
        "failures": len(verified["failures"]),
    }
    if any(actual[key] != expected[key] for key in actual):
        raise SourceDriftError(
            f"SEC day aggregate drift for {day.isoformat()}; no source rows changed"
        )
    counts: Counter[str] = Counter()
    for filing in filings:
        for row in filing["quarantines"]:
            raw = row.get("reason_code")
            key = raw if isinstance(raw, str) and _CODE.fullmatch(raw) else "UNRECOGNIZED_REASON_CODE"
            counts[key] += 1
    if sum(counts.values()) != actual["quarantinedRows"]:
        raise SourceDriftError(f"SEC reason counts do not reconcile for {day.isoformat()}")
    archive_name, archive_bytes = encode_checkpoint(verified)
    digest = hashlib.sha256(archive_bytes).hexdigest()
    if archive_name != f"checkpoint-{digest}.json.gz":
        raise SourceDriftError("remote immutable SEC checkpoint SHA mismatch")
    return {
        "day": day.isoformat(), **actual,
        "parserVersion": verified["parserVersion"],
        "checkpointSha256": digest,
        "quarantineReasonCodes": dict(sorted(counts.items())),
    }


def audit(store: ReleaseCheckpointStore, pinned: dict[str, Any]) -> dict[str, Any]:
    rows = verify_expectation(pinned)
    seen: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    for row in rows:
        day = date.fromisoformat(row["day"])
        checkpoint = store.latest(day)
        if checkpoint is None:
            raise SourceDriftError(f"verified SEC release missing for {day}")
        details = aggregate_verified_checkpoint(checkpoint, day=day, expected=row)
        reasons.update(details["quarantineReasonCodes"])
        seen.append(details)
    if sum(reasons.values()) != sum(row["quarantinedRows"] for row in rows):
        raise SourceDriftError("global SEC quarantine totals disagree")
    return {
        "schemaVersion": "sec-quarantine-cause-audit-v1",
        "status": "VERIFIED_CURRENT_CHECKPOINT_COUNTS_MATCH_PINNED_SOURCE",
        "scope": "READ_ONLY_AGGREGATE_PARSER_CAUSES_NOT_SCORING",
        "sourceResearchRunId": pinned["sourceRunId"],
        "sourceResearchSha256": pinned["sourceResearchSha256"],
        "incompleteDays": len(rows),
        "totalQuarantinedRows": sum(reasons.values()),
        "reasonCounts": dict(sorted(reasons.items())),
        "days": seen,
        "sourceIdentityCaveat": (
            "Remote latest verified SEC releases match pinned day counts. "
            "The historical research snapshot did not record each day's exact release tag; "
            "matching counts alone do not prove byte-for-byte identity to that earlier snapshot."
        ),
        "stateModified": False,
        "scoringModified": False,
        "alertsSent": False,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--repository", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()
    if not args.execute:
        print("DRY_RUN: no remote releases read or data mutated; add --execute")
        return
    pinned = json.loads(args.source.read_text(encoding="utf-8"))
    result = audit(ReleaseCheckpointStore(args.repository, target=args.target), pinned)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "days": result["incompleteDays"],
                      "quarantinedRows": result["totalQuarantinedRows"],
                      "reasonCounts": result["reasonCounts"], "alertsSent": False},
                     sort_keys=True))


if __name__ == "__main__":
    main()
