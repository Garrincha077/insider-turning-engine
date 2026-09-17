from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
_mod = importlib.import_module("research_phase1_b1_corrected_robustness")


def _source_summary(value: float = 0.1, count: int = 1) -> dict:
    horizons = {}
    for horizon in _mod.HORIZONS:
        horizons[str(horizon)] = {
            "B1ContinuityCorrected": {
                "maturedOutcomeCount": count,
                "spyExcessMean": value,
                "spyExcessMedian": value,
                "spyExcessWinRate": 1.0,
            }
        }
    return {
        "status": "PHASE1_B1_CONTINUITY_CORRECTED_PERFORMANCE_COMPLETE",
        "resultClass": "research/descriptive",
        "primaryHorizonSessions": 126,
        "horizonsSessions": [21, 63, 126, 252],
        "period": "2016-2020 XNYS evaluation-session cohort",
        "outcomeMarketBoundary": "2016-2022 only",
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "formalAlphaClaimed": False,
        "continuityGate": {"unresolvedEventHorizonRows": 0},
        "horizons": horizons,
    }


def _rows(value: str = "0.1") -> list[dict[str, str]]:
    result = []
    exits = {21: "2016-02-03", 63: "2016-04-04", 126: "2016-07-05", 252: "2017-01-04"}
    for horizon in _mod.HORIZONS:
        result.append(
            {
                "eventNumber": "1",
                "issuerCik": "0000000001",
                "ticker": "ABC",
                "evaluationSession": "2016-01-04",
                "entrySession": "2016-01-05",
                "horizon": str(horizon),
                "targetExitSession": exits[horizon],
                "correctedExcess": value,
                "valuationStatus": "VALUED",
            }
        )
    return result


def _five_year_rows(value: str = "0.1") -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for event_number, year in enumerate(range(2016, 2021), start=1):
        next_year = year + 1
        exits = {
            21: f"{year}-02-03",
            63: f"{year}-04-04",
            126: f"{year}-07-05",
            252: f"{next_year}-01-04",
        }
        for horizon in _mod.HORIZONS:
            result.append(
                {
                    "eventNumber": str(event_number),
                    "issuerCik": f"{event_number:010d}",
                    "ticker": f"T{event_number}",
                    "evaluationSession": f"{year}-01-04",
                    "entrySession": f"{year}-01-05",
                    "horizon": str(horizon),
                    "targetExitSession": exits[horizon],
                    "correctedExcess": value,
                    "valuationStatus": "VALUED",
                }
            )
    return result


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_corrected_source_requires_zero_unresolved_gate() -> None:
    summary = _source_summary()
    summary["continuityGate"]["unresolvedEventHorizonRows"] = 1
    with pytest.raises(ValueError, match="zero-unresolved"):
        _mod._validate_source_summary(summary)


def test_corrected_source_rejects_formal_alpha_claim() -> None:
    summary = _source_summary()
    summary["formalAlphaClaimed"] = True
    with pytest.raises(ValueError, match="formal alpha"):
        _mod._validate_source_summary(summary)


def test_2023_target_exit_hard_fails(tmp_path: Path) -> None:
    rows = _rows()
    rows[-1]["targetExitSession"] = "2023-01-03"
    path = tmp_path / "rows.csv"
    _write_rows(path, rows)
    with pytest.raises(ValueError, match="sealed OOS boundary"):
        _mod._load_rows(path)


def test_late_2020_evaluation_may_enter_in_2021(tmp_path: Path) -> None:
    rows = _rows()
    for row in rows:
        row["evaluationSession"] = "2020-12-31"
        row["entrySession"] = "2021-01-04"
    rows[0]["targetExitSession"] = "2021-02-03"
    rows[1]["targetExitSession"] = "2021-04-05"
    rows[2]["targetExitSession"] = "2021-07-06"
    rows[3]["targetExitSession"] = "2022-01-04"
    path = tmp_path / "rows.csv"
    _write_rows(path, rows)
    assert len(_mod._load_rows(path)) == 4


def test_all_four_frozen_horizons_required_per_event(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    _write_rows(path, _rows()[:-1])
    with pytest.raises(ValueError, match="frozen four horizons"):
        _mod._load_rows(path)


def test_nonvalued_row_cannot_contain_corrected_excess(tmp_path: Path) -> None:
    rows = _rows()
    rows[0]["valuationStatus"] = "MISSING_EXACT_TERMINAL_HOLDER_BAR"
    path = tmp_path / "rows.csv"
    _write_rows(path, rows)
    with pytest.raises(ValueError, match="non-valued"):
        _mod._load_rows(path)


def test_reproduction_matches_corrected_summary() -> None:
    checks = _mod._reproduction(_rows(), _source_summary())
    assert checks["126"]["maturedOutcomeCount"] == 1
    assert checks["126"]["spyExcessMean"] == pytest.approx(0.1)
    assert checks["126"]["spyExcessWinRate"] == 1.0


def test_reproduction_detects_changed_corrected_mean() -> None:
    summary = _source_summary(value=0.2)
    with pytest.raises(ValueError, match="corrected spyExcessMean mismatch"):
        _mod._reproduction(_rows(value="0.1"), summary)


def test_warning_semantics_are_identical_to_original_frozen_gate() -> None:
    tails = {"top1PctRemovedMean": -0.001, "positiveTailContribution": {"top1Pct": 0.49}}
    issuer = {"equalWeightMean": 0.01}
    session = {"equalWeightMean": 0.02}
    yearly = {"positiveMeanYears": 2}
    warnings = _mod.base._warnings(tails, issuer, session, yearly)
    assert warnings == {
        "issuerEqualWeightMeanNonPositive": False,
        "entrySessionEqualWeightMeanNonPositive": False,
        "top1PctRemovedMeanNonPositive": True,
        "fewerThanThreePositiveMeanYears": True,
        "top1PctPositiveTailAtLeastHalf": False,
    }


def test_run_never_opens_hac_or_oos(tmp_path: Path) -> None:
    rows_path = tmp_path / "rows.csv"
    _write_rows(rows_path, _five_year_rows())
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(_source_summary(count=5)), encoding="utf-8")
    output = tmp_path / "out.json"
    result = _mod.run(
        event_horizons_path=rows_path,
        source_summary_path=summary_path,
        output_path=output,
        source_run_id="123",
        source_artifact="artifact",
        source_artifact_digest="sha256:test",
    )
    assert result["formalAlphaClaim"] is False
    assert result["oosEligible"] is False
    assert result["oosOpened"] is False
    assert result["calendarTimeHacStageOpened"] is False
    assert result["researchOnly"] is True
