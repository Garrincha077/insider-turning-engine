"""Diagnose the exact HSDT validation long-gap interval without prices."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import exchange_calendars as xcals

EXPECTED_SCOPE_ROWS = 33
EXPECTED_SCOPE_DIGEST = (
    "sha256:9ee5091b18344e67b58fe567b92ce99d3f923e4df2829af935158947bdcae2a2"
)
EXPECTED_EVENT = 3657
EXPECTED_CIK = "0001610853"
EXPECTED_TICKER = "HSDT"
EXPECTED_ENTRY = "2021-11-16"
EXPECTED_TARGET = "2022-05-18"
EXPECTED_GAP = 29


def _load_scope(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
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
        "residualRows": EXPECTED_SCOPE_ROWS,
        "scopeKeySha256": EXPECTED_SCOPE_DIGEST,
        "priorLongGapCandidateRows": 1,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"residual-33 source mismatch: {key}")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_SCOPE_ROWS:
        raise ValueError("residual-33 rows changed")
    return payload


def _candidate(payload: dict[str, Any]) -> dict[str, Any]:
    rows = [
        row
        for row in payload["rows"]
        if (row.get("evidenceAudit") or {}).get("category")
        == "LONG_GAP_PRIOR_SECURITY_CANDIDATE"
    ]
    if len(rows) != 1:
        raise ValueError("expected one prior-security long-gap candidate")
    row = dict(rows[0])
    required = {
        "eventNumber": EXPECTED_EVENT,
        "issuerCik": EXPECTED_CIK,
        "ticker": EXPECTED_TICKER,
        "entrySession": EXPECTED_ENTRY,
        "targetExitSession": EXPECTED_TARGET,
        "horizon": 126,
        "maxInternalGapSessions": EXPECTED_GAP,
    }
    for key, expected in required.items():
        actual = row.get(key)
        if key in {"eventNumber", "horizon", "maxInternalGapSessions"}:
            actual = int(actual)
        else:
            actual = str(actual)
        if actual != expected:
            raise ValueError(f"HSDT candidate mismatch: {key}")
    return row


def _market_files(root: Path) -> list[Path]:
    files = []
    for year in (2021, 2022):
        matches = list(root.rglob(f"canonical-market-{year}.csv"))
        if len(matches) != 1:
            raise ValueError(
                f"expected one canonical-market-{year}.csv, got {len(matches)}"
            )
        files.append(matches[0])
    if list(root.rglob("canonical-market-2023.csv")):
        raise ValueError("sealed 2023 market file mounted")
    return files


def _observed_sessions(root: Path) -> set[str]:
    observed: set[str] = set()
    required = {
        "date",
        "ticker",
        "volume",
        "trade_count",
        "terminal_candidate",
    }
    for path in _market_files(root):
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if not required.issubset(reader.fieldnames or []):
                raise ValueError("market presence file missing required columns")
            for row in reader:
                if str(row["ticker"]).upper() != EXPECTED_TICKER:
                    continue
                day = str(row["date"])[:10]
                if not (EXPECTED_ENTRY <= day <= EXPECTED_TARGET):
                    continue
                terminal = (
                    str(row.get("terminal_candidate") or "").lower() == "true"
                )
                volume = int(float(row.get("volume") or 0))
                trade_count = int(float(row.get("trade_count") or 0))
                if not terminal and volume > 0 and trade_count > 0:
                    observed.add(day)
    return observed


def run(
    *,
    scope_path: Path,
    market_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    scope = _load_scope(scope_path)
    row = _candidate(scope)

    calendar = xcals.get_calendar("XNYS")
    sessions = [
        str(value.date())
        for value in calendar.sessions_in_range(EXPECTED_ENTRY, EXPECTED_TARGET)
    ]
    session_index = {day: index for index, day in enumerate(sessions)}
    observed = sorted(
        day
        for day in _observed_sessions(market_root)
        if day in session_index
    )
    if len(observed) < 2:
        raise ValueError("insufficient HSDT observed sessions")

    gaps: list[dict[str, Any]] = []
    for left, right in zip(observed, observed[1:], strict=False):
        left_index = session_index[left]
        right_index = session_index[right]
        missing = right_index - left_index - 1
        if missing <= 0:
            continue
        gaps.append(
            {
                "leftObservedSession": left,
                "rightObservedSession": right,
                "firstMissingSession": sessions[left_index + 1],
                "lastMissingSession": sessions[right_index - 1],
                "missingSessionCount": missing,
            }
        )

    maximum = max((int(item["missingSessionCount"]) for item in gaps), default=0)
    if maximum != EXPECTED_GAP:
        raise ValueError(
            f"HSDT max gap changed: {maximum} != {EXPECTED_GAP}"
        )
    max_intervals = [
        item for item in gaps if int(item["missingSessionCount"]) == maximum
    ]
    if not max_intervals:
        raise ValueError("HSDT max gap interval missing")

    result = {
        "schemaVersion": "1.0.0",
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "HSDT_GAP_INTERVAL_DIAGNOSTIC_COMPLETE"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualScopeKeySha256": EXPECTED_SCOPE_DIGEST,
        "eventNumber": int(row["eventNumber"]),
        "issuerCik": str(row["issuerCik"]),
        "ticker": EXPECTED_TICKER,
        "entrySession": EXPECTED_ENTRY,
        "targetExitSession": EXPECTED_TARGET,
        "observedRegularSessions": len(observed),
        "maxInternalGapSessions": maximum,
        "maxGapIntervals": max_intervals,
        "resolutionApplied": False,
        "primaryEvidenceCheckRequired": True,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        scope_path=args.scope,
        market_root=args.market_root,
        output_path=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
