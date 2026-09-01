"""Relative-strength features, all evaluated at a bounded information cut."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime

import polars as pl

from .price import BarsInput, _prepare, price_features, weekly_bars_frame


def _clean(value: pl.Expr) -> pl.Expr:
    """Turn non-finite numeric results into the contract's null value."""

    return value.fill_nan(None)


def ordinary_relative_strength(
    bars: BarsInput | pl.DataFrame,
    *,
    as_of: date | datetime | None = None,
    universe_symbols: Sequence[str] | None = None,
) -> pl.DataFrame:
    """Add cross-sectional 3-month relative strength (0--100 percentile).

    Ranking is performed independently on each session, with average ranks for
    ties.  A singleton universe gets the neutral rank 50; a missing/invalid
    return remains null.  Percentile ranks use the full 0--100 range for a
    universe of two or more securities.
    """

    if isinstance(bars, pl.DataFrame) and "return_3m" in bars.columns:
        frame = _prepare(bars, as_of=as_of)
    else:
        frame = price_features(bars, as_of=as_of)
    if frame.is_empty():
        return frame.with_columns(pl.lit(None, dtype=pl.Float64).alias("ordinary_rs_3m"))
    if universe_symbols is not None:
        symbols = [str(item).strip().upper() for item in universe_symbols]
        frame = frame.filter(pl.col("symbol").is_in(symbols))
    valid = pl.col("return_3m").is_not_null() & pl.col("return_3m").is_finite()
    rank = pl.col("return_3m").rank(method="average").over("date")
    count = pl.col("return_3m").filter(valid).count().over("date")
    # ``rank`` includes nulls in the expression's window but returns null for
    # them; using the valid count keeps singleton/tie behavior explicit.
    rs = (
        pl.when(~valid)
        .then(None)
        .when(count <= 1)
        .then(50.0)
        .otherwise((rank - 1.0) / (count - 1.0) * 100.0)
    )
    return frame.with_columns(_clean(rs).alias("ordinary_rs_3m"))


def _benchmark_values(
    weekly: pl.DataFrame,
    benchmark: pl.DataFrame,
    benchmark_symbol: str,
) -> pl.DataFrame:
    """Join one benchmark's adjusted weekly closes to candidate rows."""

    if benchmark.is_empty():
        return weekly.with_columns(pl.lit(None, dtype=pl.Float64).alias("_benchmark_close"))
    benchmark_symbol = benchmark_symbol.strip().upper()
    reference = benchmark.filter(pl.col("symbol") == benchmark_symbol)
    if reference.is_empty():
        return weekly.with_columns(pl.lit(None, dtype=pl.Float64).alias("_benchmark_close"))
    reference = reference.select("date", pl.col("adj_close").alias("_benchmark_close")).unique(
        "date", keep="last"
    )
    return weekly.join(reference, on="date", how="left")


def _mansfield(
    weekly: pl.DataFrame,
    benchmark: pl.DataFrame,
    benchmark_symbol: str,
    name: str,
) -> pl.DataFrame:
    joined = _benchmark_values(weekly, benchmark, benchmark_symbol)
    ratio = (
        pl.when((pl.col("_benchmark_close") > 0) & (pl.col("adj_close") > 0))
        .then(pl.col("adj_close") / pl.col("_benchmark_close"))
        .otherwise(None)
    )
    ratio_name = f"_{name}_ratio"
    result = joined.with_columns(ratio.alias(ratio_name))
    mean_name = f"_{name}_ratio_mean"
    result = result.with_columns(
        pl.col(ratio_name)
        .rolling_mean(window_size=52, min_samples=52)
        .over("symbol")
        .alias(mean_name)
    ).with_columns(
        _clean(
            pl.when(pl.col(mean_name) > 0)
            .then((pl.col(ratio_name) / pl.col(mean_name) - 1.0) * 100.0)
            .otherwise(None)
        ).alias(name)
    )
    return result.select("symbol", "date", name)


def _sector_symbol_for(
    symbol: str,
    sector_by_symbol: Mapping[str, str] | None,
    sector_symbol: str | None,
) -> str | None:
    if sector_by_symbol is not None:
        value = sector_by_symbol.get(symbol) or sector_by_symbol.get(symbol.upper())
        return value.strip().upper() if value else None
    return sector_symbol.strip().upper() if sector_symbol else None


def relative_strength_features(
    bars: BarsInput,
    *,
    as_of: date | datetime | None = None,
    market_symbol: str = "SPY",
    sector_symbol: str | None = None,
    sector_by_symbol: Mapping[str, str] | None = None,
    market_bars: BarsInput | None = None,
    sector_bars: BarsInput | None = None,
    universe_symbols: Sequence[str] | None = None,
) -> pl.DataFrame:
    """Build weekly ordinary, Mansfield-market and Mansfield-sector features.

    Mansfield RS is ``(price / benchmark) / 52-week mean(price / benchmark) -
    1`` expressed in percent.  It needs 52 weekly observations; before that
    point it is null.  A missing or non-positive benchmark never becomes zero.
    ``sector_by_symbol`` maps each candidate to its sector benchmark symbol.
    """

    all_daily = price_features(bars, as_of=as_of)
    if all_daily.is_empty():
        return all_daily
    normalized_universe = (
        sorted({str(symbol).strip().upper() for symbol in universe_symbols})
        if universe_symbols is not None
        else None
    )
    daily_rs = ordinary_relative_strength(
        all_daily,
        as_of=as_of,
        universe_symbols=normalized_universe,
    )
    candidate_daily = (
        all_daily.filter(pl.col("symbol").is_in(normalized_universe))
        if normalized_universe is not None
        else all_daily
    )
    weekly = weekly_bars_frame(candidate_daily, as_of=as_of)
    # At a weekly grain, use the last daily cross-sectional rank in that week.
    daily_rs = daily_rs.with_columns(
        (pl.col("date") - pl.duration(days=pl.col("date").dt.weekday() - 1)).alias("week_start")
    )
    ordinary_weekly = (
        daily_rs.sort("date")
        .group_by(["symbol", "week_start"], maintain_order=True)
        .agg(pl.col("date").last(), pl.col("return_3m").last(), pl.col("ordinary_rs_3m").last())
        .rename({"date": "_daily_endpoint"})
    )
    weekly = weekly.join(ordinary_weekly, on=["symbol", "week_start"], how="left")
    market_frame = (
        weekly_bars_frame(market_bars, as_of=as_of)
        if market_bars is not None
        else weekly_bars_frame(all_daily, as_of=as_of)
    )
    market = _mansfield(weekly, market_frame, market_symbol, "mansfield_market")
    result = weekly.join(market, on=["symbol", "date"], how="left")

    if sector_bars is not None:
        sector_frame = weekly_bars_frame(sector_bars, as_of=as_of)
    else:
        sector_frame = weekly_bars_frame(all_daily, as_of=as_of)
    sector_rows: list[pl.DataFrame] = []
    for symbol in result.get_column("symbol").unique().to_list():
        benchmark_symbol = _sector_symbol_for(str(symbol), sector_by_symbol, sector_symbol)
        if benchmark_symbol is None:
            sector_rows.append(
                result.filter(pl.col("symbol") == symbol)
                .select("symbol", "date")
                .with_columns(pl.lit(None, dtype=pl.Float64).alias("mansfield_sector"))
            )
        else:
            candidate = result.filter(pl.col("symbol") == symbol)
            sector_rows.append(
                _mansfield(candidate, sector_frame, benchmark_symbol, "mansfield_sector")
            )
    sectors = pl.concat(sector_rows, how="vertical") if sector_rows else pl.DataFrame()
    result = result.join(sectors, on=["symbol", "date"], how="left")
    result = rolling_four_week_slopes(result)
    return result.sort(["symbol", "date"])


def rolling_four_week_slopes(
    frame: pl.DataFrame,
    *,
    value_columns: Sequence[str] = ("ordinary_rs_3m", "mansfield_market", "mansfield_sector"),
    window_weeks: int = 4,
) -> pl.DataFrame:
    """Add linear-regression slopes over the trailing weekly observations."""

    if window_weeks < 2:
        raise ValueError("window_weeks must be at least 2")
    if frame.is_empty():
        return frame
    if "symbol" not in frame.columns:
        raise ValueError("relative-strength frame requires a symbol column")
    ordered = frame.sort(["symbol", "date"])
    n = float(window_weeks)
    # For equally spaced x=0..n-1, derive sums as rolling shifts.  This avoids
    # Python UDFs and is deterministic across Polars versions.
    x_sum = n * (n - 1) / 2.0
    x_sq_sum = n * (n - 1) * (2.0 * n - 1.0) / 6.0
    denominator = n * x_sq_sum - x_sum * x_sum
    for column in value_columns:
        if column not in ordered.columns:
            continue
        y = pl.col(column)
        y_sum = y.rolling_sum(window_size=window_weeks, min_samples=window_weeks).over("symbol")
        # sum(x*y), with x=0 oldest ... n-1 newest.  shift(k) is k rows back,
        # therefore its coefficient is n-1-k.
        xy = pl.lit(0.0)
        for k in range(window_weeks):
            xy = xy + y.shift(k).over("symbol") * float(window_weeks - 1 - k)
        slope = (n * xy - x_sum * y_sum) / denominator
        output = f"{column}_slope_4w" if window_weeks == 4 else f"{column}_slope_{window_weeks}w"
        ordered = ordered.with_columns(_clean(slope).alias(output))
    if "ordinary_rs_3m_slope_4w" in ordered.columns:
        ordered = ordered.with_columns(
            (pl.col("ordinary_rs_3m_slope_4w") > 0).alias("ordinary_rs_improving_4w")
        )
    return ordered


# Friendly aliases for pipeline callers.
build_relative_strength_features = relative_strength_features
compute_rs_features = relative_strength_features
build_ordinary_rs = ordinary_relative_strength
build_rs_features = relative_strength_features

__all__ = [
    "ordinary_relative_strength",
    "relative_strength_features",
    "rolling_four_week_slopes",
    "build_relative_strength_features",
    "compute_rs_features",
    "build_ordinary_rs",
    "build_rs_features",
]
