"""Freeze the residual feature-tournament continuity scope after safe prior reuse."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_ROWS = 210
EXPECTED_SAFE_ROWS = 175
EXPECTED_CONFLICT_ROWS = 1
EXPECTED_UNMATCHED_ROWS = 34
EXPECTED_RESIDUAL_ROWS = EXPECTED_CONFLICT_ROWS + EXPECTED_UNMATCHED_ROWS
SEALED_YEAR = 2023
SAFE_STATUS = "SAFE_PRIOR_ECONOMIC_MATCH"
CONFLICT_STATUS = "PRIOR_ECONOMIC_CONFLICT"
UNMATCHED_STATUS = "NO_PRIOR_EVIDENCE_MATCH"
KEY_FIELDS = (
    "issuerCik",
    "ticker",
    "evaluationSession",
    "entrySession",
    "horizon",
    "targetExitSession",
)


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


def _assert_date(value: object, field: str) -> None:
    text = str(value or "")
    if len(text) < 10:
        raise ValueError(f"invalid {field}")
    if int(text[:4]) >= SEALED_YEAR:
        raise ValueError(f"sealed OOS boundary violated by {field}")


def run(*, overlap_path: Path, output_path: Path) -> dict[str, Any]:
    source = json.loads(overlap_path.read_text(encoding="utf-8"))
    required = {
        "status": "PHASE1_FEATURE_TOURNAMENT_PRIOR_CONTINUITY_OVERLAP_V2_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": EXPECTED_SOURCE_ROWS,
        "safeReusableRows": EXPECTED_SAFE_ROWS,
        "conflictingPriorRows": EXPECTED_CONFLICT_ROWS,
        "unmatchedRows": EXPECTED_UNMATCHED_ROWS,
        "resolutionApplied": False,
        "featureDiscoveryOutcomesOpened": False,
    }
    for key, expected in required.items():
        if source.get(key) != expected:
            raise ValueError(f"overlap source mismatch: {key}")

    rows = source.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_SOURCE_ROWS:
        raise ValueError("overlap row count changed")

    residual = [
        row
        for row in rows
        if row.get("matchStatus") in {CONFLICT_STATUS, UNMATCHED_STATUS}
    ]
    if len(residual) != EXPECTED_RESIDUAL_ROWS:
        raise ValueError("residual row count changed")

    status_counts = Counter(str(row["matchStatus"]) for row in residual)
    if status_counts[CONFLICT_STATUS] != EXPECTED_CONFLICT_ROWS:
        raise ValueError("conflict row count changed")
    if status_counts[UNMATCHED_STATUS] != EXPECTED_UNMATCHED_ROWS:
        raise ValueError("unmatched row count changed")

    for row in residual:
        for field in ("evaluationSession", "entrySession", "targetExitSession"):
            _assert_date(row[field], field)

    residual.sort(
        key=lambda row: (
            str(row["issuerCik"]),
            str(row["ticker"]),
            str(row["entrySession"]),
            int(row["horizon"]),
        )
    )

    by_horizon = Counter(str(row["horizon"]) for row in residual)
    by_current_source = Counter(
        str(row.get("currentResolutionSource") or "") for row in residual
    )
    identities: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"rows": 0, "statuses": Counter(), "horizons": Counter()}
    )
    for row in residual:
        key = (str(row["issuerCik"]), str(row["ticker"]).upper())
        identities[key]["rows"] += 1
        identities[key]["statuses"][str(row["matchStatus"])] += 1
        identities[key]["horizons"][str(row["horizon"])] += 1

    identity_rows = [
        {
            "issuerCik": cik,
            "ticker": ticker,
            "rows": data["rows"],
            "statuses": dict(sorted(data["statuses"].items())),
            "horizons": dict(sorted(data["horizons"].items())),
        }
        for (cik, ticker), data in sorted(identities.items())
    ]

    payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_RESIDUAL_CONTINUITY_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": EXPECTED_SOURCE_ROWS,
        "safePriorEvidenceRows": EXPECTED_SAFE_ROWS,
        "residualRows": len(residual),
        "conflictingPriorRows": status_counts[CONFLICT_STATUS],
        "unmatchedRows": status_counts[UNMATCHED_STATUS],
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
        "rowsByCurrentResolutionSource": dict(sorted(by_current_source.items())),
        "residualSemanticKeySha256": _digest(residual),
        "identities": identity_rows,
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
    parser.add_argument("--overlap", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(overlap_path=args.overlap, output_path=args.output)
    compact = {key: value for key, value in result.items() if key != "rows"}
    print(json.dumps(compact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
