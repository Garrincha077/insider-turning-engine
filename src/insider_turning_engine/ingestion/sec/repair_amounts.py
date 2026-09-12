"""Explicit, source-verified replay of amount-only derivative quarantines.

No cursor/marker, fuzzy amendment matching, score changes or automatic retries.
Unchanged rows retain exact bytes; newly recovered facts become known at repair.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from insider_turning_engine.domain.models import CanonicalTransaction

from .checkpoint import encode_checkpoint, validate_checkpoint
from .daily_history import PARSER_VERSION, _digest
from .daily_index import SECDailyIndexSource
from .historical import _write_json
from .parser import parse_sec_filing
from .release_store import ReleaseCheckpointStore


def repair_checkpoint(
    original: dict[str, Any], source: SECDailyIndexSource, *, repaired_at: datetime,
) -> dict[str, Any]:
    """Read-only against source/archive. Caller alone may publish the result."""
    day = date.fromisoformat(original["day"])
    validate_checkpoint(original, day=day)
    if repaired_at.tzinfo is None or repaired_at < datetime.combine(day, datetime.min.time(), UTC):
        raise ValueError("repair requires an aware, non-retroactive clock")
    candidates = [filing for filing in original["filings"] if filing["quarantines"]
                  and all(q["reason_code"] == "INVALID_TRANSACTION"
                          and q["source_row_key"].startswith("DERIVATIVE:")
                          for q in filing["quarantines"])]
    if not candidates:
        return copy.deepcopy(original)
    entries = {entry.accession_number: entry for entry in source.discover_day(day)}
    if (sorted(entries) != original["discoveredAccessions"]
            or source.last_index_hash != original["indexHash"]):
        raise ValueError("SEC index changed; amount repair cannot rewrite discovery")
    parent_name, _ = encode_checkpoint(original)
    parent_hash = parent_name.removeprefix("checkpoint-").removesuffix(".json.gz")
    result = copy.deepcopy(original)
    result["parserVersion"] = PARSER_VERSION
    by_accession = {filing["accession"]: filing for filing in result["filings"]}
    for filing in candidates:
        rows = [CanonicalTransaction.model_validate(row) for row in filing["records"]]
        if not rows:
            raise ValueError("repair requires an original parsed row as lineage evidence")
        first = rows[0]
        if any(row.timestamps != first.timestamps or row.run_id != first.run_id for row in rows):
            raise ValueError("mixed prior observation lineage requires manual investigation")
        if repaired_at < first.timestamps.recorded_at:
            raise ValueError("repair cannot precede original observation")
        raw = source.fetch_entry(entries[filing["accession"]], index_hash=original["indexHash"])
        if (raw.payload is None or raw.accepted_at != first.timestamps.accepted_at
                or dict(raw.provenance) != filing["provenance"]):
            raise ValueError("source submission or acceptance evidence changed")
        # Recreate original metadata solely to compare the existing canonical bytes.
        parsed = parse_sec_filing(raw.payload, {
            "accession_number": filing["accession"], "source_url": raw.source_url,
            "accepted_at": first.timestamps.accepted_at,
            "observed_at": first.timestamps.observed_at,
            "recorded_at": first.timestamps.recorded_at, "run_id": first.run_id,
        })
        if parsed.quarantines:
            raise ValueError("source replay still has quarantines; archive unchanged")
        previous = {(row.transaction_id, row.revision_id): row.canonical_dump() for row in rows}
        fresh = {(row.transaction_id, row.revision_id): row for row in parsed.records}
        if not previous.keys() <= fresh.keys() or any(fresh[key].canonical_dump() != value
                                                    for key, value in previous.items()):
            raise ValueError("repair changed or removed an existing canonical revision")
        recovered = [row for key, row in fresh.items() if key not in previous]
        expected = sorted(q["source_row_key"] for q in filing["quarantines"])
        actual = sorted(row.source.source_row_key for row in recovered)
        if (not actual or actual != expected or len(set(expected)) != len(expected)
                or any(row.schema_version != "1.1.0" for row in recovered)):
            raise ValueError("recovered rows do not exactly resolve derivative quarantines")
        for row in recovered:
            # Do not retroactively inject a repaired row into an older as-of snapshot.
            row.timestamps.observed_at = repaired_at
            row.timestamps.recorded_at = repaired_at
            row.timestamps.knowledge_at = repaired_at
            row.ingested_at = repaired_at
            row.lifecycle.valid_from = repaired_at
            row.run_id = "run_repair_" + hashlib.sha256(
                (parent_hash + repaired_at.isoformat()).encode()).hexdigest()[:24]
        fixed = by_accession[filing["accession"]]
        fixed.update(parserVersion=PARSER_VERSION,
            records=[row.canonical_dump() for row in parsed.records], quarantines=[],
            repair={"previousFilingHash": _digest(filing), "previousCheckpointHash": parent_hash,
                    "previousParserVersion": filing["parserVersion"],
                    "replayedAt": repaired_at.isoformat(), "previousRecordCount": len(rows),
                    "resolvedRowKeys": actual})
    return validate_checkpoint(result, day=day)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--work", type=Path, default=Path("work/derivative-repair"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"status": "DRY_RUN", "day": args.day.isoformat(),
                          "operation": "verify original source and publish immutable repair"}))
        return
    store = ReleaseCheckpointStore(args.repository, target=args.target)
    original = store.latest(args.day)
    if original is None:
        raise ValueError("no original checkpoint to repair")
    source = SECDailyIndexSource(os.environ.get("SEC_USER_AGENT", ""),
                                cache_dir=args.work / "cache")
    try:
        fixed = repair_checkpoint(original, source, repaired_at=datetime.now(UTC))
        # No partial replacement is published if any targeted replay failed.
        receipt = store.persist(fixed)
        report = {"day": args.day.isoformat(), "changed": fixed != original, "receipt": receipt,
                  "quarantinesBefore": sum(len(p["quarantines"]) for p in original["filings"]),
                  "quarantinesAfter": sum(len(p["quarantines"]) for p in fixed["filings"]),
                  "failures": len(fixed["failures"]), "cursorAdvanced": False}
        _write_json(args.work / "repair-report.json", report)
        print(json.dumps(report, sort_keys=True))
    finally:
        source.close()


if __name__ == "__main__":
    main()
