from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_feature_tournament_stage_b_scope")


def _summary() -> dict[str, object]:
    return {
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
        "scope": {
            "events": mod.EXPECTED_EVENTS,
            "distinctIssuers": mod.EXPECTED_ISSUERS,
            "scopeKeySha256": "sha256:fixture",
        },
    }


def test_digest_is_deterministic() -> None:
    rows = [{"eventNumber": 1, "horizon": 126}]
    assert mod._digest(rows) == mod._digest(rows)
    assert mod._digest(rows).startswith("sha256:")


def test_stage_a_contract_rejects_open_oos(tmp_path: Path) -> None:
    summary = _summary()
    summary["oosOpened"] = True
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    matrix = tmp_path / "matrix.csv"
    matrix.write_text(
        "eventNumber,issuerCik,ticker,evaluationSession,entrySession\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="source contract mismatch"):
        mod._load_stage_a(matrix, summary_path)


def test_stage_a_matrix_rejects_outcome_column(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(_summary()), encoding="utf-8")
    matrix = tmp_path / "matrix.csv"
    with matrix.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "eventNumber",
                "issuerCik",
                "ticker",
                "evaluationSession",
                "entrySession",
                "excess_126",
            ]
        )
    with pytest.raises(ValueError, match="forbidden outcome"):
        mod._load_stage_a(matrix, summary_path)


def test_expected_scope_row_count_is_four_per_event() -> None:
    assert mod.EXPECTED_ROWS == mod.EXPECTED_EVENTS * 4
    assert mod.HORIZONS == (21, 63, 126, 252)
