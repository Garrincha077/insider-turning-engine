"""Freeze the exact 34-row residual continuity scope after POPE adjudication."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

RESIDUAL35_DIGEST = (
    "sha256:bba0f3fd8c46c04e0ccd27a6b6a2a6ac0f8fcf074d89fee7239d5477f0574e01"
)
POPE_ADJUDICATION_DIGEST = (
    "sha256:8c87c27a3689c1aa10c5d8881cf91de0bb078e97d6133968f1c7d0528afd18a4"
)
EXPECTED_ROWS = 34
KEY_FIELDS = (
    "issuerCik",
    "ticker",
    "evaluationSession",
    "entrySession",
    "horizon",
    "targetExitSession",
)


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row[field]) for field in KEY_FIELDS)


def _digest(rows: list[dict[str, Any]]) -> str:
    lines = sorted(
        json.dumps(
            {field: row[field] for field in KEY_FIELDS},
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in rows
    )
    return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()


def run(
    *,
    residual35_path: Path,
    pope_adjudication_path: Path,
    output_path: Path,
    verify_frozen_assets: bool = True,
) -> dict[str, Any]:
    if verify_frozen_assets:
        if _sha(residual35_path) != RESIDUAL35_DIGEST:
            raise ValueError("residual35 asset digest changed")
        if _sha(pope_adjudication_path) != POPE_ADJUDICATION_DIGEST:
            raise ValueError("POPE adjudication asset digest changed")

    source = json.loads(residual35_path.read_text(encoding="utf-8"))
    pope = json.loads(pope_adjudication_path.read_text(encoding="utf-8"))

    source_required = {
        "status": "PHASE1_FEATURE_TOURNAMENT_RESIDUAL_CONTINUITY_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "residualRows": 35,
        "conflictingPriorRows": 1,
        "unmatchedRows": 34,
        "resolutionComplete": False,
        "featureDiscoveryOutcomesOpened": False,
    }
    for key, expected in source_required.items():
        if source.get(key) != expected:
            raise ValueError(f"residual35 contract mismatch: {key}")

    pope_required = {
        "status": "PHASE1_FEATURE_TOURNAMENT_POPE_CONFLICT_ADJUDICATED",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "safePriorEvidenceRows": 175,
        "conflictRows": 1,
        "adjudicatedRows": 1,
        "remainingPOPEConflictRows": 0,
        "remainingPrimaryEvidenceRows": 34,
        "adjudicated": True,
        "resolutionCompleteForPOPE": True,
        "featureDiscoveryOutcomesOpened": False,
    }
    for key, expected in pope_required.items():
        if pope.get(key) != expected:
            raise ValueError(f"POPE adjudication mismatch: {key}")

    rows = source.get("rows")
    resolution = pope.get("resolution")
    if not isinstance(rows, list) or len(rows) != 35:
        raise ValueError("residual35 rows changed")
    if not isinstance(resolution, dict):
        raise ValueError("missing POPE resolution")

    pope_key = _key(resolution)
    matching = [row for row in rows if _key(row) == pope_key]
    if len(matching) != 1:
        raise ValueError("POPE adjudicated key must match exactly one residual row")
    if matching[0].get("matchStatus") != "PRIOR_ECONOMIC_CONFLICT":
        raise ValueError("POPE source row is not the frozen conflict")

    residual = [row for row in rows if _key(row) != pope_key]
    if len(residual) != EXPECTED_ROWS:
        raise ValueError("residual34 row count changed")
    if any(row.get("matchStatus") != "NO_PRIOR_EVIDENCE_MATCH" for row in residual):
        raise ValueError("residual34 contains a previously matched prior row")

    residual.sort(
        key=lambda row: (
            str(row["issuerCik"]),
            str(row["ticker"]),
            str(row["entrySession"]),
            int(row["horizon"]),
        )
    )
    by_horizon = Counter(str(row["horizon"]) for row in residual)
    by_source = Counter(
        str(row.get("currentResolutionSource") or "") for row in residual
    )

    payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_RESIDUAL34_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidual35Rows": 35,
        "safePriorEvidenceRows": 175,
        "popeAdjudicatedRows": 1,
        "residualRows": len(residual),
        "residualUniqueEvents": len(
            {
                (
                    row["issuerCik"],
                    row["ticker"],
                    row["evaluationSession"],
                    row["entrySession"],
                )
                for row in residual
            }
        ),
        "residualUniqueIssuers": len({row["issuerCik"] for row in residual}),
        "residualUniqueTickers": len({row["ticker"] for row in residual}),
        "rowsByHorizon": dict(sorted(by_horizon.items())),
        "rowsByCurrentResolutionSource": dict(sorted(by_source.items())),
        "residualSemanticKeySha256": _digest(residual),
        "rows": residual,
        "resolutionComplete": False,
        "featureDiscoveryOutcomesOpened": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--residual35", type=Path, required=True)
    parser.add_argument("--pope-adjudication", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        residual35_path=args.residual35,
        pope_adjudication_path=args.pope_adjudication,
        output_path=args.output,
    )
    compact = {key: value for key, value in result.items() if key != "rows"}
    print(json.dumps(compact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
