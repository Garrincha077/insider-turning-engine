"""Freeze the feature-tournament Stage-B event-horizon continuity scope."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import research_market_event_audit_v2 as p0

HORIZONS = (21, 63, 126, 252)
EXPECTED_EVENTS = 24192
EXPECTED_ISSUERS = 4729
EXPECTED_ROWS = EXPECTED_EVENTS * len(HORIZONS)
FORBIDDEN_TOKENS = ("raw_", "excess_", "mae_", "forward_return", "future_return")


def _digest(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        rows,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _load_stage_a(
    matrix_path: Path,
    summary_path: Path,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    required = {
        "status": "PHASE1_INSIDER_FEATURE_TOURNAMENT_STAGE_A_FROZEN",
        "definitionId": "PHASE1_INSIDER_FEATURE_TOURNAMENT_V1",
        "researchOnly": True,
        "forwardReturnsRead": False,
        "outcomeFieldsRead": [],
        "maeRead": False,
        "robustnessRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for key, expected in required.items():
        if summary.get(key) != expected:
            raise ValueError(f"Stage-A source contract mismatch: {key}")
    if summary["scope"]["events"] != EXPECTED_EVENTS:
        raise ValueError("Stage-A event count changed")
    if summary["scope"]["distinctIssuers"] != EXPECTED_ISSUERS:
        raise ValueError("Stage-A issuer count changed")

    with matrix_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        required_fields = {
            "eventNumber",
            "issuerCik",
            "ticker",
            "evaluationSession",
            "entrySession",
        }
        if not required_fields.issubset(fields):
            raise ValueError("Stage-A matrix missing scope key fields")
        lowered = [field.lower() for field in fields]
        if any(
            token in field
            for field in lowered
            for token in FORBIDDEN_TOKENS
        ):
            raise ValueError("Stage-A matrix contains forbidden outcome field")
        rows = [
            {key: str(row.get(key) or "").strip() for key in required_fields}
            for row in reader
        ]

    if len(rows) != EXPECTED_EVENTS:
        raise ValueError("Stage-A matrix row count changed")
    if len({row["issuerCik"] for row in rows}) != EXPECTED_ISSUERS:
        raise ValueError("Stage-A matrix issuer count changed")
    event_numbers = [int(row["eventNumber"]) for row in rows]
    if event_numbers != list(range(1, EXPECTED_EVENTS + 1)):
        raise ValueError("Stage-A event order changed")
    return rows, summary


def freeze(
    *,
    matrix_path: Path,
    summary_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    events, source_summary = _load_stage_a(matrix_path, summary_path)
    sessions = p0._expected_sessions()
    session_index = {day: index for index, day in enumerate(sessions)}

    scope_rows: list[dict[str, Any]] = []
    for event in events:
        entry = event["entrySession"]
        entry_idx = session_index.get(entry)
        if entry_idx is None:
            raise ValueError("Stage-A entry session absent from XNYS calendar")
        for horizon in HORIZONS:
            target_idx = entry_idx + horizon
            if target_idx >= len(sessions):
                raise ValueError("Stage-B target exceeds bounded XNYS calendar")
            target = sessions[target_idx]
            if int(target[:4]) >= 2023:
                raise ValueError("sealed OOS target encountered")
            scope_rows.append(
                {
                    "eventNumber": int(event["eventNumber"]),
                    "issuerCik": event["issuerCik"],
                    "ticker": event["ticker"].upper(),
                    "evaluationSession": event["evaluationSession"],
                    "entrySession": entry,
                    "horizon": horizon,
                    "targetExitSession": target,
                }
            )

    if len(scope_rows) != EXPECTED_ROWS:
        raise ValueError("Stage-B continuity scope row count changed")

    scope_digest = _digest(scope_rows)
    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_STAGE_B_CONTINUITY_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceStageAScopeKeySha256": source_summary["scope"]["scopeKeySha256"],
        "events": EXPECTED_EVENTS,
        "distinctIssuers": EXPECTED_ISSUERS,
        "horizonsSessions": list(HORIZONS),
        "eventHorizonRows": len(scope_rows),
        "scopeKeySha256": scope_digest,
        "scopeRows": scope_rows,
        "continuityResolutionComplete": False,
        "unresolvedRows": None,
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
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = freeze(
        matrix_path=args.matrix,
        summary_path=args.summary,
        output_path=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
