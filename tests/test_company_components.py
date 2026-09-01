from datetime import UTC, date, datetime

import pytest

from insider_turning_engine.scoring.components import (
    aggregate_company_insider_components,
    deterministic_reason_codes,
    prior_dollar_winsor_cap,
)


def _row(code: str, value: float, when: date, **scores: float) -> dict[str, object]:
    return {
        "transaction_date": when,
        "knowledge_at": datetime.combine(when, datetime.min.time(), tzinfo=UTC),
        "code": code,
        "table_type": "NON_DERIVATIVE",
        "lifecycle_status": "ACTIVE",
        "value_usd": value,
        **scores,
    }


def test_company_components_use_winsorized_dollar_weighted_buys() -> None:
    rows = [
        _row(
            "P",
            100,
            date(2026, 7, 1),
            conviction_score=60,
            opportunistic_score=40,
            cluster_score=70,
        ),
        _row(
            "P",
            300,
            date(2026, 7, 20),
            conviction_score=90,
            opportunistic_score=80,
            cluster_score=100,
        ),
        _row("S", 200, date(2026, 7, 25)),
    ]
    result = aggregate_company_insider_components(
        rows,
        as_of=date(2026, 8, 1),
        prior_universe_dollar_values=[200.0] * 200,
    )
    assert result.conviction == pytest.approx((60 * 100 + 90 * 200) / 300)
    assert result.opportunistic == pytest.approx((40 * 100 + 80 * 200) / 300)
    assert result.cluster == 100
    assert result.net_buying_absence_sales == pytest.approx(60.0)
    assert result.available is True


def test_sparse_winsor_history_is_flagged_but_does_not_invent_a_cap() -> None:
    cap, flags = prior_dollar_winsor_cap([100.0] * 199)
    assert cap is None
    assert flags == ("LOW_CONFIDENCE_WINSOR_HISTORY",)


def test_winsor_contract_validates_bounds_and_filters_non_finite_values() -> None:
    with pytest.raises(ValueError, match="percentile"):
        prior_dollar_winsor_cap([1.0], percentile=1.0)
    with pytest.raises(ValueError, match="minimum_observations"):
        prior_dollar_winsor_cap([1.0], minimum_observations=0)
    cap, flags = prior_dollar_winsor_cap(
        [10.0, 20.0, float("nan"), -1.0],
        percentile=0.5,
        minimum_observations=2,
    )
    assert cap == pytest.approx(15.0)
    assert flags == ()


def test_missing_required_company_component_is_explicit() -> None:
    result = aggregate_company_insider_components(
        [_row("S", 100, date(2026, 7, 1))], as_of=date(2026, 8, 1)
    )
    assert result.available is False
    assert "INSUFFICIENT_COMPONENT_DATA" in result.quality_flags


def test_company_components_reject_future_knowledge() -> None:
    row = _row("P", 100, date(2026, 8, 1), conviction_score=50)
    row["knowledge_at"] = datetime(2026, 8, 2, tzinfo=UTC)
    with pytest.raises(ValueError, match="knowledge_at"):
        aggregate_company_insider_components([row], as_of=date(2026, 8, 1))


def test_company_components_reject_naive_cutoff_and_future_transaction_date() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        aggregate_company_insider_components([], as_of=datetime(2026, 8, 1))
    future = _row("P", 100, date(2026, 8, 2), conviction_score=50)
    future["knowledge_at"] = datetime(2026, 8, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="transaction_date"):
        aggregate_company_insider_components(
            [future],
            as_of=date(2026, 8, 1),
        )


def test_company_components_derive_dollars_and_ignore_ineligible_rows() -> None:
    rows = [
        {
            "transaction_date": "2026-07-20",
            "knowledge_at": "2026-07-20T12:00:00Z",
            "code": "P",
            "table_type": "NON_DERIVATIVE",
            "lifecycle_status": "ACTIVE",
            "shares": 10,
            "price_per_share": 5,
            "conviction_score": 80,
            "opportunistic_score": 70,
            "cluster_score": 60,
        },
        _row("P", 1_000, date(2026, 7, 21), conviction_score=100),
        {
            **_row("S", 100, date(2026, 7, 22)),
            "table_type": "DERIVATIVE",
        },
        {"transaction_date": "not-a-date", "code": "P"},
    ]
    result = aggregate_company_insider_components(
        rows,
        as_of=date(2026, 8, 1),
        prior_universe_dollar_values=[100.0, 100.0],
        winsor_minimum_observations=2,
    )
    assert result.conviction == pytest.approx((80 * 50 + 100 * 100) / 150)
    assert result.opportunistic == 70
    assert result.cluster == 60
    assert result.net_buying_absence_sales == 100


def test_reason_codes_put_rules_before_stable_top_three_contributions() -> None:
    assert deterministic_reason_codes(
        ["first_buy", "cluster"],
        {"zeta": 100.0, "alpha": 50.0, "beta": 25.0, "unused": None},
        {"zeta": 0.1, "alpha": 0.4, "beta": 0.8, "unused": 0.1},
    ) == (
        "FIRST_BUY",
        "CLUSTER",
        "ALPHA_CONTRIBUTION",
        "BETA_CONTRIBUTION",
        "ZETA_CONTRIBUTION",
    )
