from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from statistics import stdev

import polars as pl
import pytest

from insider_turning_engine.features.price import (
    latest_price_facts,
    price_features,
    weekly_bars_frame,
)
from insider_turning_engine.features.rs import (
    relative_strength_features,
    rolling_four_week_slopes,
)
from insider_turning_engine.ingestion.market import DailyBar


def _bars(symbol: str = "ACME", count: int = 70) -> list[DailyBar]:
    result: list[DailyBar] = []
    current = date(2025, 1, 1)
    while len(result) < count:
        if current.weekday() < 5:
            close = Decimal(str(100 + len(result)))
            result.append(
                DailyBar(
                    date=current,
                    symbol=symbol,
                    open=close,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                    volume=100,
                )
            )
        current += timedelta(days=1)
    return result


def test_price_features_are_bounded_and_50d_3m_facts_are_session_based() -> None:
    bars = _bars()
    as_of = bars[-1].date
    facts = price_features(bars, as_of=as_of)
    latest = latest_price_facts(bars, as_of=as_of).row(0, named=True)
    assert facts.height == 70
    assert latest["ma50"] == pytest.approx(sum(range(120, 170)) / 50)
    assert latest["return_3m"] == pytest.approx(169 / 106 - 1)
    assert latest["close_above_ma50"] is True
    returns = [((100 + index) / (99 + index)) - 1 for index in range(50, 70)]
    assert latest["volatility_20d"] == pytest.approx(stdev(returns))
    assert latest["prior_volatility_20d"] == pytest.approx(
        stdev([((100 + index) / (99 + index)) - 1 for index in range(30, 50)])
    )
    assert latest["median_volume_20d"] == 100
    assert latest["prior_median_volume_20d"] == 100
    assert latest["ma20_slope_5d"] == pytest.approx(1)
    assert latest["signed_volume_ratio_20d"] == pytest.approx(1)

    with pytest.raises(ValueError, match="after as_of"):
        price_features(bars, as_of=as_of - timedelta(days=1))


def test_weekly_ohlcv_uses_last_observed_session() -> None:
    weekly = weekly_bars_frame(_bars(count=10), as_of=date(2025, 1, 20))
    assert weekly.get_column("date").to_list() == [
        date(2025, 1, 3),
        date(2025, 1, 10),
        date(2025, 1, 14),
    ]
    assert weekly.get_column("volume").to_list() == [300, 500, 200]


def test_date_only_price_cutoff_excludes_post_close_provider_row() -> None:
    frame = pl.DataFrame(
        {
            "date": [date(2025, 1, 2), date(2025, 1, 3)],
            "symbol": ["ACME", "ACME"],
            "close": [10.0, 11.0],
            "provider": ["stooq", "stooq"],
            "available_at": [
                datetime(2025, 1, 2, 21, 0, tzinfo=UTC),
                datetime(2025, 1, 3, 21, 0, 1, tzinfo=UTC),
            ],
        }
    )

    result = price_features(frame, as_of=date(2025, 1, 3))
    assert result.get_column("date").to_list() == [date(2025, 1, 2)]


def test_split_quarantine_nulls_derived_facts() -> None:
    bars = _bars(count=4)
    bars[2] = DailyBar(
        date=bars[2].date, symbol="ACME", open=50, high=51, low=49, close=50, volume=100
    )
    facts = price_features(bars, as_of=bars[-1].date)
    assert facts.get_column("split_quarantine").to_list() == [True] * 4
    assert facts.get_column("return_3m").null_count() == 4
    for name in (
        "volatility_20d",
        "prior_volatility_20d",
        "median_volume_20d",
        "prior_median_volume_20d",
        "ma20_slope_5d",
        "signed_volume_ratio_20d",
    ):
        assert facts.get_column(name).null_count() == 4


def test_technical_windows_are_session_based_and_null_until_available() -> None:
    bars = _bars(count=41)
    facts = price_features(bars, as_of=bars[-1].date)
    latest = facts.tail(1).row(0, named=True)
    assert latest["median_volume_20d"] == 100
    assert latest["prior_median_volume_20d"] == 100
    assert latest["volatility_20d"] is not None
    assert latest["prior_volatility_20d"] is not None
    assert latest["ma20_slope_5d"] is not None
    assert latest["signed_volume_ratio_20d"] is not None

    early = price_features(_bars(count=20), as_of=bars[19].date).tail(1).row(0, named=True)
    assert early["median_volume_20d"] == 100
    for name in (
        "volatility_20d",
        "prior_volatility_20d",
        "prior_median_volume_20d",
        "ma20_slope_5d",
        "signed_volume_ratio_20d",
    ):
        assert early[name] is None


def test_four_week_slope_has_no_lookahead_and_zero_is_not_positive() -> None:
    frame = pl.DataFrame(
        {
            "symbol": ["A"] * 5,
            "date": [
                date(2025, 1, 3),
                date(2025, 1, 10),
                date(2025, 1, 17),
                date(2025, 1, 24),
                date(2025, 1, 31),
            ],
            "ordinary_rs_3m": [10.0, 10.0, 10.0, 10.0, 1000.0],
        }
    )
    result = rolling_four_week_slopes(frame)
    slopes = result.get_column("ordinary_rs_3m_slope_4w").to_list()
    assert slopes[:3] == [None, None, None]
    assert slopes[3] == pytest.approx(0)
    assert slopes[4] > 0
    assert result.get_column("ordinary_rs_improving_4w").to_list()[3] is False


def test_relative_strength_ranks_only_insider_active_universe() -> None:
    rows: list[dict[str, object]] = []
    session = date(2024, 1, 2)
    index = 0
    while index < 300:
        if session.weekday() < 5:
            for symbol, rate in (("ACME", 0.003), ("BETA", -0.001), ("SPY", 0.001)):
                close = 100.0 * (1.0 + rate) ** index
                rows.append(
                    {
                        "date": session,
                        "symbol": symbol,
                        "open": close,
                        "high": close,
                        "low": close,
                        "close": close,
                        "adj_close": close,
                        "volume": 1_000,
                        "is_adjusted": True,
                    }
                )
            index += 1
        session += timedelta(days=1)
    result = relative_strength_features(
        pl.DataFrame(rows),
        as_of=rows[-1]["date"],
        market_symbol="SPY",
        universe_symbols=["ACME", "BETA"],
    )
    latest = {
        row["symbol"]: row
        for row in result.sort("date").group_by("symbol").tail(1).to_dicts()
    }
    assert set(latest) == {"ACME", "BETA"}
    assert latest["ACME"]["ordinary_rs_3m"] == pytest.approx(100)
    assert latest["BETA"]["ordinary_rs_3m"] == pytest.approx(0)
    assert latest["ACME"]["mansfield_market"] is not None
