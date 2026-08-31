from datetime import date, timedelta

import pytest

from insider_turning_engine.features.technical import (
    CostBasisObservation,
    Observation,
    base_structure_score,
    cost_basis_reclaim_score,
    mansfield_transform,
    mansfield_turn_score,
    midrank_percentile,
    ordinary_rs_turn_score,
    signed_volume_ratio,
    signed_volume_ratio_score,
    volume_accumulation_score,
)


def test_midrank_is_strictly_point_in_time_and_neutral_when_history_is_short() -> None:
    as_of = date(2026, 8, 31)
    observations = [
        Observation(as_of - timedelta(days=3), 10),
        Observation(as_of - timedelta(days=2), 20),
        Observation(as_of, 100),
    ]
    result = midrank_percentile(20, observations, as_of=as_of, min_history=2, history_size=2)
    assert result.score == pytest.approx(75)
    assert "LOW_CONFIDENCE_HISTORY" not in result.reason_codes

    short = midrank_percentile(20, observations, as_of=as_of, min_history=3, history_size=3)
    assert short.score == 50
    assert short.reason_codes == ("LOW_CONFIDENCE_HISTORY",)


def test_midrank_rejects_future_observation_and_excludes_future_knowledge() -> None:
    as_of = date(2026, 8, 31)
    with pytest.raises(ValueError, match="timestamp after"):
        midrank_percentile(
            20,
            [Observation(as_of + timedelta(days=1), 20)],
            as_of=as_of,
            min_history=1,
        )
    with pytest.raises(ValueError, match="known_at after"):
        midrank_percentile(
            20,
            [
                {
                    "date": as_of - timedelta(days=1),
                    "value": 10,
                    "known_at": as_of + timedelta(days=1),
                }
            ],
            as_of=as_of,
            min_history=1,
        )


def test_base_structure_uses_exact_weights_and_rejects_missing_facts() -> None:
    facts = {
        "no_new_52_week_low_20_sessions": True,
        "volatility_contraction": True,
        "volume_dryup": False,
        "ma20_flattening": True,
        "close_above_ma20": False,
    }
    assert base_structure_score(facts).score == 65
    missing = base_structure_score({**facts, "ma20_flattening": None})
    assert missing.score is None
    assert missing.reason_codes == ("INSUFFICIENT_COMPONENT_DATA",)

    raw = base_structure_score(
        {
            "no_new_52_week_low_20_sessions": True,
            "volatility_20d": 0.08,
            "prior_volatility_20d": 0.10,
            "median_volume_20d": 80,
            "prior_median_volume_20d": 100,
            "ma20_slope_5d": 0.10,
            "close": 100,
            "ma20": 99,
        }
    )
    assert raw.score == 100


def test_rs_mansfield_and_volume_golden_boundaries() -> None:
    assert ordinary_rs_turn_score(100, 0).score == 30
    assert ordinary_rs_turn_score(100, 100).score == 100
    assert mansfield_transform(-10) == 0
    assert mansfield_transform(0) == 50
    assert mansfield_transform(10) == 100
    assert mansfield_transform(-100) == 0
    assert mansfield_transform(100) == 100
    assert mansfield_turn_score(-10, 100).score == 70
    assert signed_volume_ratio_score(-0.10) == 0
    assert signed_volume_ratio_score(0.30) == 100
    assert volume_accumulation_score(0.30, 0).score == 50
    assert signed_volume_ratio([10, 11, 10], [1, 100, 50], sessions=2) == pytest.approx(1 / 3)


def test_cost_basis_reclaim_requires_a_recent_cross_from_below() -> None:
    as_of = date(2026, 8, 31)
    history = [
        CostBasisObservation(as_of - timedelta(days=12), 9, 10),
        CostBasisObservation(as_of - timedelta(days=9), 11, 10),
    ]
    assert cost_basis_reclaim_score(11, 10, history=history, as_of=as_of).score == 100
    assert cost_basis_reclaim_score(12, 10, history=(), as_of=as_of).score == 50
    assert cost_basis_reclaim_score(9, 10, history=history, as_of=as_of).score == 0
    assert cost_basis_reclaim_score(None, 10, as_of=as_of).score is None
