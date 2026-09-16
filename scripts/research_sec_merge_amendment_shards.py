"""Deterministically merge issuer-safe SEC amendment reconciliation shards.

The shard runner partitions by issuer CIK, so amendment chains and transaction
identities cannot cross shard boundaries.  The merge is therefore a stable
concatenation in shard-index order plus audited summary aggregation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

FILES = (
    "reconciled-all-revisions.jsonl",
    "effective-end-2022.jsonl",
    "amendment-linkage.jsonl",
    "quarantines.jsonl",
)
NUMERIC_SUMMARY_FIELDS = (
    "originalCanonicalRows",
    "transactionBearingAmendmentFilingsHydrated",
    "zeroTransactionAmendmentFilingsObserved",
    "amendmentCanonicalRows",
    "linkedAmendmentRows",
    "researchQuarantineRows",
    "resolverQuarantineRows",
    "reconciledRevisionRows",
    "effectiveRowsAtEndOfPeriod",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_summaries(root: Path, shard_count: int) -> list[tuple[Path, dict[str, Any]]]:
    indexed: dict[int, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(root.rglob("summary.json")):
        summary = json.loads(path.read_text(encoding="utf-8"))
        shard = summary.get("issuerShard")
        if not isinstance(shard, dict):
            continue
        index = int(shard["index"])
        count = int(shard["count"])
        if count != shard_count:
            raise ValueError(f"unexpected shard count in {path}: {count}")
        if index in indexed:
            raise ValueError(f"duplicate reconciliation shard index {index}")
        if summary.get("shardReconciliationComplete") is not True:
            raise ValueError(f"shard {index} is not complete")
        if summary.get("oosOpened") is not False:
            raise ValueError(f"shard {index} violated sealed OOS boundary")
        if summary.get("canonicalReady") is not False:
            raise ValueError(f"shard {index} unexpectedly marked canonicalReady")
        if summary.get("marketDataJoined") is not False:
            raise ValueError(f"shard {index} unexpectedly joined market data")
        if summary.get("signalReady") is not False:
            raise ValueError(f"shard {index} unexpectedly marked signalReady")
        indexed[index] = (path.parent, summary)
    expected = set(range(shard_count))
    if set(indexed) != expected:
        raise ValueError(f"missing shard outputs: {sorted(expected - set(indexed))}")
    return [indexed[index] for index in range(shard_count)]


def _concat(inputs: list[Path], output: Path) -> None:
    with output.open("wb") as target:
        for path in inputs:
            if not path.exists():
                raise ValueError(f"missing shard evidence file: {path}")
            with path.open("rb") as source:
                shutil.copyfileobj(source, target, length=1024 * 1024)


def merge(*, shard_root: Path, output: Path, shard_count: int) -> dict[str, Any]:
    shards = _load_summaries(shard_root, shard_count)
    output.mkdir(parents=True, exist_ok=True)

    evidence: list[dict[str, Any]] = []
    for index, (directory, summary) in enumerate(shards):
        file_hashes = {filename: _sha256(directory / filename) for filename in FILES}
        evidence.append(
            {
                "index": index,
                "summarySha256": _sha256(directory / "summary.json"),
                "files": file_hashes,
                "numericCounts": {
                    field: int(summary.get(field, 0)) for field in NUMERIC_SUMMARY_FIELDS
                },
            }
        )

    for filename in FILES:
        _concat([directory / filename for directory, _ in shards], output / filename)

    first = shards[0][1]
    for _, summary in shards[1:]:
        if summary.get("lifecycleHistoricalClockNormalization") != first.get(
            "lifecycleHistoricalClockNormalization"
        ):
            raise ValueError("lifecycle normalization policy differs across shards")
        if summary.get("linkagePolicy") != first.get("linkagePolicy"):
            raise ValueError("linkage policy differs across shards")

    status_counts: dict[str, int] = defaultdict(int)
    totals = {field: 0 for field in NUMERIC_SUMMARY_FIELDS}
    for _, summary in shards:
        for field in NUMERIC_SUMMARY_FIELDS:
            totals[field] += int(summary.get(field, 0))
        for status, count in summary.get("linkageStatusCounts", {}).items():
            status_counts[str(status)] += int(count)

    summary: dict[str, Any] = {
        "schemaVersion": "1.2.0",
        "dataset": "SEC PIT amendment reconciliation research",
        "period": "2013-2022",
        **totals,
        "linkageStatusCounts": dict(sorted(status_counts.items())),
        "issuerSharding": {
            "count": shard_count,
            "method": "sha256(issuer_cik)[0:8] mod shard_count",
            "chainBoundaryInvariant": "issuer identity is required for every amendment predecessor/successor link",
        },
        "shardEvidence": evidence,
        "mergedFileSha256": {filename: _sha256(output / filename) for filename in FILES},
        "lifecycleHistoricalClockNormalization": first[
            "lifecycleHistoricalClockNormalization"
        ],
        "linkagePolicy": first["linkagePolicy"],
        "amendmentReconciliationComplete": True,
        "canonicalReady": False,
        "marketDataJoined": False,
        "signalReady": False,
        "oosOpened": False,
        "nextGate": "historical adjusted/delisted market-data join",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            merge(
                shard_root=args.shard_root,
                output=args.output,
                shard_count=args.shard_count,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
