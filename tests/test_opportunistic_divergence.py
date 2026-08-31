from datetime import UTC, date, datetime

import polars as pl
import pytest

from insider_turning_engine.features.cluster import cluster_features
from insider_turning_engine.features.divergence import divergence_features
from insider_turning_engine.features.opportunistic import opportunistic_features


def _trades(rows: list[tuple[str, date, str, float, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "issuer_cik": ["0000000001"] * len(rows),
            "owner_cik": [owner for owner, _, _, _, _ in rows],
            "transaction_date": [when for _, when, _, _, _ in rows],
            "code": [code for _, _, code, _, _ in rows],
            "acquired_disposed": ["A" if code == "P" else "D" for _, _, code, _, _ in rows],
            "shares": [value / price for _, _, _, value, price in rows],
            "price_per_share": [price for _, _, _, _, price in rows],
            "value_usd": [value for _, _, _, value, _ in rows],
        }
    )


def test_opportunistic_sparse_history_is_neutral_except_reentry() -> None:
    sparse = _trades(
        [
            ("owner", date(2025, 6, 1), "P", 100.0, 10.0),
            ("owner", date(2025, 12, 1), "S", 100.0, 12.0),
            ("owner", date(2026, 1, 1), "P", 100.0, 8.0),
        ]
    )
    sparse_row = opportunistic_features(sparse, as_of=date(2026, 1, 1)).row(-1, named=True)
    assert sparse_row["opportunistic_score"] == 50.0
    assert sparse_row["confidence"] == "LOW_CONFIDENCE"
    assert "NEUTRAL_INSUFFICIENT_HISTORY" in sparse_row["reason_codes"]

    reentry = _trades(
        [
            ("owner", date(2022, 1, 1), "P", 100.0, 12.0),
            ("owner", date(2026, 1, 1), "P", 100.0, 8.0),
        ]
    )
    row = opportunistic_features(reentry, as_of=date(2026, 1, 1)).row(-1, named=True)
    assert row["insider_reentry"] is True
    assert row["opportunistic_score"] == 90.0
    assert "INSIDER_REENTRY" in row["reason_codes"]


def test_cluster_uses_independent_owners_and_bounded_past_window() -> None:
    frame = _trades(
        [
            ("one", date(2026, 1, 1), "P", 100.0, 10.0),
            ("one", date(2026, 1, 2), "P", 100.0, 10.0),
            ("two", date(2026, 1, 3), "P", 100.0, 10.0),
            ("three", date(2026, 2, 2), "P", 100.0, 10.0),
        ]
    )
    result = cluster_features(frame, as_of=date(2026, 2, 2))
    first = result.row(0, named=True)
    assert first["strong_cluster"] is False
    final = result.row(-1, named=True)
    assert final["cluster_owner_count"] == 2
    assert final["important_cluster"] is True
    assert final["strong_cluster"] is False
    assert "IMPORTANT_CLUSTER" in final["reason_codes"]


def test_divergence_golden_uses_frozen_weights_and_strict_prior_windows() -> None:
    frame = _trades(
        [
            ("one", date(2025, 12, 15), "P", 50.0, 10.0),
            ("one", date(2026, 1, 15), "P", 100.0, 10.0),
            ("one", date(2026, 2, 20), "P", 50.0, 8.0),
        ]
    )
    row = divergence_features(
        frame,
        as_of=date(2026, 3, 1),
        price_context={"0000000001": {"price_weakness_score": 80.0}},
        cluster_context={"0000000001": {"cluster_score": 60.0}},
    ).row(0, named=True)
    assert row["insider_activity_percentile"] == pytest.approx(50.0)
    assert row["acceleration_cluster"] == pytest.approx(60.0)
    assert row["divergence_score"] == pytest.approx(67.5)
    assert row["confidence"] == "HIGH"


def test_features_reject_future_accepted_or_knowledge_rows() -> None:
    frame = _trades([("owner", date(2026, 1, 1), "P", 100.0, 10.0)]).with_columns(
        pl.lit(datetime(2026, 1, 2, tzinfo=UTC)).alias("knowledge_at")
    )
    with pytest.raises(ValueError, match="knowledge_at"):
        opportunistic_features(frame, as_of=date(2026, 1, 1))
    with pytest.raises(ValueError, match="knowledge_at"):
        cluster_features(frame, as_of=date(2026, 1, 1))
    with pytest.raises(ValueError, match="knowledge_at"):
        divergence_features(frame, as_of=date(2026, 1, 1))


def test_date_only_divergence_context_cutoff_is_us_session_close() -> None:
    trades = _trades([("owner", date(2026, 1, 2), "P", 100.0, 10.0)])

    with pytest.raises(ValueError, match="available_at"):
        divergence_features(
            trades,
            as_of=date(2026, 1, 2),
            price_context={
                "0000000001": {
                    "price_weakness_score": 80.0,
                    "available_at": datetime(2026, 1, 2, 21, 0, 1, tzinfo=UTC),
                }
            },
        )
