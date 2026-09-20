"""Construct frozen pre-outcome B3 development events on the exact XNYS clock.

This stage is deliberately performance-blind. It maps raw B3 positive state
boundaries to the same exact-session evaluation rule used by the Phase-1 market
audit, assigns the exact next XNYS session as entry, and applies the predeclared
20-session issuer deduplication rule. It does not read prices or returns.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import exchange_calendars as xcals

import research_market_event_audit as market_audit
import research_market_event_audit_v2 as p0

DEVELOPMENT_START = "2016-01-01"
DEVELOPMENT_END = "2020-12-31"
SEALED_OOS_YEAR = 2023


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def construct(
    *,
    candidates_path: Path,
    source_summary_path: Path,
    definition_path: Path,
    output: Path,
) -> dict[str, Any]:
    source_summary = json.loads(source_summary_path.read_text(encoding="utf-8"))
    definition = json.loads(definition_path.read_text(encoding="utf-8"))

    if source_summary.get("developmentPeriod") != "2016-2020":
        raise ValueError("unexpected B3 raw development period")
    for flag in (
        "marketDataJoined",
        "returnsRead",
        "developmentPerformanceComputed",
        "validationPerformanceComputed",
        "oosOpened",
        "productionScoringChanged",
    ):
        if source_summary.get(flag) is not False:
            raise ValueError(f"raw B3 source violates pre-outcome flag {flag}")

    if definition.get("status") != "PREDECLARED_BEFORE_B3_DEVELOPMENT_OUTCOMES":
        raise ValueError("B3 event construction definition is not predeclared")
    if definition.get("sourceDefinitionId") != source_summary.get("definitionId"):
        raise ValueError("B3 event construction/source definition mismatch")
    if int(definition["issuerDedupSessions"]) != 20:
        raise ValueError("B3 issuer dedup must remain frozen at 20 sessions")

    raw_rows = _read_jsonl(candidates_path)
    expected_raw = int(source_summary["rawCandidateCount"])
    if len(raw_rows) != expected_raw:
        raise ValueError(
            f"raw candidate count mismatch: expected {expected_raw}, got {len(raw_rows)}"
        )

    calendar = xcals.get_calendar("XNYS")
    sessions = p0._expected_sessions()
    session_index = {day: index for index, day in enumerate(sessions)}
    evaluation_cache: dict[str, str] = {}

    mapped: list[dict[str, Any]] = []
    boundary_excluded = 0

    for row in raw_rows:
        knowledge = str(row["knowledgeBoundaryAt"])
        if int(knowledge[:4]) >= SEALED_OOS_YEAR:
            raise ValueError("sealed OOS boundary violated by B3 raw candidate")
        if row.get("definitionId") != definition["sourceDefinitionId"]:
            raise ValueError("mixed B3 source definition IDs are not allowed")

        evaluation_session = evaluation_cache.get(knowledge)
        if evaluation_session is None:
            evaluation_session = market_audit._evaluation_session(knowledge, calendar)
            evaluation_cache[knowledge] = evaluation_session

        if not (DEVELOPMENT_START <= evaluation_session <= DEVELOPMENT_END):
            boundary_excluded += 1
            continue

        evaluation_idx = session_index.get(evaluation_session)
        if evaluation_idx is None:
            raise ValueError(f"evaluation session absent from XNYS calendar: {evaluation_session}")
        entry_idx = evaluation_idx + 1
        if entry_idx >= len(sessions):
            raise ValueError("missing exact next XNYS entry session")

        mapped.append(
            {
                **row,
                "evaluationSession": evaluation_session,
                "evaluationIndex": evaluation_idx,
                "entrySession": sessions[entry_idx],
                "entryIndex": entry_idx,
                "eventConstructionDefinitionId": definition["definitionId"],
            }
        )

    mapped.sort(
        key=lambda row: (
            int(row["evaluationIndex"]),
            str(row["knowledgeBoundaryAt"]),
            str(row["issuerCik"]),
            str(row["signalId"]),
        )
    )

    retained: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    last_by_issuer: dict[str, tuple[int, str]] = {}

    retained_by_year: dict[str, int] = defaultdict(int)
    suppressed_by_year: dict[str, int] = defaultdict(int)

    for row in mapped:
        issuer = str(row["issuerCik"])
        evaluation_idx = int(row["evaluationIndex"])
        prior = last_by_issuer.get(issuer)
        if prior is not None:
            prior_idx, prior_signal_id = prior
            gap = evaluation_idx - prior_idx
            if gap <= int(definition["issuerDedupSessions"]):
                suppressed.append(
                    {
                        **row,
                        "dedupGapSessions": gap,
                        "suppressedBySignalId": prior_signal_id,
                    }
                )
                suppressed_by_year[str(row["evaluationSession"])[:4]] += 1
                continue

        retained.append(row)
        last_by_issuer[issuer] = (evaluation_idx, str(row["signalId"]))
        retained_by_year[str(row["evaluationSession"])[:4]] += 1

    output.mkdir(parents=True, exist_ok=True)
    with (output / "b3-development-preoutcome-events.jsonl").open(
        "w", encoding="utf-8"
    ) as stream:
        for row in retained:
            stream.write(json.dumps(row, sort_keys=True) + "\n")

    with (output / "b3-development-dedup-suppressed.jsonl").open(
        "w", encoding="utf-8"
    ) as stream:
        for row in suppressed:
            stream.write(json.dumps(row, sort_keys=True) + "\n")

    summary: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_EVENT_CONSTRUCTION_PREOUTCOME_PASS",
        "definitionId": definition["definitionId"],
        "sourceDefinitionId": definition["sourceDefinitionId"],
        "sourceRawCandidateCount": len(raw_rows),
        "developmentEvaluationCandidates": len(mapped),
        "developmentBoundaryExcluded": boundary_excluded,
        "issuerDedupSessions": int(definition["issuerDedupSessions"]),
        "dedupSuppressed": len(suppressed),
        "retainedEventCount": len(retained),
        "distinctRetainedIssuers": len({str(row["issuerCik"]) for row in retained}),
        "retainedByEvaluationYear": dict(sorted(retained_by_year.items())),
        "suppressedByEvaluationYear": dict(sorted(suppressed_by_year.items())),
        "evaluationRule": definition["evaluationRule"],
        "entryRule": definition["entryRule"],
        "dedupRule": definition["dedupRule"],
        "developmentCohortRule": definition["developmentCohortRule"],
        "marketDataJoined": False,
        "returnsRead": False,
        "developmentPerformanceComputed": False,
        "validationPerformanceComputed": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "nextGate": (
            "join frozen pre-outcome B3 events to PIT historical identity/market "
            "data and compute development outcomes through 2022 only"
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--source-summary", type=Path, required=True)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    print(
        json.dumps(
            construct(
                candidates_path=args.candidates,
                source_summary_path=args.source_summary,
                definition_path=args.definition,
                output=args.output,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
