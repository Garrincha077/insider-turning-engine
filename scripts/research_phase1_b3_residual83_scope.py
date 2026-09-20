"""Freeze B3 residual-83 scope after SPAC-unit resolution subtraction."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

SOURCE_SCOPE_KEY_SHA256 = (
    "sha256:c28829aa56204db04633546d91b06b938d06f897cd022d2c8147f488415d2742"
)
SPAC_RESOLUTION_KEY_SHA256 = (
    "sha256:2d93f63e9002ef10c913315a7a30bde9377bebf95a7e0442ade39b496e12beba"
)
RESIDUAL83_KEY_SHA256 = (
    "sha256:d1758905bedc027e7f7448cbffed1bf9a35506b947bd8bdec77e48096f28adcd"
)
REMOVED_BUCKET = (
    "TICKER_CHANGED_AFTER_PIVOT|TITLE_SET_EXACT_MATCH|"
    "TICKER_CHANGED_AFTER_PIVOT"
)


def _load_scope(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "B3_RESIDUAL87_SCOPE_FROZEN":
        raise ValueError("unexpected residual-87 scope status")
    if payload.get("residualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-87 key digest changed")
    if payload.get("performanceRead") is not False:
        raise ValueError("residual-87 source is not performance-blind")
    if payload.get("priceFieldsRead") != []:
        raise ValueError("residual-87 source read price fields")
    if payload.get("oosOpened") is not False:
        raise ValueError("residual-87 source opened OOS")
    if payload.get("productionScoringChanged") is not False:
        raise ValueError("residual-87 source changed production scoring")

    columns = payload["scopeColumns"]
    rows = [
        dict(zip(columns, values, strict=True))
        for values in payload["scopeRows"]
    ]
    if len(rows) != 87 or base._key_digest(rows) != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-87 scope content changed")
    return payload, rows


def _load_spac_resolution(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "B3_SPAC_UNIT_PRIMARY_RESOLUTION_COMPLETE":
        raise ValueError("unexpected SPAC-unit resolution status")
    if payload.get("resolvedRows") != 4:
        raise ValueError("SPAC-unit resolved row count changed")
    if payload.get("resolutionKeySha256") != SPAC_RESOLUTION_KEY_SHA256:
        raise ValueError("SPAC-unit resolution key digest changed")
    if payload.get("performanceRead") is not False:
        raise ValueError("SPAC-unit resolution is not performance-blind")
    if payload.get("priceFieldsRead") != []:
        raise ValueError("SPAC-unit resolution read price fields")
    if payload.get("oosOpened") is not False:
        raise ValueError("SPAC-unit resolution opened OOS")

    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != 4:
        raise ValueError("invalid SPAC-unit resolution rows")
    if base._key_digest(rows) != SPAC_RESOLUTION_KEY_SHA256:
        raise ValueError("SPAC-unit resolution rows changed")
    return rows


def freeze(
    *,
    scope_path: Path,
    spac_resolution_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    source_payload, source_rows = _load_scope(scope_path)
    resolved = _load_spac_resolution(spac_resolution_path)

    resolved_keys = {base._row_key(row) for row in resolved}
    source_keys = {base._row_key(row) for row in source_rows}
    if not resolved_keys < source_keys:
        raise ValueError("SPAC-unit resolutions are not a strict source subset")

    residual = [
        row for row in source_rows
        if base._row_key(row) not in resolved_keys
    ]
    if len(residual) != 83:
        raise ValueError("SPAC-unit subtraction did not produce 83 rows")
    if base._key_digest(residual) != RESIDUAL83_KEY_SHA256:
        raise ValueError("residual-83 key digest mismatch")
    if any(row["evidenceBucket"] == REMOVED_BUCKET for row in residual):
        raise ValueError("resolved SPAC-unit bucket remained in residual-83 scope")

    pairs = sorted({(str(row["issuerCik"]), str(row["ticker"])) for row in residual})
    if len(pairs) != 31:
        raise ValueError("unexpected residual-83 issuer/ticker identity count")

    buckets = Counter(str(row["evidenceBucket"]) for row in residual)

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_RESIDUAL83_SCOPE_FROZEN",
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
        "sourceResidual87KeySha256": SOURCE_SCOPE_KEY_SHA256,
        "spacResolutionKeySha256": SPAC_RESOLUTION_KEY_SHA256,
        "sourceRows": 87,
        "subtractedSpacRows": 4,
        "residualRows": 83,
        "uniqueIssuerTickerPairs": 31,
        "residualKeySha256": RESIDUAL83_KEY_SHA256,
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
    parser.add_argument("--spac-resolution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            freeze(
                scope_path=args.scope,
                spac_resolution_path=args.spac_resolution,
                output_path=args.output,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
