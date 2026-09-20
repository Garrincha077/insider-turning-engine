from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
b3 = importlib.import_module("research_phase1_b3_robustness")
base = importlib.import_module("research_phase1_b1_robustness")


def test_b3_uses_existing_b1_warning_semantics() -> None:
    tail = {
        "top1PctRemovedMean": 0.01,
        "positiveTailContribution": {"top1Pct": 0.20},
    }
    issuer = {"equalWeightMean": 0.01}
    session = {"equalWeightMean": 0.01}
    yearly = {"positiveMeanYears": 3}

    assert base._warnings(tail, issuer, session, yearly) == {
        "issuerEqualWeightMeanNonPositive": False,
        "entrySessionEqualWeightMeanNonPositive": False,
        "top1PctRemovedMeanNonPositive": False,
        "fewerThanThreePositiveMeanYears": False,
        "top1PctPositiveTailAtLeastHalf": False,
    }


def test_source_validation_rejects_validation_or_oos() -> None:
    source = {
        "status": "PHASE1_B3_DEVELOPMENT_DESCRIPTIVE_COMPLETE",
        "benchmark": "B3_COMPANY_NET_BUYING_V1",
        "resultClass": "research/descriptive",
        "formalAlphaClaimed": False,
        "period": "2016-2020 XNYS evaluation-session cohort",
        "outcomeMarketBoundary": "2016-2022 only",
        "primaryHorizonSessions": 126,
        "horizonsSessions": [21, 63, 126, 252],
        "coverageTier": "C_EXPLORATORY",
        "validationPerformanceComputed": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "b3DefinitionChanged": False,
        "eventConstructionChanged": False,
        "identityDefinitionChanged": False,
    }
    try:
        b3._validate_source_summary(source)
    except ValueError as exc:
        assert "validation performance" in str(exc)
    else:
        raise AssertionError("opened validation must fail closed")


def test_reproduction_matches_source_summary(tmp_path: Path) -> None:
    rows = []
    horizons = {}
    for horizon in (21, 63, 126, 252):
        rows.append(
            {
                "issuerCik": "0000000001",
                "entrySession": "2019-01-03",
                "evaluationSession": "2019-01-02",
                f"excess_{horizon}": "0.05",
            }
        )
        horizons[str(horizon)] = {
            "maturedOutcomeCount": 1,
            "spyExcessMean": 0.05,
            "spyExcessMedian": 0.05,
            "spyExcessWinRate": 1.0,
        }

    # Reproduction helper receives wide rows, so combine horizon values into one.
    wide = {
        "issuerCik": "0000000001",
        "entrySession": "2019-01-03",
        "evaluationSession": "2019-01-02",
        "excess_21": "0.05",
        "excess_63": "0.05",
        "excess_126": "0.05",
        "excess_252": "0.05",
    }
    result = b3._reproduction([wide], {"horizons": horizons})
    assert result["126"]["maturedOutcomeCount"] == 1
    assert result["126"]["spyExcessMean"] == 0.05
