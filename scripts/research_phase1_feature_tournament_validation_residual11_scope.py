"""Freeze F2 validation residual-11 scope after SPAC resolutions."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_ROWS = 19
EXPECTED_RESOLVED_ROWS = 8
EXPECTED_RESIDUAL_ROWS = 11
EXPECTED_SOURCE_DIGEST = (
    "sha256:612f62f79717037ecb858998a03cf5fb6d6ce927f308fd08f535af5eeb99945d"
)
EXPECTED_RESOLUTION_DIGEST = (
    "sha256:f08070c07a6bb411490e8f97b6413c5b498496d4f178067ceab5059db4d159c0"
)
EXPECTED_RESIDUAL_DIGEST = (
    "sha256:46381d68c3ad51f9d6d9d7a934d88d807c599f78712f34d4e210c9f4248e5d55"
)
KEY_FIELDS = (
    "eventNumber",
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
    return tuple(str(key[field]) for field in KEY_FIELDS)


def _digest(rows: list[dict[str, Any]]) -> str:
    lines = sorted(
        json.dumps(_key_object(row), sort_keys=True, separators=(",", ":"))
        for row in rows
    )
    return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _assert_boundary(payload: dict[str, Any], label: str) -> None:
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


def run(
    *,
    source_path: Path,
    resolution_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    resolution = json.loads(resolution_path.read_text(encoding="utf-8"))
    _assert_boundary(source, "residual-19")
    _assert_boundary(resolution, "SPAC resolution")

    if source.get("status") != (
        "PHASE1_FEATURE_TOURNAMENT_VALIDATION_RESIDUAL19_SCOPE_FROZEN"
    ):
        raise ValueError("residual-19 status changed")
    if source.get("residualRows") != EXPECTED_SOURCE_ROWS:
        raise ValueError("residual-19 row count changed")
    if source.get("scopeKeySha256") != EXPECTED_SOURCE_DIGEST:
        raise ValueError("residual-19 scope digest changed")

    if resolution.get("status") != (
        "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
        "SPAC_SHARE_EXCHANGE_PRIMARY_RESOLUTION_COMPLETE"
    ):
        raise ValueError("SPAC resolution status changed")
    if resolution.get("resolvedRows") != EXPECTED_RESOLVED_ROWS:
        raise ValueError("SPAC resolved count changed")
    if resolution.get("resolvedKeySha256") != EXPECTED_RESOLUTION_DIGEST:
        raise ValueError("SPAC resolution digest changed")

    source_rows = source.get("rows")
    resolved_rows = resolution.get("resolutionRows")
    if not isinstance(source_rows, list) or len(source_rows) != EXPECTED_SOURCE_ROWS:
        raise ValueError("residual-19 rows changed")
    if not isinstance(resolved_rows, list) or len(resolved_rows) != EXPECTED_RESOLVED_ROWS:
        raise ValueError("SPAC resolution rows changed")
    if _digest(source_rows) != EXPECTED_SOURCE_DIGEST:
        raise ValueError("residual-19 semantic keys changed")
    if _digest(resolved_rows) != EXPECTED_RESOLUTION_DIGEST:
        raise ValueError("SPAC resolution semantic keys changed")

    resolved_keys = {_key_tuple(row) for row in resolved_rows}
    residual = [
        row for row in source_rows if _key_tuple(row) not in resolved_keys
    ]
    if len(residual) != EXPECTED_RESIDUAL_ROWS:
        raise ValueError("residual-11 row count changed")
    if _digest(residual) != EXPECTED_RESIDUAL_DIGEST:
        raise ValueError("residual-11 semantic-key digest changed")

    categories = Counter(
        str((row.get("evidenceAudit") or {}).get("category") or "")
        for row in residual
    )
    expected_categories = {
        "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED": 10,
        "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED": 1,
    }
    if dict(sorted(categories.items())) != expected_categories:
        raise ValueError("residual-11 category partition changed")

    provider_rows = [
        row
        for row in residual
        if str((row.get("evidenceAudit") or {}).get("category") or "")
        == "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED"
    ]
    if len(provider_rows) != 1:
        raise ValueError("provider residual count changed")
    provider = provider_rows[0]
    if provider["ticker"] != "CBTX":
        raise ValueError("standalone provider ticker changed")
    if provider.get("candidateActionTypes") != ["name_changes"]:
        raise ValueError("CBTX action type changed")

    residual.sort(key=lambda row: (int(row["eventNumber"]), int(row["horizon"])))
    result = {
        "schemaVersion": "1.0.0",
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "RESIDUAL11_SCOPE_FROZEN"
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
        "subtractedSpacRows": EXPECTED_RESOLVED_ROWS,
        "residualRows": EXPECTED_RESIDUAL_ROWS,
        "scopeKeySha256": EXPECTED_RESIDUAL_DIGEST,
        "categoryCounts": expected_categories,
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
    compact = {key: value for key, value in result.items() if key != "rows"}
    print(json.dumps(compact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
