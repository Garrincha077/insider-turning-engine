"""Freeze the exact unresolved Stage-B feature-tournament continuity scope."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_EVENTS = 24190
EXPECTED_SOURCE_ROWS = 96760
EXPECTED_UNRESOLVED_ROWS = 210
HORIZONS = (21, 63, 126, 252)
SEALED_YEAR = 2023


def _sha(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> str:
    payload = [
        {field: row[field] for field in fields}
        for row in rows
    ]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def run(
    *,
    ledger_path: Path,
    summary_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    required_summary = {
        "status": "PHASE1_SECURITY_CONTINUITY_LEDGER_COMPLETE",
        "eventRowsScanned": EXPECTED_SOURCE_EVENTS,
        "eventHorizonRows": EXPECTED_SOURCE_ROWS,
        "unresolvedEventHorizonRows": EXPECTED_UNRESOLVED_ROWS,
        "performanceRead": False,
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "gapThresholdSessions": 10,
    }
    for key, expected in required_summary.items():
        if summary.get(key) != expected:
            raise ValueError(f"source audit summary mismatch: {key}")

    with ledger_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        forbidden = [
            field
            for field in fields
            if field.startswith(("raw_", "excess_", "mae_"))
        ]
        if forbidden:
            raise ValueError(f"performance fields present in continuity ledger: {forbidden}")
        rows = [
            dict(row)
            for row in reader
            if str(row.get("state") or "") == "UNRESOLVED_CONTINUITY"
        ]

    if len(rows) != EXPECTED_UNRESOLVED_ROWS:
        raise ValueError("unresolved continuity row count changed")

    normalized: list[dict[str, Any]] = []
    for row in rows:
        horizon = int(row["horizon"])
        if horizon not in HORIZONS:
            raise ValueError("unexpected unresolved horizon")
        for field in ("evaluationSession", "entrySession", "targetExitSession"):
            value = str(row.get(field) or "")
            if value and int(value[:4]) >= SEALED_YEAR:
                raise ValueError("sealed OOS metadata encountered")
        normalized.append(
            {
                "eventNumber": int(row["eventNumber"]),
                "issuerCik": str(row["issuerCik"]),
                "ticker": str(row["ticker"]).upper(),
                "evaluationSession": str(row["evaluationSession"]),
                "entrySession": str(row["entrySession"]),
                "horizon": horizon,
                "targetExitSession": str(row["targetExitSession"]),
                "resolutionSource": str(row.get("resolutionSource") or ""),
                "candidateActionTypes": str(row.get("candidateActionTypes") or ""),
                "candidateActionIds": str(row.get("candidateActionIds") or ""),
                "adjustedActionTypes": str(row.get("adjustedActionTypes") or ""),
                "maxInternalGapSessions": int(row.get("maxInternalGapSessions") or 0),
                "longInternalGapCandidate": str(
                    row.get("longInternalGapCandidate") or ""
                ).lower()
                in {"true", "1"},
            }
        )

    normalized.sort(key=lambda row: (row["eventNumber"], row["horizon"]))
    keys = [
        (
            row["eventNumber"],
            row["issuerCik"],
            row["ticker"],
            row["entrySession"],
            row["horizon"],
            row["targetExitSession"],
        )
        for row in normalized
    ]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate unresolved event-horizon key")

    key_fields = (
        "eventNumber",
        "issuerCik",
        "ticker",
        "evaluationSession",
        "entrySession",
        "horizon",
        "targetExitSession",
    )
    evidence_fields = key_fields + (
        "resolutionSource",
        "candidateActionTypes",
        "candidateActionIds",
        "adjustedActionTypes",
        "maxInternalGapSessions",
        "longInternalGapCandidate",
    )

    by_source = Counter(row["resolutionSource"] for row in normalized)
    by_horizon = Counter(str(row["horizon"]) for row in normalized)
    by_action = Counter()
    for row in normalized:
        for action in row["candidateActionTypes"].split(";"):
            if action:
                by_action[action] += 1

    payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_STAGE_B_UNRESOLVED_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceEventRows": EXPECTED_SOURCE_EVENTS,
        "sourceEventHorizonRows": EXPECTED_SOURCE_ROWS,
        "unresolvedRows": len(normalized),
        "unresolvedUniqueEvents": len({row["eventNumber"] for row in normalized}),
        "unresolvedUniqueIssuers": len({row["issuerCik"] for row in normalized}),
        "unresolvedUniqueTickers": len({row["ticker"] for row in normalized}),
        "longInternalGapRows": sum(
            1 for row in normalized if row["longInternalGapCandidate"]
        ),
        "rowsByResolutionSource": dict(sorted(by_source.items())),
        "rowsByHorizon": dict(sorted(by_horizon.items())),
        "candidateActionRowsByType": dict(sorted(by_action.items())),
        "scopeKeySha256": _sha(normalized, key_fields),
        "evidenceKeySha256": _sha(normalized, evidence_fields),
        "rows": normalized,
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
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        ledger_path=args.ledger,
        summary_path=args.summary,
        output_path=args.output,
    )
    compact = {key: value for key, value in result.items() if key != "rows"}
    print(json.dumps(compact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
