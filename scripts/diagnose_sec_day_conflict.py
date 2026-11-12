"""Read-only forensic comparison of verified, immutable SEC daily checkpoints.

Never fetches fresh SEC filings, writes Releases, changes a cursor, or publishes.
Only anonymous conflict summaries are printed; no accession or filer identifiers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, timedelta
from typing import Any

from insider_turning_engine.ingestion.sec.release_store import ReleaseCheckpointStore
from insider_turning_engine.pipeline.research_history import _filing_identity

_DAY_TAG = re.compile(r"^sec-day-v[12]-(\d{4}-\d{2}-\d{2})-[a-f0-9]{64}$")


def _record_diff(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    older = {row["source"]["sourceRowKey"]: row for row in left["records"]}
    newer = {row["source"]["sourceRowKey"]: row for row in right["records"]}
    shared = older.keys() & newer.keys()
    checked = ("transactionId", "revisionId", "issuer", "reportingOwner",
               "relationship", "security", "transaction", "quality")
    changed = sorted({field for key in shared for field in checked
                      if older[key].get(field) != newer[key].get(field)})
    return {
        "row_keys_equal": older.keys() == newer.keys(),
        "rows_only_first": len(older.keys() - newer.keys()),
        "rows_only_second": len(newer.keys() - older.keys()),
        "changed_record_fields": changed,
    }


def diagnose(store: ReleaseCheckpointStore, *, cutoff: date, lookback_days: int = 90,
             max_conflicts: int = 10) -> list[dict[str, Any]]:
    earliest = cutoff - timedelta(days=lookback_days - 1)
    days = sorted({date.fromisoformat(match.group(1))
                   for release in store._releases()
                   if (match := _DAY_TAG.fullmatch(release["tag_name"])) is not None
                   and earliest <= date.fromisoformat(match.group(1)) <= cutoff})
    print(f"DIAGNOSTIC: verified available SEC checkpoint days={len(days)}, "
          f"window={earliest}..{cutoff}", flush=True)
    seen: dict[str, tuple[date, dict[str, Any]]] = {}
    collisions: list[dict[str, Any]] = []
    for day in days:
        checkpoint = store.latest(day)
        if checkpoint is None:
            continue
        for filing in checkpoint["filings"]:
            accession = filing["accession"]
            previous = seen.get(accession)
            if previous is None:
                seen[accession] = (day, filing)
                continue
            previous_day, previous_filing = previous
            if _filing_identity(previous_filing) == _filing_identity(filing):
                continue
            old_id = _filing_identity(previous_filing)
            new_id = _filing_identity(filing)
            components = ("submission_hash", "parsed_records", "quarantines")
            diagnostic = {
                "first_day": previous_day.isoformat(),
                "duplicate_day": day.isoformat(),
                "accession_sha256_prefix": hashlib.sha256(accession.encode()).hexdigest()[:12],
                "changed_components": [key for key, a, b in zip(
                    components, old_id, new_id, strict=True) if a != b],
                "same_complete_submission_sha256":
                    old_id[0] == new_id[0],
                "parser_versions": [previous_filing["parserVersion"], filing["parserVersion"]],
                "same_filer_cik": (
                    previous_filing["provenance"]["filer_cik"]
                    == filing["provenance"]["filer_cik"]
                ),
                "same_primary_source_urls": (
                    sorted(row["source"]["sourceUrl"] for row in previous_filing["records"])
                    == sorted(row["source"]["sourceUrl"] for row in filing["records"])
                ),
                "record_counts": [len(previous_filing["records"]), len(filing["records"])],
                "quarantine_counts": [len(previous_filing["quarantines"]),
                                      len(filing["quarantines"])],
                **_record_diff(previous_filing, filing),
            }
            collisions.append(diagnostic)
            print("SEC_CONFLICT: " + json.dumps(diagnostic, sort_keys=True), flush=True)
            if len(collisions) >= max_conflicts:
                print("DIAGNOSTIC_LIMIT_REACHED", flush=True)
                return collisions
    print(f"DIAGNOSTIC_DONE: conflicts={len(collisions)}", flush=True)
    return collisions


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--cutoff", default=date.today().isoformat())
    parser.add_argument("--lookback-days", type=int, default=90)
    args = parser.parse_args()
    if args.lookback_days < 1 or args.lookback_days > 120:
        parser.error("lookback-days must be between 1 and 120")
    diagnose(
        ReleaseCheckpointStore(args.repository, target=args.target),
        cutoff=date.fromisoformat(args.cutoff), lookback_days=args.lookback_days,
    )
