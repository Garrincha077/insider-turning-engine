"""Bounded read-only replay of quarantined SEC rows against current parser.

Inputs are verified immutable GitHub SEC Release checkpoints, never unchecked
filing identifiers. Fetch only the original submissions for quarantined rows;
require unchanged official index and source provenance. Never persist SEC
responses, checkpoint mutations, cursor, scores, alerts or dashboard changes.

Only safe aggregate diagnostic categories leave this process. Raw XML, accession
numbers, owner identifiers and exception messages are not logged or archived.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from insider_turning_engine.domain.models import CanonicalTransaction
from insider_turning_engine.ingestion.sec.daily_index import SECDailyIndexSource
from insider_turning_engine.ingestion.sec.parser import parse_sec_filing
from insider_turning_engine.ingestion.sec.release_store import ReleaseCheckpointStore
from triage_existing_sec_quarantines import (
    SourceDriftError,
    aggregate_verified_checkpoint,
    verify_expectation,
)

# These correspond to explicit, static validation conditions in parser.py.
# Unknown/untrusted exception prose is never copied to output.
KNOWN_REASONS = (
    ("security title, transaction date, non-derivative code, and A/D",
     "REQUIRED_TRANSACTION_FIELDS"),
    ("transaction shares are required and must be non-negative",
     "MISSING_OR_INVALID_SHARES"),
    ("derivative without transaction shares requires a valid total value",
     "DERIVATIVE_TOTAL_VALUE_UNAVAILABLE"),
    ("transaction price is invalid", "INVALID_PRICE"),
    ("post-transaction shares are invalid", "INVALID_POST_HOLDINGS"),
    ("acquired/disposed code must be A or D", "INVALID_ACQUIRED_DISPOSED"),
    ("direct/indirect ownership must be D or I", "INVALID_OWNERSHIP_NATURE"),
)
MAX_DAYS = 20
MAX_SUBMISSIONS = 60


def safe_cause(message: str) -> str:
    """Classify only hard-coded parser conditions, never include free text."""
    for needle, code in KNOWN_REASONS:
        if needle in message:
            return code
    if "date" in message.lower():
        return "INVALID_DATE_OR_TIMESTAMP"
    return "OTHER_MODEL_OR_PARSER_VALIDATION"


def old_lineage(filing: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Reconstruct original parser metadata if a validated canonical row exists."""
    rows = [CanonicalTransaction.model_validate(x) for x in filing["records"]]
    now = datetime.now(UTC)
    if not rows:
        return ({
            "accession_number": filing["accession"], "observed_at": now,
            "recorded_at": now, "run_id": "run_diagnostic_only_no_lineage",
        }, False)
    first = rows[0]
    consistent = all(row.timestamps == first.timestamps
                     and row.run_id == first.run_id for row in rows)
    return ({
        "accession_number": filing["accession"],
        "accepted_at": first.timestamps.accepted_at,
        "observed_at": first.timestamps.observed_at,
        "recorded_at": first.timestamps.recorded_at,
        "run_id": first.run_id,
        "source_url": first.source.source_url,
    }, consistent)


def replay_filing(filing: dict[str, Any], raw: Any) -> dict[str, Any]:
    """Compare expected quarantine row keys against current parser in memory."""
    expected = [q["source_row_key"] for q in filing["quarantines"]]
    if len(set(expected)) != len(expected):
        raise SourceDriftError("duplicate quarantine row keys")
    metadata, lineage_ok = old_lineage(filing)
    metadata["source_url"] = raw.source_url
    metadata["accepted_at"] = raw.accepted_at

    old = [CanonicalTransaction.model_validate(item) for item in filing["records"]]
    if old and (any(item.timestamps.accepted_at != raw.accepted_at or
                    item.source.source_url != raw.source_url for item in old)):
        return {"sourceStatus": "TIMESTAMP_OR_PRIMARY_DOCUMENT_DRIFT",
                "outcomes": {"SOURCE_DRIFT": len(expected)}}
    if not lineage_ok and old:
        return {"sourceStatus": "MIXED_PRIOR_LINEAGE",
                "outcomes": {"UNVERIFIED_LINEAGE": len(expected)}}

    current = parse_sec_filing(raw.payload, metadata)
    current_valid = {row.source.source_row_key: row for row in current.records}
    current_bad = {q.source_row_key: q for q in current.quarantines if q.source_row_key}
    old_by_identity = {(row.transaction_id, row.revision_id): row.canonical_dump()
                       for row in old}
    new_by_identity = {(row.transaction_id, row.revision_id): row.canonical_dump()
                       for row in current.records}
    preserved = all(new_by_identity.get(key) == value
                    for key, value in old_by_identity.items()) if lineage_ok else False

    outcomes: Counter[str] = Counter()
    for key in expected:
        if key in current_bad:
            outcomes["STILL_REJECTED_" + safe_cause(current_bad[key].message)] += 1
        elif key in current_valid:
            outcomes["PARSES_WITH_CURRENT_PARSER"] += 1
        else:
            outcomes["NOT_REPRODUCED_BY_CURRENT_PARSER"] += 1

    # Additional quarantine/record differences block any "safe repair" claim.
    extras = (set(current_bad) - set(expected))
    source_status = ("CANONICAL_UNCHANGED" if preserved else "CANONICAL_UNVERIFIED_OR_CHANGED")
    if extras or any(q.source_row_key is None for q in current.quarantines):
        source_status = "NEW_OR_UNSCOPED_QUARANTINES"
    derivative_only = bool(expected) and all(
        q["reason_code"] == "INVALID_TRANSACTION"
        and q["source_row_key"].startswith("DERIVATIVE:")
        for q in filing["quarantines"]
    )
    recovered = set(current_valid) - {
        row.source.source_row_key for row in old
    }
    schema_valid = all(
        row.schema_version in {"1.1.0", "1.2.0"}
        for key, row in current_valid.items() if key in recovered
    )
    # Pure diagnostic: not a write permission, not proof of approval for repair.
    possible_derivative_replay = (
        derivative_only and bool(old) and lineage_ok and preserved
        and not current.quarantines and recovered == set(expected)
        and schema_valid and source_status == "CANONICAL_UNCHANGED"
    )
    return {
        "sourceStatus": source_status,
        "lineageAvailable": bool(old) and lineage_ok,
        "outcomes": dict(sorted(outcomes.items())),
        "derivativeOnlyReplayPrecheck": possible_derivative_replay,
        "eligibleForAutomaticRepair": False,
    }


def audit(store: ReleaseCheckpointStore, source: SECDailyIndexSource,
          pinned: dict[str, Any]) -> dict[str, Any]:
    expected = verify_expectation(pinned)
    if len(expected) > MAX_DAYS:
        raise SourceDriftError("too many days for read-only replay")
    checkpoints: list[tuple[dict[str, Any], dict[str, Any]]] = []
    total = 0
    for day_row in expected:
        day = date.fromisoformat(day_row["day"])
        checkpoint = store.latest(day)
        if checkpoint is None:
            raise SourceDriftError("one or more pinned SEC checkpoint releases are unavailable")
        aggregate_verified_checkpoint(checkpoint, day=day, expected=day_row)
        targets = [x for x in checkpoint["filings"] if x["quarantines"]]
        total += len(targets)
        checkpoints.append((checkpoint, day_row))
    if total > MAX_SUBMISSIONS:
        raise SourceDriftError("bounded SEC submission budget exceeded")

    outcomes: Counter[str] = Counter()
    cause_total: Counter[str] = Counter()
    row_kinds: Counter[str] = Counter()
    source_statuses: Counter[str] = Counter()
    precheck = 0
    checked = 0
    day_summary = []
    for checkpoint, day_row in checkpoints:
        day = date.fromisoformat(day_row["day"])
        targets = [x for x in checkpoint["filings"] if x["quarantines"]]
        rows_targeted = sum(len(x["quarantines"]) for x in targets)
        day_outcomes: Counter[str] = Counter()
        day_status = "SOURCE_PROOFS_VERIFIED"
        try:
            entries = {entry.accession_number: entry for entry in source.discover_day(day)}
            if (source.last_index_hash != checkpoint["indexHash"] or
                    set(entries) != set(checkpoint["discoveredAccessions"])):
                day_status = "INDEX_SOURCE_DRIFT"
        except (RuntimeError, ValueError, OSError):
            day_status = "INDEX_SOURCE_UNAVAILABLE"
        if day_status != "SOURCE_PROOFS_VERIFIED":
            day_outcomes[day_status] = rows_targeted
        else:
            for filing in targets:
                expected_count = len(filing["quarantines"])
                entry = entries.get(filing["accession"])
                if entry is None:
                    day_outcomes["ORIGINAL_ENTRY_UNAVAILABLE"] += expected_count
                    continue
                try:
                    raw = source.fetch_entry(entry, index_hash=checkpoint["indexHash"])
                except (RuntimeError, ValueError, OSError):
                    day_outcomes["ORIGINAL_SUBMISSION_UNAVAILABLE"] += expected_count
                    continue
                if (raw.payload is None or raw.accession_number != filing["accession"]
                        or raw.provenance != filing["provenance"]):
                    day_outcomes["SOURCE_SUBMISSION_HASH_OR_PROVENANCE_DRIFT"] += expected_count
                    continue
                try:
                    result = replay_filing(filing, raw)
                except (ValueError, TypeError, KeyError, AttributeError):
                    day_outcomes["CURRENT_PARSER_REPLAY_ERROR"] += expected_count
                    continue
                day_outcomes.update(result["outcomes"])
                source_statuses[result["sourceStatus"]] += expected_count
                precheck += int(result.get("derivativeOnlyReplayPrecheck", False))
                checked += expected_count
        if sum(day_outcomes.values()) != rows_targeted:
            raise SourceDriftError("replay categories fail to reconcile with pinned quarantine")
        outcomes.update(day_outcomes)
        # Only date + aggregate values; no untrusted filing metadata in artifact.
        day_summary.append({
            "day": day.isoformat(), "quarantinedRows": rows_targeted,
            "classifiedCounts": dict(sorted(day_outcomes.items())),
            "verification": day_status,
        })

    return {
        "schemaVersion": "sec-quarantine-read-only-replay-v1",
        "status": ("COMPLETE_DIAGNOSTIC_NOT_A_REPAIR"
                   if checked == sum(row["quarantinedRows"] for row in expected)
                   else "PARTIAL_UNVERIFIED"),
        "scope": "AGGREGATE_SOURCE_VERIFIED_REPLAY_ONLY",
        "sourceResearchRunId": pinned["sourceRunId"],
        "quarantinedRows": sum(row["quarantinedRows"] for row in expected),
        "quarantinedFilingsTargeted": total,
        "sourceVerifiedRowsParsed": checked,
        "outcomeTotals": dict(sorted(outcomes.items())),
        "sourceStatusTotals": dict(sorted(source_statuses.items())),
        "derivativePrecheckFilings": precheck,
        "days": day_summary,
        "limitations": (
            "Checked currently latest immutable releases, not exact pinned old release tags. "
            "A derivative precheck is not authorization to publish a repair; historical "
            "PIT timestamps, parser policy, scores and alerts are unchanged."
        ),
        "sourceDataWritten": False, "checkpointUpdated": False,
        "scoreChanged": False, "alertsSent": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print('{"status":"DRY_RUN_NO_SOURCE_REQUESTS"}')
        return 0
    pinned = json.loads(args.source.read_text(encoding="utf-8"))
    store = ReleaseCheckpointStore(args.repository, target=args.target)
    sec = SECDailyIndexSource(os.environ["SEC_USER_AGENT"], cache_dir=None,
                              max_attempts=2)
    try:
        report = audit(store, sec, pinned)
    finally:
        sec.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "status": report["status"], "quarantinedRows": report["quarantinedRows"],
        "sourceVerifiedRowsParsed": report["sourceVerifiedRowsParsed"],
        "outcomeTotals": report["outcomeTotals"],
        "derivativePrecheckFilings": report["derivativePrecheckFilings"],
        "scoresChanged": False, "alertsSent": False,
    }, sort_keys=True))
    return 0 if report["status"] == "COMPLETE_DIAGNOSTIC_NOT_A_REPAIR" else 2


if __name__ == "__main__":
    raise SystemExit(main())
