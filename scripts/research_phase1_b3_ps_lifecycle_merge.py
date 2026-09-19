"""Merge issuer-safe B3 P/S lifecycle reconciliation shards."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

FILES = (
    "reconciled-ps-revisions.jsonl",
    "effective-ps-end-2022.jsonl",
    "amendment-linkage.jsonl",
    "zero-transaction-classification.jsonl",
    "quarantines.jsonl",
)
NUMERIC = (
    "originalPsCanonicalRows",
    "supportingPredecessorCanonicalRows",
    "transactionBearingAmendmentCanonicalRows",
    "transactionBearingAmendmentFilingsHydrated",
    "linkedAmendmentRows",
    "zeroTransactionAmendmentsOnPsRoots",
    "zeroLifecycleActionsApplied",
    "qualifiedBuyRowsAddedByAmendment",
    "qualifiedBuyRowsRemovedByAmendment",
    "qualifiedBuyRowsCorrectedByAmendment",
    "qualifiedSaleRowsAddedByAmendment",
    "qualifiedSaleRowsRemovedByAmendment",
    "qualifiedSaleRowsCorrectedByAmendment",
    "researchQuarantineRows",
    "resolverQuarantineRows",
    "reconciledRevisionRows",
    "effectiveQualifiedPsRowsAtEndOf2022",
)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _concat(paths: list[Path], out: Path) -> None:
    with out.open("wb") as target:
        for path in paths:
            with path.open("rb") as source:
                shutil.copyfileobj(source, target, length=1024 * 1024)


def merge(*, shard_root: Path, output: Path, shard_count: int) -> dict[str, Any]:
    indexed: dict[int, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(shard_root.rglob("summary.json")):
        s = json.loads(path.read_text())
        shard = s.get("issuerShard")
        if not isinstance(shard, dict):
            continue
        idx, count = int(shard["index"]), int(shard["count"])
        if count != shard_count or idx in indexed:
            raise ValueError("invalid or duplicate lifecycle shard")
        for flag in (
            "zeroTransactionSemanticReviewComplete",
            "supportingPredecessorHydrationComplete",
            "fullPsHistoryComplete",
            "amendmentsReconciledForPsUniverse",
        ):
            if s.get(flag) is not True:
                raise ValueError(f"shard {idx} failed {flag}")
        if s.get("oosOpened") is not False or s.get("productionScoringChanged") is not False:
            raise ValueError(f"shard {idx} violated research boundary")
        indexed[idx] = (path.parent, s)
    if set(indexed) != set(range(shard_count)):
        raise ValueError("missing lifecycle shards")
    shards = [indexed[i] for i in range(shard_count)]
    output.mkdir(parents=True, exist_ok=True)
    for filename in FILES:
        _concat([directory / filename for directory, _ in shards], output / filename)

    totals = {field: 0 for field in NUMERIC}
    zero_counts: dict[str, int] = defaultdict(int)
    linkage_counts: dict[str, int] = defaultdict(int)
    evidence: list[dict[str, Any]] = []
    for idx, (directory, s) in enumerate(shards):
        for field in NUMERIC:
            totals[field] += int(s.get(field, 0))
        for key, value in s.get("zeroTransactionClassificationCounts", {}).items():
            zero_counts[str(key)] += int(value)
        for key, value in s.get("linkageStatusCounts", {}).items():
            linkage_counts[str(key)] += int(value)
        evidence.append(
            {
                "index": idx,
                "summarySha256": _sha(directory / "summary.json"),
                "files": {name: _sha(directory / name) for name in FILES},
            }
        )

    if totals["zeroTransactionAmendmentsOnPsRoots"] != 596:
        raise ValueError("zero-transaction scope count changed")
    if sum(zero_counts.values()) != 596:
        raise ValueError("not every zero-transaction amendment was classified")

    summary = {
        "schemaVersion": "1.0.0",
        "dataset": "B3 P/S deterministic amendment lifecycle reconciliation",
        "period": "2013-2022",
        **totals,
        "zeroTransactionClassificationCounts": dict(sorted(zero_counts.items())),
        "linkageStatusCounts": dict(sorted(linkage_counts.items())),
        "issuerSharding": {
            "count": shard_count,
            "method": "sha256(issuer_cik)[0:8] mod shard_count",
        },
        "shardEvidence": evidence,
        "mergedFileSha256": {name: _sha(output / name) for name in FILES},
        "zeroTransactionSemanticReviewComplete": True,
        "supportingPredecessorHydrationComplete": True,
        "fullPsHistoryComplete": True,
        "amendmentsReconciledForPsUniverse": True,
        "b3Eligible": False,
        "b3DefinitionFrozen": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "canonicalReady": False,
        "marketDataJoined": False,
        "signalReady": False,
        "status": "B3_PS_AMENDMENT_RECONCILIATION_PASS",
        "nextGate": "freeze B3 company-net-buying definition before development performance",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(merge(
        shard_root=args.shard_root,
        output=args.output,
        shard_count=args.shard_count,
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
