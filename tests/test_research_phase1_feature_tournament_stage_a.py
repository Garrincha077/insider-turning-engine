from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_feature_tournament_stage_a")


def test_quintiles_use_frozen_linear_empirical_method() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    q = mod._quintiles(values)
    assert q == {
        "q20": 1.8,
        "q40": 2.6,
        "q60": 3.4,
        "q80": 4.2,
    }


def test_general_coverage_requires_every_year_floor() -> None:
    annual = {
        2016: (40, 100),
        2017: (40, 100),
        2018: (40, 100),
        2019: (40, 100),
        2020: (40, 100),
    }
    assert mod._coverage_class(250, 500, annual) == "GENERAL_ELIGIBLE"


def test_specialty_coverage_when_general_floor_fails() -> None:
    annual = {
        2016: (20, 100),
        2017: (20, 100),
        2018: (20, 100),
        2019: (20, 100),
        2020: (20, 100),
    }
    assert mod._coverage_class(100, 500, annual) == "SPECIALTY_ELIGIBLE"


def test_below_specialty_is_not_advanced() -> None:
    annual = {
        2016: (5, 100),
        2017: (5, 100),
        2018: (5, 100),
        2019: (5, 100),
        2020: (5, 100),
    }
    assert mod._coverage_class(25, 500, annual) == "BELOW_SPECIALTY"


def test_historical_superseded_revision_is_active_inside_its_interval() -> None:
    cutoff = datetime(2018, 6, 1, 20, tzinfo=UTC)
    row = {
        "_valid_from": datetime(2018, 1, 1, tzinfo=UTC),
        "_valid_to": datetime(2018, 7, 1, tzinfo=UTC),
        "_knowledge": datetime(2018, 1, 1, tzinfo=UTC),
        "lifecycle": {"status": "SUPERSEDED"},
        "security": {"tableType": "NON_DERIVATIVE"},
        "transaction": {
            "code": "P",
            "acquiredDisposed": "A",
            "economicClassification": "OPEN_MARKET_PURCHASE",
            "shares": "100",
            "pricePerShare": "10",
        },
    }
    assert mod._active_purchases([row], cutoff) == [row]


def test_revision_is_not_active_after_valid_to() -> None:
    cutoff = datetime(2018, 8, 1, 20, tzinfo=UTC)
    row = {
        "_valid_from": datetime(2018, 1, 1, tzinfo=UTC),
        "_valid_to": datetime(2018, 7, 1, tzinfo=UTC),
        "_knowledge": datetime(2018, 1, 1, tzinfo=UTC),
        "lifecycle": {"status": "SUPERSEDED"},
        "security": {"tableType": "NON_DERIVATIVE"},
        "transaction": {
            "code": "P",
            "acquiredDisposed": "A",
            "economicClassification": "OPEN_MARKET_PURCHASE",
            "shares": "100",
            "pricePerShare": "10",
        },
    }
    assert mod._active_purchases([row], cutoff) == []


def test_void_revision_is_never_feature_evidence() -> None:
    cutoff = datetime(2018, 6, 1, 20, tzinfo=UTC)
    row = {
        "_valid_from": datetime(2018, 1, 1, tzinfo=UTC),
        "_valid_to": None,
        "_knowledge": datetime(2018, 1, 1, tzinfo=UTC),
        "lifecycle": {"status": "VOID"},
        "security": {"tableType": "NON_DERIVATIVE"},
        "transaction": {
            "code": "P",
            "acquiredDisposed": "A",
            "economicClassification": "OPEN_MARKET_PURCHASE",
            "shares": "100",
            "pricePerShare": "10",
        },
    }
    assert mod._active_purchases([row], cutoff) == []


def test_f4_persistence_definition_is_backward_looking() -> None:
    rows = [
        ("2018-01-01", 9.0, 9.0, 9.0, 9.0, 100, 10, 0),
        ("2018-01-02", 10.5, 10.5, 10.5, 10.5, 100, 10, 0),
        ("2018-01-03", 10.6, 10.6, 10.6, 10.6, 100, 10, 0),
    ]
    idx = mod._at_or_before(rows, "2018-01-03")
    assert idx == 2
    basis = 10.0
    persist2 = (
        float(rows[idx - 2][4]) < basis
        and all(float(rows[i][4]) >= basis for i in range(idx - 1, idx + 1))
    )
    assert persist2 is True
