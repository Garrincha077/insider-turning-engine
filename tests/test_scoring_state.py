import json
import math
from pathlib import Path

import pytest

from insider_turning_engine.scoring import (
    DEFAULT_LOCK,
    CompanyState,
    ScoreEngine,
    ScoreValidationError,
    StateMachine,
)


def test_score_weights_and_null_fundamental_renormalization() -> None:
    engine = ScoreEngine()
    insider = engine.company_insider(
        conviction=80,
        cluster=70,
        opportunistic=60,
        net_buying_absence_sales=90,
    )
    assert insider.score == pytest.approx(74.5)
    total = engine.total(
        divergence=80,
        conviction=70,
        cluster=60,
        opportunistic=50,
        base=40,
        ordinary_rs=30,
        mansfield_rs=20,
        volume=10,
    )
    expected = (
        80 * 0.25
        + 70 * 0.15
        + 60 * 0.10
        + 50 * 0.10
        + 40 * 0.10
        + 30 * 0.10
        + 20 * 0.10
        + 10 * 0.05
    ) / 0.95
    assert total.score == pytest.approx(expected)
    assert total.components["fundamental"] is None
    assert total.confidence == pytest.approx(8 / 9)
    assert total.score_config_hash.startswith("sha256:")
    assert total.score_lineage.startswith("config/scoring.v1.yaml@")
    assert total.score_lineage.endswith("@" + total.score_config_hash)
    assert total.frozen_at == engine.score_frozen_at_iso
    assert total.score_source_commit == engine.score_source_commit


def test_score_lock_rejects_hash_and_timestamp_tampering(tmp_path: Path) -> None:
    lock = json.loads(DEFAULT_LOCK.read_text(encoding="utf-8"))
    lock["scoreConfigHash"] = "sha256:" + "0" * 64
    forged = tmp_path / "forged.lock.json"
    forged.write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises(ScoreValidationError, match="lock hash"):
        ScoreEngine(lock_path=forged)

    lock = json.loads(DEFAULT_LOCK.read_text(encoding="utf-8"))
    lock["status"] = "FROZEN"
    lock["frozenAt"] = "not-a-timestamp"
    forged.write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises(ScoreValidationError, match="canonical UTC timestamp"):
        ScoreEngine(lock_path=forged)


def test_score_rejects_missing_future_like_and_non_finite_inputs() -> None:
    engine = ScoreEngine()
    with pytest.raises(ScoreValidationError, match="cluster is required"):
        engine.company_insider(conviction=80, opportunistic=50, net_buying_absence_sales=50)
    with pytest.raises(ScoreValidationError, match="finite"):
        engine.turn(
            base_structure=50,
            ordinary_rs_turn=50,
            mansfield_market=math.inf,
            mansfield_sector=50,
            volume_accumulation=50,
            cost_basis_reclaim=50,
        )


def test_state_machine_promotes_one_state_at_a_time_and_confirms() -> None:
    machine = StateMachine()
    accumulation = {
        "drawdown_from_52_week_high": -0.30,
        "company_insider_score": 80,
        "qualified_buy_age_days": 4,
        "no_new_52_week_low_20_sessions": True,
        "volatility_contraction": True,
        "volume_dryup": True,
        "ma20_flattening": True,
        "turn_score": 80,
        "ordinary_rs_improving_4w": True,
        "mansfield_market_slope_4w": 1.0,
        "close_above_ma50_days_last10": 7,
        "mansfield_market": 1.0,
    }
    first = machine.evaluate(CompanyState.FALLING, accumulation)
    assert first.state is CompanyState.INSIDER_ACCUMULATION
    second = machine.evaluate(first.state, accumulation)
    assert second.state is CompanyState.BASE_FORMING
    third = machine.evaluate(second.state, accumulation)
    assert third.state is CompanyState.EARLY_TURN
    fourth = machine.evaluate(third.state, accumulation)
    assert fourth.state is CompanyState.CONFIRMED_TURN


def test_state_hysteresis_and_new_low_reset() -> None:
    machine = StateMachine()
    one = machine.evaluate(CompanyState.EARLY_TURN, {}, consecutive_failed_evaluations=0)
    assert one.state is CompanyState.EARLY_TURN
    assert one.failed_evaluations == 1
    two = machine.evaluate(
        CompanyState.EARLY_TURN,
        {},
        consecutive_failed_evaluations=one.failed_evaluations,
    )
    assert two.state is CompanyState.BASE_FORMING
    reset = machine.evaluate(CompanyState.CONFIRMED_TURN, {"new_52_week_low": True})
    assert reset.state is CompanyState.FALLING
    assert reset.reason_codes == ("NEW_52W_LOW_RESET",)


def test_falling_uses_negative_return_and_below_ma50_predicate() -> None:
    machine = StateMachine()
    falling = machine.evaluate(
        CompanyState.FALLING,
        {"return_3m": -0.10, "close": 90, "ma50": 100},
    )
    assert falling.reason_codes == ("STATE_HELD",)

    outside = machine.evaluate(
        CompanyState.FALLING,
        {"return_3m": 0.10, "close": 110, "ma50": 100},
    )
    assert outside.state is CompanyState.FALLING
    assert "FALLING_PREDICATE_NOT_MET" in outside.reason_codes
