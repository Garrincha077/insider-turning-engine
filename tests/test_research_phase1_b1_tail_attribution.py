from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
audit = importlib.import_module("research_phase1_b1_tail_attribution")

FIELDS = [
    "issuerCik",
    "ticker",
    "knowledgeAtFirst",
    "evaluationSession",
    "entrySession",
    "entryOpen",
    "opportunisticOwnerCount",
    "rawOpportunisticPurchaseRows",
    "exit_21",
    "exit_63",
    "exit_126",
    "exit_252",
    "raw_126",
    "excess_126",
]


def _row(
    index: int,
    *,
    year: int = 2020,
    excess: float = 0.1,
    evaluation: str | None = None,
    issuer: str | None = None,
    ticker: str | None = None,
) -> dict[str, str]:
    day = index % 20 + 1
    evaluation = evaluation or f"{year}-01-{day:02d}"
    return {
        "issuerCik": issuer or f"{index:010d}",
        "ticker": ticker or f"T{index:04d}",
        "knowledgeAtFirst": f"{year}-01-01T12:00:00Z",
        "evaluationSession": evaluation,
        "entrySession": f"{year}-02-03",
        "entryOpen": "10.0",
        "opportunisticOwnerCount": "1",
        "rawOpportunisticPurchaseRows": "1",
        "exit_21": f"{year}-03-03",
        "exit_63": f"{year}-05-04",
        "exit_126": f"{year}-08-03",
        "exit_252": f"{year + 1}-02-03",
        "raw_126": str(excess + 0.02),
        "excess_126": str(excess),
    }


def _write_events(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _source_summary(values: list[float]) -> dict[str, object]:
    return {
        "status": "PHASE1_B1_DEVELOPMENT_DESCRIPTIVE_COMPLETE",
        "primaryHorizonSessions": 126,
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "period": "2016-2020 XNYS evaluation-session cohort",
        "outcomeMarketBoundary": "2016-2022 only",
        "horizons": {
            "126": {
                "maturedOutcomeCount": len(values),
                "spyExcessMean": audit._mean(values),
                "spyExcessMedian": audit._median(values),
                "spyExcessWinRate": audit._win_rate(values),
            }
        },
    }


def test_global_top_one_percent_uses_floor_cutoff() -> None:
    rows = [_row(i, excess=float(i)) for i in range(1, 101)]
    result, top = audit._global_tail(rows)
    assert result["count"] == 1
    assert len(top) == 1
    assert audit._excess(top[0]) == pytest.approx(100.0)


def test_global_tail_ties_use_frozen_deterministic_order() -> None:
    rows = [_row(i, excess=float(i)) for i in range(1, 99)]
    rows.extend(
        [
            _row(
                990,
                excess=999.0,
                evaluation="2020-01-03",
                issuer="0000000002",
                ticker="BBB",
            ),
            _row(
                991,
                excess=999.0,
                evaluation="2020-01-02",
                issuer="0000000003",
                ticker="CCC",
            ),
        ]
    )
    result, top = audit._global_tail(rows)
    assert result["count"] == 1
    assert top[0]["issuerCik"] == "0000000003"


def test_2020_attribution_uses_evaluation_year_and_exclusion() -> None:
    mature = [
        _row(1, year=2019, excess=-0.2),
        _row(2, year=2020, excess=0.4),
        _row(3, year=2020, excess=0.6),
    ]
    grouped = {
        2019: [mature[0]],
        2020: [mature[1], mature[2]],
    }
    result = audit._attribution_2020(mature, grouped, [mature[2]])
    assert result["count"] == 2
    assert result["mean"] == pytest.approx(0.5)
    assert result["globalTopSetSignedExcessSum"] == pytest.approx(0.6)
    assert result["fullCohortExcluding2020"]["mean"] == pytest.approx(-0.2)


def test_sanity_flags_sealed_date_and_invalid_session_order() -> None:
    row = _row(1)
    row["entrySession"] = "2023-01-03"
    row["exit_126"] = "2022-08-03"
    failures = audit._sanity_failures(row)
    assert "SEALED_DATE_entrySession" in failures
    assert "INVALID_SESSION_ORDER" in failures


def test_run_reproduces_summary_and_keeps_oos_closed(tmp_path: Path) -> None:
    rows: list[dict[str, str]] = []
    values: list[float] = []
    index = 1
    for year in range(2016, 2021):
        for offset in range(20):
            value = (year - 2018) / 100 + offset / 1000
            row = _row(index, year=year, excess=value)
            rows.append(row)
            values.append(value)
            index += 1

    events_path = tmp_path / "b1-events.csv"
    summary_path = tmp_path / "b1-summary.json"
    output_path = tmp_path / "tail.json"
    _write_events(events_path, rows)
    summary_path.write_text(
        json.dumps(_source_summary(values)),
        encoding="utf-8",
    )

    result = audit.run(
        events_path=events_path,
        source_summary_path=summary_path,
        output_path=output_path,
        source_run_id="test-run",
    )

    assert result["status"] == audit.STATUS
    assert result["researchOnly"] is True
    assert result["oosOpened"] is False
    assert result["productionScoringChanged"] is False
    assert result["formalAlphaClaim"] is False
    assert result["oosEligible"] is False
    assert result["globalTop1Pct"]["count"] == 1
    assert result["topSetSanity"]["anyFailure"] is False
