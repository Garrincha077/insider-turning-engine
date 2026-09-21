from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_corrected_robustness")


def _summary() -> dict[str, object]:
    return {
        "status": mod.SOURCE_STATUS,
        "benchmark": "B3_COMPANY_NET_BUYING_V1",
        "resultClass": "research/descriptive",
        "formalAlphaClaimed": False,
        "period": "2016-2020 XNYS evaluation-session cohort",
        "outcomeMarketBoundary": "2016-2022 only",
        "coverageTier": "C_EXPLORATORY",
        "primaryHorizonSessions": 126,
        "horizonsSessions": [21, 63, 126, 252],
        "continuityCorrectionComplete": True,
        "maeRecomputed": False,
        "validationPerformanceComputed": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "b3DefinitionChanged": False,
        "eventConstructionChanged": False,
        "identityDefinitionChanged": False,
        "definitionId": "B3_CONTINUITY_CORRECTED_DEVELOPMENT_V1",
    }


def test_corrected_source_contract_passes() -> None:
    mod._validate_source_summary(_summary())


def test_uncorrected_source_status_fails() -> None:
    payload = _summary()
    payload["status"] = "PHASE1_B3_DEVELOPMENT_DESCRIPTIVE_COMPLETE"
    with pytest.raises(ValueError, match="source mismatch"):
        mod._validate_source_summary(payload)


def test_mae_recomputation_change_fails() -> None:
    payload = _summary()
    payload["maeRecomputed"] = True
    with pytest.raises(ValueError, match="source mismatch"):
        mod._validate_source_summary(payload)


def test_open_oos_fails() -> None:
    payload = _summary()
    payload["oosOpened"] = True
    with pytest.raises(ValueError, match="source mismatch"):
        mod._validate_source_summary(payload)
