from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import research_market_event_audit_v2 as p0

mod = importlib.import_module("research_phase1_b3_event_construction")


def _definition() -> dict[str, object]:
    return {
        "definitionId": "B3_EVENT_CONSTRUCTION_TEST",
        "status": "PREDECLARED_BEFORE_B3_DEVELOPMENT_OUTCOMES",
        "sourceDefinitionId": "B3_TEST",
        "issuerDedupSessions": 20,
        "evaluationRule": "test evaluation",
        "entryRule": "test entry",
        "dedupRule": "test dedup",
        "developmentCohortRule": "test cohort",
    }


def _candidate(
    signal_id: str,
    issuer: str,
    knowledge: str,
) -> dict[str, object]:
    return {
        "signalId": signal_id,
        "issuerCik": issuer,
        "knowledgeBoundaryAt": knowledge,
        "definitionId": "B3_TEST",
        "buyDollars": "100",
        "saleDollars": "0",
        "netDollars": "100",
        "grossDollars": "100",
        "netBuyingIntensity": "1",
        "primaryWindowCalendarDays": 30,
        "activeEconomicRows": 1,
        "requiresDownstreamXnys20SessionIssuerDedup": True,
    }


def _run(tmp_path: Path, rows: list[dict[str, object]]) -> dict[str, object]:
    candidates = tmp_path / "candidates.jsonl"
    candidates.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    summary = tmp_path / "source-summary.json"
    summary.write_text(
        json.dumps(
            {
                "developmentPeriod": "2016-2020",
                "rawCandidateCount": len(rows),
                "definitionId": "B3_TEST",
                "marketDataJoined": False,
                "returnsRead": False,
                "developmentPerformanceComputed": False,
                "validationPerformanceComputed": False,
                "oosOpened": False,
                "productionScoringChanged": False,
            }
        ),
        encoding="utf-8",
    )
    definition = tmp_path / "definition.json"
    definition.write_text(json.dumps(_definition()), encoding="utf-8")
    return mod.construct(
        candidates_path=candidates,
        source_summary_path=summary,
        definition_path=definition,
        output=tmp_path / "out",
    )


def test_exact_xnys_evaluation_and_next_session_entry(tmp_path: Path) -> None:
    rows = [
        _candidate("before", "1", "2019-01-02T20:00:00+00:00"),
        _candidate("after", "2", "2019-01-02T22:00:00+00:00"),
        _candidate("weekend", "3", "2019-01-05T12:00:00+00:00"),
    ]

    summary = _run(tmp_path, rows)
    assert summary["retainedEventCount"] == 3

    events = [
        json.loads(line)
        for line in (tmp_path / "out/b3-development-preoutcome-events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    by_id = {row["signalId"]: row for row in events}

    assert by_id["before"]["evaluationSession"] == "2019-01-02"
    assert by_id["before"]["entrySession"] == "2019-01-03"
    assert by_id["after"]["evaluationSession"] == "2019-01-03"
    assert by_id["after"]["entrySession"] == "2019-01-04"
    assert by_id["weekend"]["evaluationSession"] == "2019-01-07"
    assert by_id["weekend"]["entrySession"] == "2019-01-08"


def test_dedup_suppresses_20_sessions_but_retains_21(tmp_path: Path) -> None:
    sessions = p0._expected_sessions()
    first = sessions[200]
    at_20 = sessions[220]
    at_21 = sessions[221]
    rows = [
        _candidate("first", "1", f"{first}T15:00:00+00:00"),
        _candidate("twenty", "1", f"{at_20}T15:00:00+00:00"),
        _candidate("twenty_one", "1", f"{at_21}T15:00:00+00:00"),
    ]

    summary = _run(tmp_path, rows)

    assert summary["dedupSuppressed"] == 1
    assert summary["retainedEventCount"] == 2
    retained = [
        json.loads(line)["signalId"]
        for line in (tmp_path / "out/b3-development-preoutcome-events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert retained == ["first", "twenty_one"]


def test_evaluation_session_defines_development_boundary(tmp_path: Path) -> None:
    rows = [
        _candidate("late_2020", "1", "2020-12-31T22:00:00+00:00"),
    ]

    summary = _run(tmp_path, rows)

    assert summary["developmentEvaluationCandidates"] == 0
    assert summary["developmentBoundaryExcluded"] == 1
    assert summary["retainedEventCount"] == 0
    assert summary["returnsRead"] is False
    assert summary["oosOpened"] is False
