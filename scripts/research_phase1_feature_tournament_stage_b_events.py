"""Adapt the frozen Stage-B continuity scope into one event row per B0 event.

This adapter is deliberately outcome-blind. It only validates and reshapes the
immutable Stage-B event-horizon key set for the generic continuity ledger.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

HORIZONS = (21, 63, 126, 252)
EXPECTED_EVENTS = 24190
EXPECTED_ISSUERS = 4729
EXPECTED_ROWS = EXPECTED_EVENTS * len(HORIZONS)
SEALED_YEAR = 2023


def _load_scope(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "status": "PHASE1_FEATURE_TOURNAMENT_STAGE_B_CONTINUITY_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "events": EXPECTED_EVENTS,
        "distinctIssuers": EXPECTED_ISSUERS,
        "horizonsSessions": list(HORIZONS),
        "eventHorizonRows": EXPECTED_ROWS,
        "continuityResolutionComplete": False,
        "unresolvedRows": None,
        "featureDiscoveryOutcomesOpened": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"Stage-B scope contract mismatch: {key}")
    rows = payload.get("scopeRows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_ROWS:
        raise ValueError("Stage-B scopeRows count changed")
    return payload


def _collapse_scope(payload: dict[str, Any]) -> list[dict[str, str]]:
    rows = payload["scopeRows"]
    grouped: dict[int, dict[str, Any]] = {}

    for raw in rows:
        event_number = int(raw["eventNumber"])
        horizon = int(raw["horizon"])
        if horizon not in HORIZONS:
            raise ValueError("unexpected Stage-B horizon")

        identity = {
            "issuerCik": str(raw["issuerCik"]),
            "ticker": str(raw["ticker"]).upper(),
            "evaluationSession": str(raw["evaluationSession"]),
            "entrySession": str(raw["entrySession"]),
        }
        for field in ("evaluationSession", "entrySession", "targetExitSession"):
            value = str(raw[field])
            if value and int(value[:4]) >= SEALED_YEAR:
                raise ValueError("sealed OOS boundary violated by Stage-B metadata")

        event = grouped.setdefault(
            event_number,
            {
                **identity,
                "targets": {},
            },
        )
        for key, value in identity.items():
            if event[key] != value:
                raise ValueError(f"Stage-B identity drift within event: {key}")
        targets = event["targets"]
        if horizon in targets:
            raise ValueError("duplicate Stage-B event/horizon")
        targets[horizon] = str(raw["targetExitSession"])

    if sorted(grouped) != list(range(1, EXPECTED_EVENTS + 1)):
        raise ValueError("Stage-B event numbering changed")

    events: list[dict[str, str]] = []
    for event_number in range(1, EXPECTED_EVENTS + 1):
        item = grouped[event_number]
        targets = item["targets"]
        if sorted(targets) != list(HORIZONS):
            raise ValueError("Stage-B event missing frozen horizon")
        events.append(
            {
                "eventNumber": str(event_number),
                "issuerCik": item["issuerCik"],
                "ticker": item["ticker"],
                "evaluationSession": item["evaluationSession"],
                "entrySession": item["entrySession"],
                **{f"exit_{horizon}": targets[horizon] for horizon in HORIZONS},
            }
        )

    if len(events) != EXPECTED_EVENTS:
        raise ValueError("Stage-B event count changed")
    if len({event["issuerCik"] for event in events}) != EXPECTED_ISSUERS:
        raise ValueError("Stage-B issuer count changed")
    return events


def run(*, scope_path: Path, output_csv: Path, summary_path: Path) -> dict[str, Any]:
    payload = _load_scope(scope_path)
    events = _collapse_scope(payload)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "eventNumber",
        "issuerCik",
        "ticker",
        "evaluationSession",
        "entrySession",
        *(f"exit_{horizon}" for horizon in HORIZONS),
    ]
    with output_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(events)

    summary = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_STAGE_B_EVENT_ADAPTER_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceScopeKeySha256": payload["scopeKeySha256"],
        "sourceStageAScopeKeySha256": payload["sourceStageAScopeKeySha256"],
        "events": len(events),
        "distinctIssuers": len({event["issuerCik"] for event in events}),
        "horizonsSessions": list(HORIZONS),
        "eventHorizonRows": len(events) * len(HORIZONS),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                scope_path=args.scope,
                output_csv=args.output_csv,
                summary_path=args.summary,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
