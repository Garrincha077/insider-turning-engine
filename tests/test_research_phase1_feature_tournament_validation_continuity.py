from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_continuity"
)


def _summary() -> dict[str, object]:
    return {
        "status": "PHASE1_FEATURE_TOURNAMENT_VALIDATION_SCOPE_FROZEN",
        "confirmedCandidate": "F2_DIRECT_VS_INDIRECT",
        "frozenPreferred": "INDIRECT_ONLY",
        "frozenComplement": "DIRECT_ONLY",
        "outcomesRead": False,
        "priceOutcomeFieldsRead": [],
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "primaryHorizonSessions": 126,
        "validationScopeRows": 1,
        "scopeKeySha256": "sha256:test",
    }


def _write_scope(tmp_path: Path, *, horizon: int = 126) -> tuple[Path, Path]:
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps(_summary()), encoding="utf-8")

    scope = tmp_path / "validation-scope.csv"
    with scope.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "eventNumber",
                "issuerCik",
                "ticker",
                "evaluationSession",
                "entrySession",
                "horizon",
                "targetExitSession",
                "F2_DIRECT_VS_INDIRECT",
                "F2_OWNERSHIP_CATEGORY",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "eventNumber": 1,
                "issuerCik": "0000000001",
                "ticker": "TEST",
                "evaluationSession": "2021-01-04",
                "entrySession": "2021-01-05",
                "horizon": horizon,
                "targetExitSession": "2021-07-07",
                "F2_DIRECT_VS_INDIRECT": "INDIRECT_ONLY",
                "F2_OWNERSHIP_CATEGORY": "INDIRECT_ONLY",
            }
        )
    return scope, summary


def test_load_scope_accepts_frozen_primary_horizon(tmp_path: Path) -> None:
    scope, summary = _write_scope(tmp_path)
    loaded_summary, rows = mod._load_scope(scope, summary)
    assert loaded_summary["scopeKeySha256"] == "sha256:test"
    assert len(rows) == 1
    assert rows[0]["horizon"] == "126"


def test_load_scope_rejects_horizon_drift(tmp_path: Path) -> None:
    scope, summary = _write_scope(tmp_path, horizon=63)
    with pytest.raises(ValueError, match="horizon changed"):
        mod._load_scope(scope, summary)


def test_load_actions_requires_performance_blind_source(
    tmp_path: Path,
) -> None:
    path = tmp_path / "actions.json"
    path.write_text(
        json.dumps(
            {
                "performanceRead": True,
                "oosOpened": False,
                "actions": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not performance-blind"):
        mod._load_actions(path)
