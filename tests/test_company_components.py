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
