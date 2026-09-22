"""Freeze the 19-row F2 validation residual after incomplete stock mergers."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_ROWS = 27
EXPECTED_RESOLVED_ROWS = 8
EXPECTED_RESIDUAL_ROWS = 19
EXPECTED_SOURCE_DIGEST = (
    "sha256:683086e2a4ba61f734b45a22a24371f3f2a5ffa0f1fd74e7e9576275ab32da9f"
)
EXPECTED_RESOLUTION_DIGEST = (
    "sha256:31296aeae352b58fc55a6eba4cbfaf2fa0d600134a004afcf6c7980782a5b776"
)
EXPECTED_RESIDUAL_DIGEST = (
    "sha256:612f62f79717037ecb858998a03cf5fb6d6ce927f308fd08f535af5eeb99945d"
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
    _assert_boundary(payload, label="residual-27")
    if payload.get("status") != (
        "PHASE1_FEATURE_TOURNAMENT_VALIDATION_RESIDUAL27_SCOPE_FROZEN"
    ):
        raise ValueError("residual-27 status changed")
    if payload.get("residualRows") != EXPECTED_SOURCE_ROWS:
        raise ValueError("residual-27 row count changed")
    if payload.get("scopeKeySha256") != EXPECTED_SOURCE_DIGEST:
        raise ValueError("residual-27 digest changed")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_SOURCE_ROWS:
        raise ValueError("residual-27 rows changed")
    if _digest(rows) != EXPECTED_SOURCE_DIGEST:
        raise ValueError("residual-27 semantic keys changed")
    return [dict(row) for row in rows]


def _load_resolution(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _assert_boundary(payload, label="incomplete stock-merger resolution")
    if payload.get("status") != (
        "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
        "INCOMPLETE_STOCK_MERGER_PRIMARY_RESOLUTION_COMPLETE"
    ):
        raise ValueError("incomplete stock-merger resolution status changed")
    if payload.get("sourceResidualRows") != EXPECTED_SOURCE_ROWS:
        raise ValueError("incomplete stock-merger source count changed")
    if payload.get("resolvedRows") != EXPECTED_RESOLVED_ROWS:
        raise ValueError("incomplete stock-merger resolved count changed")
    if payload.get("remainingUnresolvedRows") != EXPECTED_RESIDUAL_ROWS:
        raise ValueError("incomplete stock-merger remaining count changed")
    if payload.get("resolvedKeySha256") != EXPECTED_RESOLUTION_DIGEST:
        raise ValueError("incomplete stock-merger digest changed")
    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_RESOLVED_ROWS:
        raise ValueError("incomplete stock-merger resolution rows changed")
    if _digest(rows) != EXPECTED_RESOLUTION_DIGEST:
        raise ValueError("incomplete stock-merger key set changed")
    return [dict(row) for row in rows]


def _wave_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "nameChangeStockMergerRows": 0,
        "standaloneNameChangeRows": 0,
        "longGapRows": 0,
    }
    for row in rows:
        category = str((row.get("evidenceAudit") or {}).get("category") or "")
        action_types = sorted(str(item) for item in row.get("candidateActionTypes") or [])
        if category == "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED":
            counts["longGapRows"] += 1
        elif action_types == ["name_changes", "stock_mergers"]:
            counts["nameChangeStockMergerRows"] += 1
        elif action_types == ["name_changes"]:
            counts["standaloneNameChangeRows"] += 1
        else:
            raise ValueError(
                f"unrecognized residual-19 wave: {row.get('ticker')} {action_types}"
            )
    return counts


def run(*, source_path: Path, resolution_path: Path, output_path: Path) -> dict[str, Any]:
    source_rows = _load_source(source_path)
    resolved_rows = _load_resolution(resolution_path)

    source_keys = {_key_tuple(row) for row in source_rows}
    resolved_keys = {_key_tuple(row) for row in resolved_rows}
    if len(source_keys) != EXPECTED_SOURCE_ROWS:
        raise ValueError("duplicate residual-27 keys")
    if len(resolved_keys) != EXPECTED_RESOLVED_ROWS:
        raise ValueError("duplicate resolution keys")
    if not resolved_keys.issubset(source_keys):
        raise ValueError("resolution keys absent from residual-27")

    residual = [row for row in source_rows if _key_tuple(row) not in resolved_keys]
    if len(residual) != EXPECTED_RESIDUAL_ROWS:
        raise ValueError("residual-19 row count changed")
    if _digest(residual) != EXPECTED_RESIDUAL_DIGEST:
        raise ValueError("residual-19 semantic-key digest changed")

    categories = Counter(
        str((row.get("evidenceAudit") or {}).get("category") or "")
        for row in residual
    )
    expected_categories = {
        "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED": 10,
        "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED": 9,
    }
    if dict(sorted(categories.items())) != expected_categories:
        raise ValueError("residual-19 category partition changed")

    waves = _wave_counts(residual)
    expected_waves = {
        "nameChangeStockMergerRows": 8,
        "standaloneNameChangeRows": 1,
        "longGapRows": 10,
    }
    if waves != expected_waves:
        raise ValueError("residual-19 wave partition changed")

    residual.sort(key=lambda row: (int(row["eventNumber"]), int(row["horizon"])))
    result = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_VALIDATION_RESIDUAL19_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": EXPECTED_SOURCE_ROWS,
        "subtractedIncompleteStockMergerRows": EXPECTED_RESOLVED_ROWS,
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
