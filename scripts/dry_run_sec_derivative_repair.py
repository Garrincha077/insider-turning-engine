"""Verify the existing derivative SEC repair method without publishing anything.

Reads only pinned, immutable GitHub SEC checkpoints and the original SEC source.
Runs repair_checkpoint() in memory on full original days, never an altered
subset. It deliberately cannot modify Releases, the SEC cursor, scores, Pages,
or the digest/Telegram ledger. Output is aggregate only, without filing data.
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
from insider_turning_engine.ingestion.sec.checkpoint import encode_checkpoint
from insider_turning_engine.ingestion.sec.daily_index import SECDailyIndexSource
from insider_turning_engine.ingestion.sec.release_store import ReleaseCheckpointStore
from insider_turning_engine.ingestion.sec.repair_amounts import repair_checkpoint
from triage_existing_sec_quarantines import (
    SourceDriftError,
    aggregate_verified_checkpoint,
    verify_expectation,
)

MAX_DAYS = 20
MAX_DERIVATIVE_FILES = 30
_ALLOWED_VERSIONS = frozenset({"1.1.0", "1.2.0"})


def _candidate(filing: dict[str, Any]) -> bool:
    return bool(filing["quarantines"]) and all(
        q["reason_code"] == "INVALID_TRANSACTION"
        and q["source_row_key"].startswith("DERIVATIVE:")
        for q in filing["quarantines"]
    )


def _lineage_status(filing: dict[str, Any]) -> str:
    rows = [CanonicalTransaction.model_validate(row) for row in filing["records"]]
    if not rows:
        return "NO_PRIOR_CANONICAL_ROWS"
    first = rows[0]
    if any(row.timestamps != first.timestamps or row.run_id != first.run_id
           for row in rows):
        return "MIXED_PRIOR_LINEAGE"
    return "HAS_PRIOR_CANONICAL_LINEAGE"


def _failure_category(exc: Exception) -> str:
    # Never show untrusted HTTP/provider/validation exception strings.
    message = str(exc)
    if "SEC index changed" in message:
        return "OFFICIAL_INDEX_CHANGED"
    if "source submission or acceptance evidence changed" in message:
        return "SOURCE_HASH_OR_ACCEPTANCE_DRIFT"
    if "source replay still has quarantines" in message:
        return "CURRENT_PARSER_STILL_REJECTS_ROW"
    if "original parsed row as lineage evidence" in message:
        return "MISSING_ORIGINAL_LINEAGE"
    if "mixed prior observation lineage" in message:
        return "MIXED_PRIOR_LINEAGE"
    if "repair changed or removed an existing canonical revision" in message:
        return "EXISTING_CANONICAL_FACTS_CHANGED"
    if "recovered rows do not exactly resolve" in message:
        return "RECOVERED_ROW_IDENTITY_OR_SCHEMA_MISMATCH"
    if "invalid repaired row inventory" in message:
        return "INVALID_REPAIR_RECEIPT"
    return "UNCLASSIFIED_FAIL_CLOSED"


def verify_dry_run(original: dict[str, Any], proposed: dict[str, Any],
                   *, repair_at: datetime) -> tuple[int, int]:
    """Check that a returned in-memory repair changed only verified new rows."""
    original_name, original_bytes = encode_checkpoint(original)
    proposed_name, proposed_bytes = encode_checkpoint(proposed)
    if not original_name or not proposed_name or not original_bytes or not proposed_bytes:
        raise SourceDriftError("invalid replay evidence")
    if original["day"] != proposed["day"] or original["indexHash"] != proposed["indexHash"]:
        raise SourceDriftError("replay changed the SEC source identity")
    if original["discoveredAccessions"] != proposed["discoveredAccessions"]:
        raise SourceDriftError("replay changed SEC discovery")
    if original["failures"] != proposed["failures"] or proposed["signalReady"] is not False:
        raise SourceDriftError("replay changed failed-source or signal state")
    if len(original["filings"]) != len(proposed["filings"]):
        raise SourceDriftError("replay changed filing inventory")
    old_files = {f["accession"]: f for f in original["filings"]}
    new_files = {f["accession"]: f for f in proposed["filings"]}
    if old_files.keys() != new_files.keys():
        raise SourceDriftError("replay changed filing IDs")

    recovered = 0
    newly_known = 0
    for accession, old in old_files.items():
        fresh = new_files[accession]
        original_rows = {
            (r["transactionId"], r["revisionId"]): r for r in old["records"]
        }
        after_rows = {
            (r["transactionId"], r["revisionId"]): r for r in fresh["records"]
        }
        if any(after_rows.get(key) != prior for key, prior in original_rows.items()):
            raise SourceDriftError("replay changed existing canonical records")
        if (old["provenance"] != fresh["provenance"]
                or old["indexHash"] != fresh["indexHash"]):
            raise SourceDriftError("replay changed source provenance")
        new_keys = after_rows.keys() - original_rows.keys()
        if _candidate(old):
            prior_quarantines = {row["source_row_key"] for row in old["quarantines"]}
            if (fresh["quarantines"] or len(new_keys) != len(old["quarantines"])
                    or {after_rows[key]["source"]["sourceRowKey"] for key in new_keys}
                    != prior_quarantines):
                raise SourceDriftError("replay failed exact quarantine reconciliation")
            for key in new_keys:
                row = CanonicalTransaction.model_validate(after_rows[key])
                if (row.schema_version not in _ALLOWED_VERSIONS
                        or row.timestamps.knowledge_at != repair_at
                        or row.timestamps.recorded_at != repair_at
                        or row.timestamps.observed_at != repair_at
                        or row.lifecycle.valid_from != repair_at
                        or row.ingested_at != repair_at
                        or not row.run_id.startswith("run_repair_")):
                    raise SourceDriftError("replay backdated or fabricated recovered facts")
            recovered += len(old["quarantines"])
            newly_known += len(new_keys)
        elif fresh != old:
            raise SourceDriftError("replay modified a non-target filing")
    if recovered != newly_known:
        raise SourceDriftError("replay row gain differs from quarantines")
    return recovered, newly_known


def audit(store: ReleaseCheckpointStore, source: SECDailyIndexSource,
          pinned: dict[str, Any], *, repair_at: datetime) -> dict[str, Any]:
    expected = verify_expectation(pinned)
    if len(expected) > MAX_DAYS:
        raise SourceDriftError("bounded audit day limit reached")
    if repair_at.tzinfo is None:
        raise SourceDriftError("dry-run timestamp must have a timezone")
    original_rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    total_derivative = 0
    for day_row in expected:
        day = date.fromisoformat(day_row["day"])
        checkpoint = store.latest(day)
        if checkpoint is None:
            raise SourceDriftError("SEC checkpoint missing from immutable Releases")
        aggregate_verified_checkpoint(checkpoint, day=day, expected=day_row)
        total_derivative += sum(_candidate(f) for f in checkpoint["filings"])
        original_rows.append((checkpoint, day_row))
    if total_derivative > MAX_DERIVATIVE_FILES:
        raise SourceDriftError("bounded derivative filing limit reached")

    counters: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    day_results: list[dict[str, Any]] = []
    for checkpoint, day_row in original_rows:
        day = date.fromisoformat(day_row["day"])
        candidates = [f for f in checkpoint["filings"] if _candidate(f)]
        counts = Counter(_lineage_status(f) for f in candidates)
        eligible = counts["HAS_PRIOR_CANONICAL_LINEAGE"]
        total_rows = sum(len(f["quarantines"]) for f in candidates)
        counters["candidateDerivativeFilings"] += len(candidates)
        counters["candidateDerivativeRows"] += total_rows
        counters["candidateFilingsWithLineage"] += eligible
        counters["candidateFilingsWithoutLineage"] += counts["NO_PRIOR_CANONICAL_ROWS"]
        counters["candidateFilingsMixedLineage"] += counts["MIXED_PRIOR_LINEAGE"]
        day_status = "NO_DERIVATIVE_CANDIDATES"
        returned_rows = 0
        if candidates and (counts["NO_PRIOR_CANONICAL_ROWS"]
                           or counts["MIXED_PRIOR_LINEAGE"]):
            # Existing repair_checkpoint intentionally requires *every*
            # derivative candidate on this day to have original row lineage.
            # Never silently mask/strip other immutable quarantines to force it.
            day_status = "BLOCKED_WHOLE_DAY_DUE_TO_UNVERIFIABLE_CANDIDATE"
            counters["candidateFilingsBlockedByDayAtomicity"] += eligible
        elif candidates:
            # Run the actual production implementation, not a reimplementation.
            # It returns a validated copy; no call to store.persist() exists.
            before = encode_checkpoint(checkpoint)
            try:
                proposed = repair_checkpoint(checkpoint, source, repaired_at=repair_at)
                if encode_checkpoint(checkpoint) != before:
                    raise SourceDriftError("original immutable checkpoint mutated")
                returned_rows, newly_known = verify_dry_run(
                    checkpoint, proposed, repair_at=repair_at
                )
                if newly_known != total_rows:
                    raise SourceDriftError("dry-run did not recover all eligible rows")
                day_status = "FULL_DAY_REPAIR_DRY_RUN_VERIFIED"
                counters["verifiedDryRunFilings"] += eligible
                counters["verifiedDryRunRows"] += returned_rows
            except (ValueError, RuntimeError, OSError, TypeError, KeyError) as exc:
                if encode_checkpoint(checkpoint) != before:
                    raise SourceDriftError("exception mutated immutable checkpoint") from None
                day_status = "BLOCKED_" + _failure_category(exc)
                counters["candidateFilingsBlockedByReplay"] += eligible
        statuses[day_status] += 1
        day_results.append({
            "day": day.isoformat(),
            "candidateDerivativeFilings": len(candidates),
            "candidateDerivativeRows": total_rows,
            "lineageBackedFilings": eligible,
            "result": day_status,
            "verifiedDryRunRows": returned_rows,
        })

    if counters["candidateDerivativeFilings"] != (
            counters["candidateFilingsWithLineage"]
            + counters["candidateFilingsWithoutLineage"]
            + counters["candidateFilingsMixedLineage"]):
        raise SourceDriftError("derivative candidate accounting mismatch")
    if counters["candidateFilingsWithLineage"] != (
            counters["verifiedDryRunFilings"]
            + counters["candidateFilingsBlockedByReplay"]
            + counters["candidateFilingsBlockedByDayAtomicity"]):
        raise SourceDriftError("eligible derivative filing accounting mismatch")
    return {
        "schemaVersion": "sec-derivative-repair-dry-run-v1",
        "status": "COMPLETE_DIAGNOSTIC_NOT_AN_ARCHIVE_REPAIR",
        "sourceResearchRunId": pinned["sourceRunId"],
        "daysExamined": len(day_results),
        "summary": dict(sorted(counters.items())),
        "dayStatusCounts": dict(sorted(statuses.items())),
        "days": day_results,
        "sourceContract": (
            "Latest verified immutable SEC checkpoints checked against pinned aggregate "
            "day counts; original source hash/acceptance enforced by repair_checkpoint. "
            "Historical snapshot did not pin per-day release tags."
        ),
        "approval": "NONE_NO_AUTOMATIC_REPAIR",
        "remoteWrites": False, "archivePublished": False,
        "cursorAdvanced": False, "scoringChanged": False, "telegramSent": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print('{"status":"DRY_RUN_NO_NETWORK_REQUESTS"}')
        return
    pinned = json.loads(args.source.read_text(encoding="utf-8"))
    sec = SECDailyIndexSource(os.environ["SEC_USER_AGENT"], cache_dir=None,
                              max_attempts=2)
    try:
        result = audit(ReleaseCheckpointStore(args.repository, target=args.target),
                       sec, pinned, repair_at=datetime.now(UTC))
    finally:
        sec.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "status": result["status"], "summary": result["summary"],
        "dayStatusCounts": result["dayStatusCounts"],
        "remoteWrites": False, "archivePublished": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
