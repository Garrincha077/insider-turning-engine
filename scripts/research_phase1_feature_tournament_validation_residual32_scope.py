"""Freeze the 32-row F2 validation continuity residual after HSDT."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_ROWS = 33
EXPECTED_RESOLVED_ROWS = 1
EXPECTED_RESIDUAL_ROWS = 32
EXPECTED_SOURCE_DIGEST = (
    "sha256:9ee5091b18344e67b58fe567b92ce99d3f923e4df2829af935158947bdcae2a2"
)
EXPECTED_HSDT_DIGEST = (
    "sha256:2dec9e57b3e6927b9c387764e2bcbfe0955cb450e9a546dfb900bcd9c8e92827"
)
EXPECTED_RESIDUAL_DIGEST = (
    "sha256:4b8d0df8ff1d06f018fdcbdf281b9fa2be05f21e77b57682012b36b419049e34"
)

KEY_FIELDS = (
    "issuerCik",
    "ticker",
    "evaluationSession",
    "entrySession",
    "horizon",
    "targetExitSession",
)


def _key_object(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventNumber": int(row["eventNumber"]),
        "issuerCik": str(row["issuerCik"]),
        "ticker": str(row["ticker"]).upper(),
        "evaluationSession": str(row["evaluationSession"]),
        "entrySession": str(row["entrySession"]),
        "horizon": int(row["horizon"]),
        "targetExitSession": str(row["targetExitSession"]),
    }


def _key_tuple(row: dict[str, Any]) -> tuple[str, ...]:
    key = _key_object(row)
    return tuple(str(key[field]) for field in ("eventNumber", *KEY_FIELDS))


def _digest(rows: list[dict[str, Any]]) -> str:
    lines = sorted(
        json.dumps(_key_object(row), sort_keys=True, separators=(",", ":"))
        for row in rows
    )
    return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _assert_source(payload: dict[str, Any]) -> list[dict[str, Any]]:
    required = {
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "RESIDUAL33_SCOPE_FROZEN"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "residualRows": EXPECTED_SOURCE_ROWS,
        "scopeKeySha256": EXPECTED_SOURCE_DIGEST,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"residual-33 mismatch: {key}")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_SOURCE_ROWS:
        raise ValueError("residual-33 rows changed")
    return [dict(row) for row in rows]


def _assert_resolution(payload: dict[str, Any]) -> list[dict[str, Any]]:
    required = {
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "HSDT_PRIMARY_RESOLUTION_COMPLETE"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": EXPECTED_SOURCE_ROWS,
        "resolvedRows": EXPECTED_RESOLVED_ROWS,
        "remainingUnresolvedRows": EXPECTED_RESIDUAL_ROWS,
        "resolvedKeySha256": EXPECTED_HSDT_DIGEST,
        "resolutionApplied": True,
        "resolutionComplete": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"HSDT resolution mismatch: {key}")
    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_RESOLVED_ROWS:
        raise ValueError("HSDT resolution rows changed")
    if _digest(rows) != EXPECTED_HSDT_DIGEST:
        raise ValueError("HSDT resolution semantic key changed")
    return [dict(row) for row in rows]


def _wave_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    stock_dividend = 0
    incomplete_merger = 0
    combo_reorg = 0
    standalone_name = 0
    long_gap = 0

    for row in rows:
        category = str((row.get("evidenceAudit") or {}).get("category") or "")
        action_types = sorted(str(item) for item in row.get("candidateActionTypes") or [])
        source = str(row.get("resolutionSource") or "")
        if category == "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED":
            long_gap += 1
        elif action_types == ["stock_dividends"]:
            stock_dividend += 1
        elif source == "provider_incomplete_terms" and action_types == ["stock_mergers"]:
            incomplete_merger += 1
        elif action_types == ["name_changes", "stock_mergers"]:
            combo_reorg += 1
        elif action_types == ["name_changes"]:
            standalone_name += 1
        else:
            raise ValueError(
                f"unrecognized residual-32 routing shape: "
                f"{row.get('ticker')} {action_types} {source}"
            )

    return {
        "stockDividendRows": stock_dividend,
        "incompleteStockMergerRows": incomplete_merger,
        "nameChangeStockMergerRows": combo_reorg,
        "standaloneNameChangeRows": standalone_name,
        "longGapRows": long_gap,
    }


def run(
    *,
    source_path: Path,
    resolution_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    source_payload = json.loads(source_path.read_text(encoding="utf-8"))
    resolution_payload = json.loads(resolution_path.read_text(encoding="utf-8"))
    source_rows = _assert_source(source_payload)
    resolution_rows = _assert_resolution(resolution_payload)

    source_keys = {_key_tuple(row) for row in source_rows}
    resolved_keys = {_key_tuple(row) for row in resolution_rows}
    if len(source_keys) != EXPECTED_SOURCE_ROWS:
        raise ValueError("duplicate residual-33 semantic keys")
    if len(resolved_keys) != EXPECTED_RESOLVED_ROWS:
        raise ValueError("duplicate HSDT resolution semantic keys")
    if not resolved_keys.issubset(source_keys):
        raise ValueError("HSDT resolution key absent from residual-33")

    residual = [
        row for row in source_rows if _key_tuple(row) not in resolved_keys
    ]
    if len(residual) != EXPECTED_RESIDUAL_ROWS:
        raise ValueError("residual-32 row count changed")
    if _digest(residual) != EXPECTED_RESIDUAL_DIGEST:
        raise ValueError("residual-32 semantic-key digest changed")

    categories = Counter(
        str((row.get("evidenceAudit") or {}).get("category") or "")
        for row in residual
    )
    expected_categories = {
        "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED": 10,
        "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED": 22,
    }
    if dict(sorted(categories.items())) != expected_categories:
        raise ValueError("residual-32 category partition changed")

    waves = _wave_counts(residual)
    expected_waves = {
        "stockDividendRows": 5,
        "incompleteStockMergerRows": 8,
        "nameChangeStockMergerRows": 8,
        "standaloneNameChangeRows": 1,
        "longGapRows": 10,
    }
    if waves != expected_waves:
        raise ValueError("residual-32 wave partition changed")

    residual.sort(key=lambda row: (int(row["eventNumber"]), int(row["horizon"])))
    result = {
        "schemaVersion": "1.0.0",
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "RESIDUAL32_SCOPE_FROZEN"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": EXPECTED_SOURCE_ROWS,
        "subtractedHSDTRows": EXPECTED_RESOLVED_ROWS,
        "residualRows": EXPECTED_RESIDUAL_ROWS,
        "scopeKeySha256": EXPECTED_RESIDUAL_DIGEST,
        "categoryCounts": expected_categories,
        "waveCounts": expected_waves,
        "rows": residual,
        "resolutionComplete": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--resolution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        source_path=args.source,
        resolution_path=args.resolution,
        output_path=args.output,
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "rows"},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
