from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_feature_tournament_stage_b_events")


def _scope() -> dict[str, object]:
    rows = []
    for horizon, target in [
        (21, "2020-02-03"),
        (63, "2020-04-02"),
        (126, "2020-07-02"),
        (252, "2021-01-04"),
    ]:
        rows.append(
            {
                "eventNumber": 1,
                "issuerCik": "0000000001",
                "ticker": "TEST",
                "evaluationSession": "2020-01-02",
                "entrySession": "2020-01-03",
                "horizon": horizon,
                "targetExitSession": target,
            }
        )
    return {
        "status": "PHASE1_FEATURE_TOURNAMENT_STAGE_B_CONTINUITY_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "events": 1,
        "distinctIssuers": 1,
        "horizonsSessions": [21, 63, 126, 252],
        "eventHorizonRows": 4,
        "continuityResolutionComplete": False,
        "unresolvedRows": None,
        "featureDiscoveryOutcomesOpened": False,
        "scopeKeySha256": "sha256:scope",
        "sourceStageAScopeKeySha256": "sha256:stage-a",
        "scopeRows": rows,
    }


def _patch_small(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "EXPECTED_EVENTS", 1)
    monkeypatch.setattr(mod, "EXPECTED_ISSUERS", 1)
    monkeypatch.setattr(mod, "EXPECTED_ROWS", 4)


def test_collapse_scope_is_one_row_per_event(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_small(monkeypatch)
    events = mod._collapse_scope(_scope())
    assert len(events) == 1
    assert events[0]["eventNumber"] == "1"
    assert events[0]["ticker"] == "TEST"
    assert events[0]["exit_126"] == "2020-07-02"
    assert events[0]["exit_252"] == "2021-01-04"


def test_duplicate_horizon_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_small(monkeypatch)
    payload = _scope()
    payload["scopeRows"][3]["horizon"] = 126
    with pytest.raises(ValueError, match="duplicate"):
        mod._collapse_scope(payload)


def test_identity_drift_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_small(monkeypatch)
    payload = _scope()
    payload["scopeRows"][2]["ticker"] = "OTHER"
    with pytest.raises(ValueError, match="identity drift"):
        mod._collapse_scope(payload)


def test_load_scope_rejects_open_oos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_small(monkeypatch)
    payload = _scope()
    payload["oosOpened"] = True
    path = tmp_path / "scope.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="oosOpened"):
        mod._load_scope(path)
