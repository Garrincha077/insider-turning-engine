from datetime import UTC, date, datetime

import polars as pl
import pytest

from insider_turning_engine.features.conviction import conviction_features
from insider_turning_engine.features.cost_basis import (
    cost_basis_reclaim_facts,
    qualified_non_derivative_purchases,
    weighted_cost_basis,
)


def _purchases() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "issuer_cik": ["0000000001"] * 4,
            "owner_cik": ["0000000002"] * 4,
            "transaction_date": [
                date(2025, 12, 1),
                date(2026, 1, 15),
                date(2026, 3, 1),
                date(2026, 3, 2),
            ],
            "code": ["P", "P", "P", "P"],
            "acquired_disposed": ["A"] * 4,
            "table_type": ["NON_DERIVATIVE"] * 4,
            "shares": [100.0, 50.0, 10.0, 20.0],
            "price_per_share": [10.0, 8.0, 7.0, 6.0],
            "value_usd": [1000.0, 400.0, 70.0, 120.0],
            "role": ["DIRECTOR"] * 4,
        }
    )


def test_conviction_golden_explains_first_and_largest_purchase() -> None:
    result = conviction_features(
        _purchases().head(1),
        as_of=date(2025, 12, 1),
        market_context={"0000000001": {"drawdown_from_52_week_high": -0.25}},
        cluster_context={"0000000001": {"cluster_score": 80}},
    ).row(0, named=True)
    assert result["first_buy"] is True
    assert result["largest_buy"] is True
    assert result["conviction_score"] == pytest.approx(71.0)
    assert {"FIRST_BUY", "LARGEST_BUY", "DRAWDOWN_OR_AVERAGING", "CLUSTER_CONTEXT"}.issubset(
        result["reason_codes"]
    )
    assert result["confidence"] == "HIGH"


def test_qualified_selection_and_weighted_calendar_windows() -> None:
    frame = _purchases().vstack(
        pl.DataFrame(
            {
                "issuer_cik": ["0000000001"],
                "owner_cik": ["0000000002"],
                "transaction_date": [date(2026, 2, 20)],
                "code": ["P"],
                "acquired_disposed": ["A"],
                "table_type": ["DERIVATIVE"],
                "shares": [999.0],
                "price_per_share": [1.0],
                "value_usd": [999.0],
                "role": ["DIRECTOR"],
            }
        )
    )
    selected = qualified_non_derivative_purchases(frame, as_of=date(2026, 3, 2))
    assert selected.height == 4
    result = weighted_cost_basis(frame, as_of=date(2026, 3, 2)).row(0, named=True)
    assert result["cost_basis_30d"] == pytest.approx((70 + 120) / 30)
    assert result["cost_basis_90d"] == pytest.approx((400 + 70 + 120) / 80)


def test_conviction_rejects_late_filing_and_market_rows() -> None:
    frame = (
        _purchases()
        .head(1)
        .with_columns(pl.lit(datetime(2026, 3, 3, tzinfo=UTC)).alias("accepted_at"))
    )
    with pytest.raises(ValueError, match="accepted_at"):
        conviction_features(frame, as_of=date(2026, 3, 2))
    with pytest.raises(ValueError, match="market row dated"):
        cost_basis_reclaim_facts(
            _purchases().head(1),
            as_of=date(2026, 3, 2),
            market=pl.DataFrame(
                {"symbol": ["0000000001"], "date": [date(2026, 3, 3)], "close": [12.0]}
            ),
        )


def test_cost_basis_reclaim_is_inclusive_and_future_purchase_cannot_leak() -> None:
    as_of = date(2026, 3, 2)
    result = cost_basis_reclaim_facts(
        _purchases(),
        as_of=as_of,
        market=pl.DataFrame({"symbol": ["0000000001"], "date": [as_of], "close": [7.0]}),
    ).row(0, named=True)
    assert result["cost_basis_reclaim_30d"] is True
    assert result["cost_basis_reclaim"] is False
    assert result["confidence"] == "HIGH"


def test_json_lifecycle_mapping_excludes_void_rows() -> None:
    row = {
        "issuer": {"cik": "0000000001"},
        "reporting_owner": {"cik": "0000000002"},
        "security": {"table_type": "NON_DERIVATIVE"},
        "transaction": {
            "transaction_date": "2026-03-02",
            "code": "P",
            "acquired_disposed": "A",
            "shares": 10,
            "price_per_share": 10,
            "value": 100,
        },
        "lifecycle": {"status": "VOID"},
    }
    assert conviction_features([row], as_of=date(2026, 3, 2)).is_empty()
