from datetime import UTC, date, datetime

import polars as pl
import pytest

from insider_turning_engine.features.pulse import market_pulse


def _rows() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "transaction_id": ["a", "b", "c", "d", "future"],
            "issuer_cik": ["1", "1", "2", "2", "3"],
            "owner_id": ["o1", "o2", "o3", "o4", "o5"],
            "sector": ["Technology", "Technology", "Financials", "Financials", "Technology"],
            "transaction_date": [
                date(2026, 8, 24),
                date(2026, 8, 24),
                date(2026, 8, 25),
                date(2026, 8, 25),
                date(2026, 8, 30),
            ],
            "code": ["P", "S", "P", "S", "P"],
            "shares": [100, 50, 20, 40, 1000],
            "value": [1000.0, 500.0, 200.0, 400.0, 10000.0],
            "conviction_score": [80.0, 60.0, 70.0, 90.0, 95.0],
            "knowledge_at": [
                datetime(2026, 8, 24, tzinfo=UTC),
                datetime(2026, 8, 24, tzinfo=UTC),
                datetime(2026, 8, 25, tzinfo=UTC),
                datetime(2026, 8, 25, tzinfo=UTC),
                datetime(2026, 8, 31, tzinfo=UTC),
            ],
        }
    )


def test_market_pulse_daily_and_sector_ratios_are_golden() -> None:
    result = market_pulse(_rows(), as_of=date(2026, 8, 30), grains=("daily",))
    market = result.filter(pl.col("scope") == "market").row(0, named=True)
    assert market["transaction_ps_ratio"] is None  # future P is not known on as_of
    assert market["quality_status"] == "WARN"

    result = market_pulse(_rows(), as_of=date(2026, 8, 25), grains=("weekly",))
    tech = result.filter(pl.col("sector") == "Technology").row(0, named=True)
    assert tech["transaction_ps_ratio"] == pytest.approx(1.0)
    assert tech["dollar_ratio"] == pytest.approx(2.0)
    assert tech["volume_ratio"] == pytest.approx(2.0)
    assert tech["company_breadth"] == pytest.approx(1.0)


def test_pulse_is_idempotent_and_future_rows_do_not_change_snapshot() -> None:
    as_of = date(2026, 8, 25)
    first = market_pulse(_rows(), as_of=as_of, grains=("weekly",)).sort("scope")
    future = _rows().filter(pl.col("transaction_date") > pl.lit(as_of))
    second = market_pulse(
        pl.concat([_rows().filter(pl.col("transaction_date") <= pl.lit(as_of)), future]),
        as_of=as_of,
        grains=("weekly",),
    ).sort("scope")
    assert first.equals(second)


def test_zero_denominators_are_null_with_explicit_reason() -> None:
    frame = _rows().filter(pl.col("code") == "P")
    row = (
        market_pulse(frame, as_of=date(2026, 8, 25), grains=("weekly",))
        .filter(pl.col("scope") == "market")
        .row(0, named=True)
    )
    assert row["transaction_ps_ratio"] is None
    assert row["dollar_ratio"] is None
    assert "UNKNOWN_DENOMINATOR:dollar_ratio" in row["quality_reasons"]
