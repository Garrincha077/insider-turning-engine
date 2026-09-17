from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
robustness = importlib.import_module("research_phase1_b1_robustness")


def test_tail_cut_semantics_are_deterministic() -> None:
    values = [float(i) for i in range(100)]
    result = robustness._tail_diagnostics(values)
    assert result["trimmedMean1PctEachTail"] == pytest.approx(49.5)
    assert result["top1PctRemovedMean"] == pytest.approx(49.0)
    assert result["top5PctRemovedMean"] == pytest.approx(47.0)
    assert result["quantiles"]["p01"] == pytest.approx(0.99)
    assert result["quantiles"]["p99"] == pytest.approx(98.01)


def test_group_equal_weighting_prevents_repeated_group_domination() -> None:
    rows = [
        {"issuerCik": "1", "entrySession": "2016-01-04", "excess_126": "1.0"},
        {"issuerCik": "1", "entrySession": "2016-01-05", "excess_126": "1.0"},
        {"issuerCik": "2", "entrySession": "2016-01-06", "excess_126": "-1.0"},
    ]
    result = robustness._group_diagnostics(rows, "issuerCik")
    assert result["eventWeightedMean"] == pytest.approx(1 / 3)
    assert result["equalWeightMean"] == pytest.approx(0.0)
    assert result["groupCount"] == 2


def test_warning_semantics_are_locked() -> None:
    tail = {"top1PctRemovedMean": 0.01, "positiveTailContribution": {"top1Pct": 0.55}}
    issuer = {"equalWeightMean": 0.02}
    session = {"equalWeightMean": -0.01}
    yearly = {"positiveMeanYears": 2}
    warnings = robustness._warnings(tail, issuer, session, yearly)
    assert warnings == {
        "issuerEqualWeightMeanNonPositive": False,
        "entrySessionEqualWeightMeanNonPositive": True,
        "top1PctRemovedMeanNonPositive": False,
        "fewerThanThreePositiveMeanYears": True,
        "top1PctPositiveTailAtLeastHalf": True,
    }


def _write_events(path: Path, rows: list[dict[str, str]]) -> None:
    fields = [
        "issuerCik",
        "knowledgeAtFirst",
        "evaluationSession",
        "entrySession",
        "exit_21",
        "excess_21",
        "exit_63",
        "excess_63",
        "exit_126",
        "excess_126",
        "exit_252",
        "excess_252",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _summary(values_by_horizon: dict[int, list[float]]) -> dict[str, object]:
    horizons = {}
    for horizon, values in values_by_horizon.items():
        horizons[str(horizon)] = {
            "maturedOutcomeCount": len(values),
            "spyExcessMean": robustness._mean(values),
            "spyExcessMedian": robustness._median(values),
            "spyExcessWinRate": robustness._win_rate(values),
        }
    return {
        "status": "PHASE1_B1_DEVELOPMENT_DESCRIPTIVE_COMPLETE",
        "primaryHorizonSessions": 126,
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "period": "2016-2020 XNYS evaluation-session cohort",
        "outcomeMarketBoundary": "2016-2022 only",
        "p0DataQualityTier": "C_EXPLORATORY",
        "horizons": horizons,
    }


def test_run_persists_boundaries_and_reproduces_canonical_summary(tmp_path: Path) -> None:
    rows = []
    values = []
    for index, year in enumerate(range(2016, 2021), start=1):
        value = index / 100
        values.append(value)
        rows.append(
            {
                "issuerCik": str(index),
                "knowledgeAtFirst": f"{year}-01-01T00:00:00Z",
                "evaluationSession": f"{year}-01-04",
                "entrySession": f"{year}-01-05",
                "exit_21": f"{year}-02-05",
                "excess_21": str(value),
                "exit_63": f"{year}-04-05",
                "excess_63": str(value),
                "exit_126": f"{year}-07-05",
                "excess_126": str(value),
                "exit_252": f"{year + 1}-01-05",
                "excess_252": str(value),
            }
        )
    events = tmp_path / "b1-events.csv"
    summary = tmp_path / "b1-summary.json"
    output = tmp_path / "robustness.json"
    _write_events(events, rows)
    payload = _summary({h: values for h in robustness.HORIZONS})
    summary.write_text(json.dumps(payload), encoding="utf-8")

    result = robustness.run(
        events_path=events,
        source_summary_path=summary,
        output_path=output,
        source_run_id="test-run",
    )

    assert result["researchOnly"] is True
    assert result["oosOpened"] is False
    assert result["productionScoringChanged"] is False
    assert result["formalAlphaClaim"] is False
    assert result["oosEligible"] is False
    assert result["yearStability"]["positiveMeanYears"] == 5
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == robustness.STATUS


def test_late_2020_evaluation_may_enter_in_2021() -> None:
    row = {
        "knowledgeAtFirst": "2020-12-31T20:00:00Z",
        "evaluationSession": "2020-12-31",
        "entrySession": "2021-01-04",
        "exit_21": "2021-02-03",
        "exit_63": "2021-04-05",
        "exit_126": "2021-07-06",
        "exit_252": "2022-01-03",
    }
    robustness._validate_row_dates(row)


def test_run_rejects_sealed_oos_date(tmp_path: Path) -> None:
    row = {
        "issuerCik": "1",
        "knowledgeAtFirst": "2020-01-01T00:00:00Z",
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "exit_21": "2023-01-05",
        "excess_21": "0.1",
        "exit_63": "2020-04-05",
        "excess_63": "0.1",
        "exit_126": "2020-07-05",
        "excess_126": "0.1",
        "exit_252": "2021-01-05",
        "excess_252": "0.1",
    }
    events = tmp_path / "events.csv"
    summary = tmp_path / "summary.json"
    _write_events(events, [row])
    payload = _summary({h: [0.1] for h in robustness.HORIZONS})
    summary.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="sealed OOS boundary"):
        robustness.run(
            events_path=events,
            source_summary_path=summary,
            output_path=tmp_path / "out.json",
            source_run_id="test-run",
        )
