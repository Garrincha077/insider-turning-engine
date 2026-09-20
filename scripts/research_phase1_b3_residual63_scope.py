"""Freeze B3 residual-63 scope after one-sided resolution subtraction."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

SOURCE_SCOPE_KEY_SHA256 = (
    "sha256:d1758905bedc027e7f7448cbffed1bf9a35506b947bd8bdec77e48096f28adcd"
)
ONE_SIDED_RESOLUTION_KEY_SHA256 = (
    "sha256:6380297ba23e117849914bb4e2f9e1956a53c22c65a6514d99e992537294861f"
)
RESIDUAL63_KEY_SHA256 = (
    "sha256:ed13976872da6522da2973a450a1f1c39e22cc19e2ffcc8367b9cc1a1b016b50"
)
REMOVED_BUCKET = (
    "BEFORE_ONLY_EXPECTED_TICKER|ONE_SIDED_ACCESSION_ONLY|"
    "EXPECTED_TICKER_BOTH_SIDES"
)


def _load_scope(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "B3_RESIDUAL83_SCOPE_FROZEN":
        raise ValueError("unexpected residual-83 scope status")
    if payload.get("residualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-83 key digest changed")
    if payload.get("performanceRead") is not False:
        raise ValueError("residual-83 source is not performance-blind")
    if payload.get("priceFieldsRead") != []:
        raise ValueError("residual-83 source read price fields")
    if payload.get("oosOpened") is not False:
        raise ValueError("residual-83 source opened OOS")
    if payload.get("productionScoringChanged") is not False:
        raise ValueError("residual-83 source changed production scoring")

    columns = payload["scopeColumns"]
    rows = [
        dict(zip(columns, values, strict=True))
        for values in payload["scopeRows"]
    ]
    if len(rows) != 83 or base._key_digest(rows) != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-83 scope content changed")
    return payload, rows


def _load_resolution(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "B3_ONE_SIDED_PRIMARY_RESOLUTION_COMPLETE":
        raise ValueError("unexpected one-sided resolution status")
    if payload.get("resolvedRows") != 20:
        raise ValueError("one-sided resolved row count changed")
    if payload.get("resolutionKeySha256") != ONE_SIDED_RESOLUTION_KEY_SHA256:
        raise ValueError("one-sided resolution key digest changed")
    if payload.get("performanceRead") is not False:
        raise ValueError("one-sided resolution is not performance-blind")
    if payload.get("priceFieldsRead") != []:
        raise ValueError("one-sided resolution read price fields")
    if payload.get("oosOpened") is not False:
        raise ValueError("one-sided resolution opened OOS")

    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != 20:
        raise ValueError("invalid one-sided resolution rows")
    if base._key_digest(rows) != ONE_SIDED_RESOLUTION_KEY_SHA256:
        raise ValueError("one-sided resolution rows changed")
    return rows


def freeze(
    *,
    scope_path: Path,
    resolution_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    source_payload, source_rows = _load_scope(scope_path)
    resolved = _load_resolution(resolution_path)

    resolved_keys = {base._row_key(row) for row in resolved}
    source_keys = {base._row_key(row) for row in source_rows}
    if not resolved_keys < source_keys:
        raise ValueError("one-sided resolutions are not a strict source subset")

    residual = [
        row for row in source_rows
        if base._row_key(row) not in resolved_keys
    ]
    if len(residual) != 63:
        raise ValueError("one-sided subtraction did not produce 63 rows")
    if base._key_digest(residual) != RESIDUAL63_KEY_SHA256:
        raise ValueError("residual-63 key digest mismatch")
    if any(row["evidenceBucket"] == REMOVED_BUCKET for row in residual):
        raise ValueError("resolved one-sided bucket remained in residual-63 scope")

    pairs = sorted({(str(row["issuerCik"]), str(row["ticker"])) for row in residual})
    if len(pairs) != 27:
        raise ValueError("unexpected residual-63 issuer/ticker identity count")

    buckets = Counter(str(row["evidenceBucket"]) for row in residual)

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_RESIDUAL63_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "developmentCohortYears": source_payload["developmentCohortYears"],
        "outcomeEnd": source_payload["outcomeEnd"],
        "sealedYear": source_payload["sealedYear"],
        "horizons": source_payload["horizons"],
        "primaryHorizon": source_payload["primaryHorizon"],
        "sourceResidual83KeySha256": SOURCE_SCOPE_KEY_SHA256,
        "oneSidedResolutionKeySha256": ONE_SIDED_RESOLUTION_KEY_SHA256,
        "sourceRows": 83,
        "subtractedOneSidedRows": 20,
        "residualRows": 63,
        "uniqueIssuerTickerPairs": 27,
        "residualKeySha256": RESIDUAL63_KEY_SHA256,
        "evidenceBucketCounts": dict(sorted(buckets.items())),
        "scopeColumns": source_payload["scopeColumns"],
        "scopeRows": [
            [row[column] for column in source_payload["scopeColumns"]]
            for row in residual
        ],
        "issuerTickerPairs": [
            {"issuerCik": cik, "ticker": ticker}
            for cik, ticker in pairs
        ],
        "autoExpansionAllowed": False,
        "finalResolutionContractCreated": False,
        "correctedPerformanceOpened": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--resolution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            freeze(
                scope_path=args.scope,
                resolution_path=args.resolution,
                output_path=args.output,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
