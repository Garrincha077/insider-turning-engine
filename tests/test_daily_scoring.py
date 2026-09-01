from __future__ import annotations

from datetime import UTC, datetime

import pytest

from insider_turning_engine.domain.scoring_lock import load_scoring_lock
from insider_turning_engine.pipeline.scoring import DailyScoringError, assemble_daily_scores

_AS_OF = datetime(2026, 8, 31, 20, tzinfo=UTC)


def _rows() -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for when in ("2026-06-01", "2026-08-20"):
        output.append(
            {
                "issuer_cik": "0000123456",
                "owner_cik": "0000654321",
                "transaction_date": when,
                "knowledge_at": f"{when}T20:00:00Z",
                "accepted_at": f"{when}T20:00:00Z",
                "code": "P",
                "acquired_disposed": "A",
                "table_type": "NON_DERIVATIVE",
                "lifecycle_status": "ACTIVE",
                "shares": 1_000,
                "price_per_share": 10,
                "value": 10_000,
                "relationship": {"is_officer": True},
            }
        )
    return output


def _context() -> list[dict[str, object]]:
    return [
        {
            "issuer_cik": "0000123456",
            "date": "2026-08-31",
            "knowledge_at": "2026-08-31T19:00:00Z",
            "close": 20,
            "return_3m": -0.10,
            "drawdown_from_52_week_high": -0.30,
            "price_weakness_score": 90,
            "no_new_52_week_low_20_sessions": True,
            "volatility_contraction": True,
            "volume_dryup": True,
            "ma20_flattening": True,
            "close_above_ma20": True,
            "current_percentile": 80,
            "slope_percentile": 80,
            "level": 5,
            "mansfield_slope_percentile": 80,
            "signed_volume_ratio": 0.20,
            "prior_percentile": 80,
            "ma50": 25,
            "close_above_ma50_days_last10": 0,
            "ordinary_rs_improving_4w": True,
            "mansfield_market_slope_4w": 1,
        }
    ]


def test_complete_daily_scoring_golden_case_is_ranked_and_provenanced() -> None:
    result = assemble_daily_scores(
        _rows(),
        _context(),
        {"0000123456": "ACME"},
        {},
        as_of=_AS_OF,
        run_id="run_daily_scoring_golden",
        quality={
            "canonical_valid": True,
            "stale_benchmark": False,
            "parse_success_rate": 1.0,
            "market_data_coverage_rate": 1.0,
            "core_branch_coverage_rate": 1.0,
        },
    )

    lock = load_scoring_lock()
    assert result.signals[0]["total_score"] == pytest.approx(70.631579)
    assert result.signals[0]["issuer_cik"] == "0000123456"
    assert result.components[0]["total"]["methodology_hash"] == lock.methodology_hash
    assert result.signals[0]["methodology_hash"] == lock.methodology_hash
    assert result.signals[0]["run_id"] == "run_daily_scoring_golden"
    assert "STALE_DATA_HOLD" not in result.signals[0]["reason_codes"]


def test_missing_component_holds_and_future_context_fails() -> None:
    stale_context = _context()
    stale_context[0].pop("signed_volume_ratio")
    held = assemble_daily_scores(
        _rows(),
        stale_context,
        {"0000123456": "ACME"},
        {"0000123456": {"state": "BASE_FORMING", "failed_evaluations": 1}},
        as_of=_AS_OF,
        run_id="run_daily_scoring_hold",
    )
    assert held.signals[0]["total_score"] is None
    assert held.signals[0]["state"] == "BASE_FORMING"
    assert "STALE_DATA_HOLD" in held.signals[0]["reason_codes"]
    assert held.alerts == ()

    future = _context()
    future[0]["knowledge_at"] = "2026-09-01T00:00:00Z"
    with pytest.raises(DailyScoringError, match="later than as_of"):
        assemble_daily_scores(
            _rows(),
            future,
            {"0000123456": "ACME"},
            {},
            as_of=_AS_OF,
            run_id="run_daily_scoring_future",
        )
