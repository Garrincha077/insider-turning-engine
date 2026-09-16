"""Run one deterministic issuer shard of the research-only SEC amendment reconciler.

Amendment chains cannot cross issuer CIKs: the production resolver requires issuer
identity for every predecessor/successor link.  We therefore partition by a stable
SHA-256 bucket of issuer CIK, keeping every complete chain in exactly one shard.

This is research infrastructure only.  It does not open 2023+ OOS data and does
not modify production parsing, scoring, thresholds, or signals.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import research_sec_reconcile_amendments_v2 as core


def _bucket(issuer_cik: str, shard_count: int) -> int:
    digest = hashlib.sha256(str(issuer_cik).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % shard_count


def _issuer_cik(row: dict[str, Any], filename: str) -> str:
    if filename == "canonical-research.jsonl":
        issuer = row.get("issuer")
        if not isinstance(issuer, dict) or not issuer.get("cik"):
            raise ValueError("canonical research row is missing issuer.cik")
        return str(issuer["cik"])
    issuer_cik = row.get("issuerCik")
    if issuer_cik in (None, ""):
        raise ValueError(f"{filename} row is missing issuerCik")
    return str(issuer_cik)


def reconcile_shard(
    *,
    original_root: Path,
    amendment_root: Path,
    catalog_root: Path,
    output: Path,
    shard_index: int,
    shard_count: int,
) -> dict[str, Any]:
    if shard_count <= 1:
        raise ValueError("shard_count must be greater than 1")
    if not 0 <= shard_index < shard_count:
        raise ValueError("shard_index must satisfy 0 <= index < shard_count")

    original_read_all = core._read_all

    def filtered_read_all(root: Path, filename: str) -> list[dict[str, Any]]:
        rows = original_read_all(root, filename)
        selected: list[dict[str, Any]] = []
        for row in rows:
            issuer_cik = _issuer_cik(row, filename)
            if _bucket(issuer_cik, shard_count) == shard_index:
                selected.append(row)
        return selected

    core._read_all = filtered_read_all
    try:
        summary = core.reconcile(
            original_root=original_root,
            amendment_root=amendment_root,
            catalog_root=catalog_root,
            output=output,
        )
    finally:
        core._read_all = original_read_all

    summary["issuerShard"] = {
        "index": shard_index,
        "count": shard_count,
        "method": "sha256(issuer_cik)[0:8] mod shard_count",
    }
    summary["shardReconciliationComplete"] = True
    summary["amendmentReconciliationComplete"] = False
    summary["globalMergeRequired"] = True
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--amendment-root", type=Path, required=True)
    parser.add_argument("--catalog-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            reconcile_shard(
                original_root=args.original_root,
                amendment_root=args.amendment_root,
                catalog_root=args.catalog_root,
                output=args.output,
                shard_index=args.shard_index,
                shard_count=args.shard_count,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
