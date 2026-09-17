from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

import exchange_calendars as xcals
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
ledger = importlib.import_module("research_phase1_security_continuity_ledger")


def test_same_cusip_name_change_is_same_security_symbol_change() -> None:
    actions = [
        {
            "bucket": "name_changes",
            "old_symbol": "AI",
            "old_cusip": "041356205",
            "new_symbol": "AAIC",
            "new_cusip": "041356205",
        }
    ]
    state, successor = ledger._provider_state(actions)
    assert state == "SYMBOL_CHANGED_SAME_SECURITY"
    assert successor == "AAIC"


def test_reverse_split_is_diagnostic_not_identity_candidate() -> None:
    actions = [
        {
            "bucket": "reverse_splits",
            "symbol": "HEAR",
            "actionDate": "2018-04-09",
        }
    ]
    candidates, adjusted = ledger._candidate_actions(
        actions,
        "2017-11-20",
        "2018-05-23",
    )
    assert candidates == []
    assert len(adjusted) == 1
    assert adjusted[0]["bucket"] == "reverse_splits"


def test_verified_fixtures_apply_only_after_effective_date() -> None:
    oas = {
        "effectiveDate": "2020-11-19",
        "correctionState": "DISCONTINUOUS_NO_COMPLETE_VALUATION",
        "successorSymbol": "OAS",
    }
    assert ledger._fixture_state(oas, "2020-10-08", "2020-11-18") == (None, None)
    assert ledger._fixture_state(oas, "2020-10-08", "2021-04-12") == (
        "DISCONTINUOUS_NO_COMPLETE_VALUATION",
        "OAS",
    )

    lov = {
        "effectiveDate": "2017-11-02",
        "correctionState": "TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol": "LOV",
    }
    assert ledger._fixture_state(lov, "2017-08-29", "2018-03-01") == (
        "TRANSFORMED_HOLDER_CONSIDERATION",
        "LOV",
    )


def test_internal_gap_threshold_is_exactly_ten_sessions() -> None:
    assert ledger._max_internal_gap([0, 11], 0, 11) == 10
    assert ledger._max_internal_gap([0, 10], 0, 10) == 9


def _market_header() -> list[str]:
    return [
        "date",
        "ticker",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "adj_close",
        "is_adjusted",
        "adjustment_basis",
        "split_factor",
        "trade_count",
        "vwap",
        "terminal_candidate",
        "provider",
    ]


def _write_market_year(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=_market_header())
        writer.writeheader()
        writer.writerows(rows)


def _market_row(day: str, ticker: str = "TEST") -> dict[str, str]:
    return {
        "date": day,
        "ticker": ticker,
        "open": "10",
        "high": "11",
        "low": "9",
        "close": "10",
        "volume": "100",
        "adj_close": "10",
        "is_adjusted": "true",
        "adjustment_basis": "alpaca-adjustment-all",
        "split_factor": "",
        "trade_count": "10",
        "vwap": "10",
        "terminal_candidate": "false",
        "provider": "alpaca-sip",
    }


def _write_event(path: Path, sessions: list[str]) -> None:
    fields = [
        "issuerCik",
        "ticker",
        "evaluationSession",
        "entrySession",
        "exit_21",
        "exit_63",
        "exit_126",
        "exit_252",
        "raw_126",
        "excess_126",
        "mae_126",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "issuerCik": "0000000001",
                "ticker": "TEST",
                "evaluationSession": sessions[0],
                "entrySession": sessions[1],
                "exit_21": sessions[22],
                "exit_63": sessions[64],
                "exit_126": sessions[127],
                "exit_252": sessions[253],
                "raw_126": "THIS_MUST_NOT_BE_PARSED",
                "excess_126": "THIS_MUST_NOT_BE_PARSED",
                "mae_126": "THIS_MUST_NOT_BE_PARSED",
            }
        )


def _write_empty_inventory(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "performanceRead": False,
                "researchOnly": True,
                "oosOpened": False,
                "productionScoringChanged": False,
                "actions": [],
            }
        ),
        encoding="utf-8",
    )


def _write_empty_fixtures(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "performanceRead": False,
                "researchOnly": True,
                "oosOpened": False,
                "fixtures": [],
            }
        ),
        encoding="utf-8",
    )


def _sessions() -> list[str]:
    calendar = xcals.get_calendar("XNYS")
    return [
        str(value.date())
        for value in calendar.sessions_in_range("2020-01-02", "2021-03-31")
    ]


def _write_market_tree(
    root: Path,
    sessions: list[str],
    *,
    missing_indices: set[int],
) -> None:
    for year in range(2016, 2023):
        rows = []
        if year in {2020, 2021}:
            rows = [
                _market_row(day)
                for index, day in enumerate(sessions)
                if int(day[:4]) == year and index not in missing_indices
            ]
        _write_market_year(root / str(year) / f"canonical-market-{year}.csv", rows)


def _run_synthetic(tmp_path: Path, missing_indices: set[int]) -> dict[str, object]:
    sessions = _sessions()
    events = tmp_path / "events.csv"
    actions = tmp_path / "actions.json"
    fixtures = tmp_path / "fixtures.json"
    market_root = tmp_path / "market"
    output = tmp_path / "out"
    _write_event(events, sessions)
    _write_empty_inventory(actions)
    _write_empty_fixtures(fixtures)
    _write_market_tree(market_root, sessions, missing_indices=missing_indices)
    return ledger.run(
        events_path=events,
        corporate_actions_path=actions,
        fixtures_path=fixtures,
        market_root=market_root,
        output_dir=output,
    )


def test_full_run_is_performance_blind_and_long_gap_blocks(tmp_path: Path) -> None:
    result = _run_synthetic(tmp_path, set(range(5, 15)))
    assert result["performanceRead"] is False
    assert result["performanceColumnsIgnored"] == ["excess_126", "mae_126", "raw_126"]
    assert result["gapThresholdSessions"] == 10
    assert result["longInternalGapEventHorizonRows"] > 0
    assert result["unresolvedEventHorizonRows"] > 0
    assert result["performanceStageBlocked"] is True


def test_nine_session_gap_does_not_trigger_long_gap_rule(tmp_path: Path) -> None:
    result = _run_synthetic(tmp_path, set(range(5, 14)))
    assert result["longInternalGapEventHorizonRows"] == 0
    assert result["unresolvedEventHorizonRows"] == 0
    assert result["performanceStageBlocked"] is False


def test_event_metadata_in_2023_hard_fails(tmp_path: Path) -> None:
    path = tmp_path / "events.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "issuerCik",
                "ticker",
                "evaluationSession",
                "entrySession",
                "exit_21",
                "exit_63",
                "exit_126",
                "exit_252",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "issuerCik": "1",
                "ticker": "TEST",
                "evaluationSession": "2020-01-02",
                "entrySession": "2020-01-03",
                "exit_21": "2020-02-03",
                "exit_63": "2020-04-03",
                "exit_126": "2020-07-03",
                "exit_252": "2023-01-03",
            }
        )
    with pytest.raises(ValueError, match="sealed OOS boundary"):
        ledger._load_events(path)
