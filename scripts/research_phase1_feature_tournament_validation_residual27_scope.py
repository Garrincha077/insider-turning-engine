"""Freeze the 27-row F2 validation residual after stock dividends."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_ROWS = 32
EXPECTED_RESOLVED_ROWS = 5
EXPECTED_RESIDUAL_ROWS = 27
EXPECTED_SOURCE_DIGEST = (
    "sha256:4b8d0df8ff1d06f018fdcbdf281b9fa2be05f21e77b57682012b36b419049e34"
)
EXPECTED_RESOLUTION_DIGEST = (
    "sha256:7dd0615edd13ae996379d9c49194a45edbeda6e5bcf418e1b47c948540a562a3"
)
EXPECTED_RESIDUAL_DIGEST = (
    "sha256:683086e2a4ba61f734b45a22a24371f3f2a5ffa0f1fd74e7e9576275ab32da9f"
)

KEY_FIELDS = (
    "eventNumber", "issuerCik", "ticker", "evaluationSession",
    "entrySession", "horizon", "targetExitSession",
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
    return tuple(str(key[field]) for field in KEY_FIELDS)


def _digest(rows: list[dict[str, Any]]) -> str:
    lines = sorted(
        json.dumps(_key_object(row), sort_keys=True, separators=(",", ":"))
        for row in rows
    )
    return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _assert_boundary(payload: dict[str, Any], *, label: str) -> None:
    required = {
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"{label} boundary mismatch: {key}")


def _load_source(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _assert_boundary(payload, label="residual-32")
    if payload.get("status") != (
        "PHASE1_FEATURE_TOURNAMENT_VALIDATION_RESIDUAL32_SCOPE_FROZEN"
    ):
        raise ValueError("residual-32 status changed")
    if payload.get("residualRows") != EXPECTED_SOURCE_ROWS:
        raise ValueError("residual-32 row count changed")
    if payload.get("scopeKeySha256") != EXPECTED_SOURCE_DIGEST:
        raise ValueError("residual-32 digest changed")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_SOURCE_ROWS:
        raise ValueError("residual-32 rows changed")
    return [dict(row) for row in rows]


def _load_resolution(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _assert_boundary(payload, label="stock-dividend resolution")
    if payload.get("status") != (
        "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
        "STOCK_DIVIDEND_PRIMARY_RESOLUTION_COMPLETE"
    ):
        raise ValueError("stock-dividend resolution status changed")
    if payload.get("sourceResidualRows") != EXPECTED_SOURCE_ROWS:
        raise ValueError("stock-dividend source count changed")
    if payload.get("resolvedRows") != EXPECTED_RESOLVED_ROWS:
        raise ValueError("stock-dividend resolved count changed")
    if payload.get("remainingUnresolvedRows") != EXPECTED_RESIDUAL_ROWS:
        raise ValueError("stock-dividend remaining count changed")
    if payload.get("resolvedKeySha256") != EXPECTED_RESOLUTION_DIGEST:
        raise ValueError("stock-dividend resolved digest changed")
    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_RESOLVED_ROWS:
        raise ValueError("stock-dividend resolution rows changed")
    if _digest(rows) != EXPECTED_RESOLUTION_DIGEST:
        raise ValueError("stock-dividend resolution key set changed")
    return [dict(row) for row in rows]


def _wave_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "incompleteStockMergerRows": 0,
        "nameChangeStockMergerRows": 0,
        "standaloneNameChangeRows": 0,
        "longGapRows": 0,
    }
    for row in rows:
        category = str((row.get("evidenceAudit") or {}).get("category") or "")
        action_types = sorted(str(item) for item in row.get("candidateActionTypes") or [])
        source = str(row.get("resolutionSource") or "")
        if category == "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED":
            counts["longGapRows"] += 1
        elif source == "provider_incomplete_terms" and action_types == ["stock_mergers"]:
            counts["incompleteStockMergerRows"] += 1
        elif action_types == ["name_changes", "stock_mergers"]:
            counts["nameChangeStockMergerRows"] += 1
        elif action_types == ["name_changes"]:
            counts["standaloneNameChangeRows"] += 1
        else:
            raise ValueError(
                f"unrecognized residual-27 wave: {row.get('ticker')} "
                f"{action_types} {source}"
            )
    return counts


def run(*, source_path: Path, resolution_path: Path, output_path: Path) -> dict[str, Any]:
    source_rows = _load_source(source_path)
    resolved_rows = _load_resolution(resolution_path)
    source_keys = {_key_tuple(row) for row in source_rows}
    resolved_keys = {_key_tuple(row) for row in resolved_rows}
    if len(source_keys) != EXPECTED_SOURCE_ROWS:
        raise ValueError("duplicate residual-32 keys")
    if len(resolved_keys) != EXPECTED_RESOLVED_ROWS:
        raise ValueError("duplicate stock-dividend keys")
    if not resolved_keys.issubset(source_keys):
        raise ValueError("stock-dividend keys absent from residual-32")

    residual = [row for row in source_rows if _key_tuple(row) not in resolved_keys]
    if len(residual) != EXPECTED_RESIDUAL_ROWS:
        raise ValueError("residual-27 row count changed")
    if _digest(residual) != EXPECTED_RESIDUAL_DIGEST:
        raise ValueError("residual-27 semantic-key digest changed")

    categories = Counter(
        str((row.get("evidenceAudit") or {}).get("category") or "")
        for row in residual
    )
    expected_categories = {
        "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED": 10,
        "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED": 17,
    }
    if dict(sorted(categories.items())) != expected_categories:
        raise ValueError("residual-27 category partition changed")

    waves = _wave_counts(residual)
    expected_waves = {
        "incompleteStockMergerRows": 8,
        "nameChangeStockMergerRows": 8,
        "standaloneNameChangeRows": 1,
        "longGapRows": 10,
    }
    if waves != expected_waves:
        raise ValueError("residual-27 wave partition changed")

    residual.sort(key=lambda row: (int(row["eventNumber"]), int(row["horizon"])))
    result = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_VALIDATION_RESIDUAL27_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": EXPECTED_SOURCE_ROWS,
        "subtractedStockDividendRows": EXPECTED_RESOLVED_ROWS,
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
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
