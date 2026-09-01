"""Deterministic, point-in-time price transforms.

The feature layer accepts the provider-neutral :class:`DailyBar` contract as
well as a Polars frame.  It deliberately does not know about a provider: a
slice is bounded before any rolling expression is evaluated and a row dated
after ``as_of`` is an error rather than an silently ignored observation.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

import polars as pl

from insider_turning_engine.domain.time import us_equity_session_close
from insider_turning_engine.ingestion.market.base import DailyBar

BarsInput = (
    pl.DataFrame
    | pl.LazyFrame
    | Sequence[DailyBar]
    | Iterable[DailyBar]
    | Mapping[str, Sequence[DailyBar]]
)


def _as_date(value: date | datetime | None) -> date:
    if value is None:
        return date.today()
    return value.date() if isinstance(value, datetime) else value


def _date_value(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _raw_frame(bars: BarsInput) -> pl.DataFrame:
    """Convert supported inputs to a canonical, eager Polars frame."""

    if isinstance(bars, pl.LazyFrame):
        return bars.collect()
    if isinstance(bars, pl.DataFrame):
        frame = bars.clone()
        if "symbol" not in frame.columns and "ticker" in frame.columns:
            frame = frame.rename({"ticker": "symbol"})
        return frame
    if isinstance(bars, Mapping):
        rows: list[DailyBar] = []
        for values in bars.values():
            for value in values:
                rows.append(value)
    else:
        rows = list(bars)

    if not rows:
        return pl.DataFrame(
            schema={
                "date": pl.Date,
                "symbol": pl.String,
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "adj_close": pl.Float64,
                "volume": pl.Int64,
                "is_adjusted": pl.Boolean,
                "split_factor": pl.Float64,
            }
        )
    records: list[dict[str, Any]] = []
    for value in rows:
        if isinstance(value, DailyBar):
            records.append(
                {
                    "date": value.date,
                    "symbol": value.symbol,
                    "open": float(value.open),
                    "high": float(value.high),
                    "low": float(value.low),
                    "close": float(value.close),
                    "adj_close": float(value.adj_close) if value.adj_close is not None else None,
                    "volume": value.volume,
                    "available_at": value.available_at,
                    "is_adjusted": value.is_adjusted,
                    "adjustment_basis": value.adjustment_basis,
                    "split_factor": (
                        float(value.split_factor) if value.split_factor is not None else None
                    ),
                    "provider_record_id": value.provider_record_id,
                    "provider": value.provider,
                }
            )
    frame = pl.DataFrame(records)
    if "ticker" in frame.columns and "symbol" not in frame.columns:
        frame = frame.rename({"ticker": "symbol"})
    return frame


def _prepare(
    bars: BarsInput,
    *,
    as_of: date | datetime | None,
    start: date | None = None,
    end: date | None = None,
) -> pl.DataFrame:
    cutoff = _as_date(as_of)
    frame = _raw_frame(bars)
    required = {"date", "symbol", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"market frame missing required columns: {sorted(missing)}")
    if frame.is_empty():
        return frame
    if frame.schema.get("date") != pl.Date:
        frame = frame.with_columns(pl.col("date").cast(pl.Date, strict=True))
    future = frame.filter(pl.col("date") > pl.lit(cutoff))
    if not future.is_empty():
        first = future.select(pl.col("date").min()).item()
        raise ValueError(f"market row dated after as_of: {first}")
    if "available_at" in frame.columns:
        # Availability is an eligibility clock, not a reason to move event
        # dates. Explicit synthetic/unknown fixtures may omit it; provider
        # rows must carry a pinned timestamp and are filtered at full precision.
        available = pl.col("available_at").cast(pl.Datetime(time_zone="UTC"), strict=False)
        cutoff_stamp = as_of if isinstance(as_of, datetime) else us_equity_session_close(cutoff)
        if cutoff_stamp.tzinfo is None:
            cutoff_stamp = cutoff_stamp.replace(tzinfo=UTC)
        cutoff_stamp = cutoff_stamp.astimezone(UTC)
        provider = pl.col("provider") if "provider" in frame.columns else pl.lit("unknown")
        frame = frame.filter(
            available.is_not_null() & (available <= pl.lit(cutoff_stamp))
            | (available.is_null() & provider.is_in(["unknown", "fixture", "synthetic"]))
        )
    frame = frame.filter(pl.col("date") <= pl.lit(cutoff))
    if start is not None:
        frame = frame.filter(pl.col("date") >= pl.lit(start))
    if end is not None:
        frame = frame.filter(pl.col("date") <= pl.lit(end))
    if frame.is_empty():
        return frame
    frame = frame.with_columns(
        pl.col("symbol").cast(pl.String).str.to_uppercase(),
        pl.col("close").cast(pl.Float64, strict=False).fill_nan(None),
    )
    if "adj_close" not in frame.columns:
        frame = frame.with_columns(pl.col("close").alias("adj_close"))
    else:
        frame = frame.with_columns(pl.col("adj_close").fill_null(pl.col("close")))
    if "volume" not in frame.columns:
        frame = frame.with_columns(pl.lit(None, dtype=pl.Int64).alias("volume"))
    if "is_adjusted" not in frame.columns:
        frame = frame.with_columns(pl.lit(False).alias("is_adjusted"))
    if "split_factor" not in frame.columns:
        frame = frame.with_columns(pl.lit(None, dtype=pl.Float64).alias("split_factor"))
    return frame.sort(["symbol", "date"])


def daily_bars_frame(
    bars: BarsInput,
    *,
    as_of: date | datetime | None = None,
    start: date | None = None,
    end: date | None = None,
) -> pl.DataFrame:
    """Return eligible daily bars, sorted by symbol and session date."""

    return _prepare(bars, as_of=as_of, start=start, end=end)


transform_daily_bars = daily_bars_frame


def weekly_bars_frame(
    bars: BarsInput,
    *,
    as_of: date | datetime | None = None,
    start: date | None = None,
    end: date | None = None,
) -> pl.DataFrame:
    """Aggregate eligible sessions into Monday-anchored ISO weeks.

    The output date is the last observed session in the week, matching the
    market provider's weekly contract and avoiding synthetic weekend dates.
    """

    daily = _prepare(bars, as_of=as_of, start=start, end=end)
    if daily.is_empty():
        return daily
    daily = daily.with_columns(
        pl.col("date").dt.weekday().alias("_weekday"),
        (pl.col("date") - pl.duration(days=pl.col("date").dt.weekday() - 1)).alias("week_start"),
    )
    group = ["symbol", "week_start"]
    weekly = (
        daily.sort(group + ["date"])
        .group_by(group, maintain_order=True)
        .agg(
            pl.col("date").last().alias("date"),
            pl.col("open").first().alias("open"),
            pl.col("high").max().alias("high"),
            pl.col("low").min().alias("low"),
            pl.col("close").last().alias("close"),
            pl.col("adj_close").last().alias("adj_close"),
            pl.col("volume").sum().alias("volume"),
            pl.col("is_adjusted").all().alias("is_adjusted"),
            pl.col("split_factor").drop_nulls().last().alias("split_factor"),
        )
        .sort(["symbol", "date"])
    )
    return weekly.drop("_weekday", strict=False)


transform_weekly_bars = weekly_bars_frame


def _split_symbols(frame: pl.DataFrame) -> pl.DataFrame:
    """Find symbols with unexplained close discontinuities."""

    if frame.is_empty():
        return pl.DataFrame({"symbol": pl.Series([], dtype=pl.String)})
    ordered = frame.sort(["symbol", "date"]).with_columns(
        pl.col("close").shift(1).over("symbol").alias("_previous_close"),
        pl.col("is_adjusted").shift(1).over("symbol").alias("_previous_adjusted"),
    )
    broken = (
        ordered.filter(
            (pl.col("_previous_close") > 0)
            & (
                (pl.col("close") / pl.col("_previous_close") <= 0.5)
                | (pl.col("close") / pl.col("_previous_close") >= 2.0)
            )
            & ~(pl.col("is_adjusted") & pl.col("_previous_adjusted"))
        )
        .select("symbol")
        .unique()
    )
    return broken


def price_features(
    bars: BarsInput,
    *,
    as_of: date | datetime | None = None,
    split_quarantine: bool = True,
) -> pl.DataFrame:
    """Compute daily price facts needed by the state machine.

    Windows are trading-session windows: 20D, 50D and 52W are 20, 50 and 252
    observations respectively, and 3M is the 63-session return.  Insufficient
    history is represented by nulls.  A split-discontinuous symbol is marked
    and its derived values are null so downstream scoring cannot consume a
    fabricated trend.
    """

    frame = _prepare(bars, as_of=as_of)
    if frame.is_empty():
        return frame.with_columns(
            pl.lit(False).alias("split_quarantine"),
            pl.lit(None, dtype=pl.String).alias("quarantine_reason"),
            pl.lit(None, dtype=pl.Float64).alias("volatility_20d"),
            pl.lit(None, dtype=pl.Float64).alias("prior_volatility_20d"),
            pl.lit(None, dtype=pl.Float64).alias("median_volume_20d"),
            pl.lit(None, dtype=pl.Float64).alias("prior_median_volume_20d"),
            pl.lit(None, dtype=pl.Float64).alias("ma20_slope_5d"),
            pl.lit(None, dtype=pl.Float64).alias("signed_volume_ratio_20d"),
        )
    frame = (
        frame.with_columns(
            pl.col("close")
            .rolling_mean(window_size=50, min_samples=50)
            .over("symbol")
            .alias("ma50"),
            pl.col("close")
            .rolling_mean(window_size=20, min_samples=20)
            .over("symbol")
            .alias("ma20"),
            pl.col("close").shift(63).over("symbol").alias("close_3m_ago"),
            pl.col("close")
            .rolling_max(window_size=252, min_samples=1)
            .over("symbol")
            .alias("high_52w"),
            pl.col("close")
            .rolling_min(window_size=252, min_samples=1)
            .over("symbol")
            .alias("low_52w"),
            pl.col("close")
            .shift(1)
            .rolling_min(window_size=252, min_samples=1)
            .over("symbol")
            .alias("prior_low_52w"),
        )
        .with_columns(
            pl.when(pl.col("close_3m_ago") > 0)
            .then(pl.col("close") / pl.col("close_3m_ago") - 1.0)
            .otherwise(None)
            .alias("return_3m"),
            (pl.col("close") / pl.col("high_52w") - 1.0).alias("drawdown_from_52_week_high"),
            ((pl.col("prior_low_52w") > 0) & (pl.col("close") <= pl.col("prior_low_52w"))).alias(
                "new_52_week_low"
            ),
        )
        .with_columns(
            (
                ~pl.col("new_52_week_low")
                .cast(pl.Int8)
                .rolling_max(window_size=20, min_samples=20)
                .over("symbol")
                .cast(pl.Boolean)
            ).alias("no_new_52_week_low_20_sessions"),
            (pl.col("close") > pl.col("ma50")).alias("close_above_ma50"),
            pl.col("close")
            .gt(pl.col("ma50"))
            .cast(pl.Int8)
            .rolling_sum(window_size=10, min_samples=10)
            .over("symbol")
            .alias("close_above_ma50_days_last10"),
        )
    )
    # Raw facts for the locked base/volume transforms.  Every window is a
    # session window over each symbol, so weekends and missing sessions do not
    # silently become observations.  Adjusted closes are used for returns and
    # signed direction; raw volume remains the traded-volume denominator.
    frame = frame.with_columns(
        pl.col("adj_close")
        .cast(pl.Float64, strict=False)
        .fill_nan(None)
        .alias("_technical_adj_close"),
        pl.col("volume").cast(pl.Float64, strict=False).fill_nan(None).alias("_technical_volume"),
    ).with_columns(
        pl.when(
            (pl.col("_technical_adj_close") > 0)
            & (pl.col("_technical_adj_close").shift(1).over("symbol") > 0)
        )
        .then(
            pl.col("_technical_adj_close")
            / pl.col("_technical_adj_close").shift(1).over("symbol")
            - 1.0
        )
        .otherwise(None)
        .alias("_technical_return"),
    ).with_columns(
        pl.col("_technical_return")
        .rolling_std(window_size=20, min_samples=20)
        .over("symbol")
        .alias("volatility_20d"),
        pl.col("_technical_volume")
        .rolling_median(window_size=20, min_samples=20)
        .over("symbol")
        .alias("median_volume_20d"),
    ).with_columns(
        pl.col("volatility_20d")
        .shift(20)
        .over("symbol")
        .alias("prior_volatility_20d"),
        pl.col("median_volume_20d")
        .shift(20)
        .over("symbol")
        .alias("prior_median_volume_20d"),
        # OLS slope for x = 0..4: (-2*y0 - y1 + y3 + 2*y4) / 10.
        (
            -2.0 * pl.col("ma20").shift(4).over("symbol")
            - pl.col("ma20").shift(3).over("symbol")
            + pl.col("ma20").shift(1).over("symbol")
            + 2.0 * pl.col("ma20")
        )
        .truediv(10.0)
        .alias("ma20_slope_5d"),
    )
    frame = frame.with_columns(
        pl.when(
            (pl.col("_technical_volume") > 0)
            & (pl.col("_technical_adj_close") > 0)
            & (pl.col("_technical_adj_close").shift(1).over("symbol") > 0)
        )
        .then(
            pl.when(
                pl.col("_technical_adj_close")
                > pl.col("_technical_adj_close").shift(1).over("symbol")
            )
            .then(1.0)
            .when(
                pl.col("_technical_adj_close")
                < pl.col("_technical_adj_close").shift(1).over("symbol")
            )
            .then(-1.0)
            .otherwise(0.0)
            * pl.col("_technical_volume")
        )
        .otherwise(None)
        .alias("_signed_adjusted_volume"),
        pl.when(pl.col("_technical_volume") > 0)
        .then(pl.col("_technical_volume"))
        .otherwise(None)
        .alias("_positive_volume"),
    ).with_columns(
        (
            pl.col("_signed_adjusted_volume")
            .is_not_null()
            .cast(pl.Int8)
            .rolling_sum(window_size=20, min_samples=1)
            .over("symbol")
        ).alias("_signed_volume_valid_count"),
        pl.col("_signed_adjusted_volume")
        .rolling_sum(window_size=20, min_samples=1)
        .over("symbol")
        .alias("_signed_volume_numerator"),
        pl.col("_positive_volume")
        .rolling_sum(window_size=20, min_samples=1)
        .over("symbol")
        .alias("_signed_volume_denominator"),
    ).with_columns(
        pl.when(
            (pl.col("_signed_volume_valid_count") >= 20)
            & (pl.col("_signed_volume_denominator") > 0)
        )
        .then(pl.col("_signed_volume_numerator") / pl.col("_signed_volume_denominator"))
        .otherwise(None)
        .alias("signed_volume_ratio_20d")
    )
    if split_quarantine:
        bad = _split_symbols(frame).with_columns(pl.lit(True).alias("split_quarantine"))
        frame = frame.join(bad, on="symbol", how="left").with_columns(
            pl.col("split_quarantine").fill_null(False),
            pl.when(pl.col("split_quarantine"))
            .then(pl.lit("split_discontinuity"))
            .otherwise(None)
            .alias("quarantine_reason"),
        )
        derived = [
            "ma50",
            "ma20",
            "close_3m_ago",
            "return_3m",
            "high_52w",
            "low_52w",
            "prior_low_52w",
            "drawdown_from_52_week_high",
            "new_52_week_low",
            "no_new_52_week_low_20_sessions",
            "close_above_ma50",
            "close_above_ma50_days_last10",
            "volatility_20d",
            "prior_volatility_20d",
            "median_volume_20d",
            "prior_median_volume_20d",
            "ma20_slope_5d",
            "signed_volume_ratio_20d",
        ]
        frame = frame.with_columns(
            [
                pl.when(pl.col("split_quarantine")).then(None).otherwise(pl.col(c)).alias(c)
                for c in derived
            ]
        )
    else:
        frame = frame.with_columns(
            pl.lit(False).alias("split_quarantine"),
            pl.lit(None, dtype=pl.String).alias("quarantine_reason"),
        )
    return frame.drop(
        [
            "_technical_adj_close",
            "_technical_volume",
            "_technical_return",
            "_signed_adjusted_volume",
            "_positive_volume",
            "_signed_volume_valid_count",
            "_signed_volume_numerator",
            "_signed_volume_denominator",
        ],
        strict=False,
    )


def latest_price_facts(
    bars: BarsInput,
    *,
    as_of: date | datetime | None = None,
    split_quarantine: bool = True,
) -> pl.DataFrame:
    """Return one (latest eligible) row per symbol with state facts."""

    frame = price_features(bars, as_of=as_of, split_quarantine=split_quarantine)
    if frame.is_empty():
        return frame
    return frame.sort("date").group_by("symbol", maintain_order=True).tail(1).sort("symbol")


# Explicit aliases make the intended contract discoverable to callers that
# use ``build_*`` terminology while keeping the core functions concise.
build_price_features = price_features
compute_price_features = price_features
build_daily_bars = daily_bars_frame
build_weekly_bars = weekly_bars_frame

__all__ = [
    "daily_bars_frame",
    "weekly_bars_frame",
    "transform_daily_bars",
    "transform_weekly_bars",
    "price_features",
    "latest_price_facts",
    "build_price_features",
    "compute_price_features",
    "build_daily_bars",
    "build_weekly_bars",
]
