"""Offline quality probes for market bars."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from decimal import Decimal

from .base import CoverageReport, DailyBar


def _rows_by_symbol(
    bars: Iterable[DailyBar] | Mapping[str, Sequence[DailyBar]],
) -> dict[str, tuple[DailyBar, ...]]:
    if isinstance(bars, Mapping):
        return {str(symbol).upper(): tuple(values) for symbol, values in bars.items()}
    grouped: defaultdict[str, list[DailyBar]] = defaultdict(list)
    for bar in bars:
        grouped[bar.symbol].append(bar)
    return {
        symbol: tuple(sorted(values, key=lambda item: item.date))
        for symbol, values in grouped.items()
    }


def probe_market_coverage(
    bars: Iterable[DailyBar] | Mapping[str, Sequence[DailyBar]],
    symbols: Sequence[str],
    *,
    as_of: date | None = None,
    stale_after_days: int = 3,
    expected_sessions: int | None = None,
    split_ratio_bounds: tuple[Decimal, Decimal] = (Decimal("0.5"), Decimal("2")),
) -> CoverageReport:
    """Assess supplied bars without fetching anything from a provider.

    A symbol is covered when at least one eligible row exists.  A large raw
    close discontinuity is quarantined unless the adjacent observations are
    explicitly adjusted, allowing a later corporate-action reconciliation.
    """

    requested = tuple(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
    grouped = _rows_by_symbol(bars)
    cutoff = as_of or date.today()
    covered: list[str] = []
    missing: list[str] = []
    stale: list[str] = []
    split: list[str] = []
    quarantined: list[str] = []
    reasons: dict[str, tuple[str, ...]] = {}
    observed_rows = 0
    for symbol in requested:
        eligible = tuple(bar for bar in grouped.get(symbol, ()) if bar.date <= cutoff)
        observed_rows += len(eligible)
        if not eligible:
            missing.append(symbol)
            reasons[symbol] = ("missing",)
            continue
        covered.append(symbol)
        latest = max(bar.date for bar in eligible)
        if (cutoff - latest).days > stale_after_days:
            stale.append(symbol)
            reasons.setdefault(symbol, tuple())
            reasons[symbol] = (*reasons[symbol], "stale")
        ordered = sorted(eligible, key=lambda bar: bar.date)
        discontinuity = False
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if previous.close <= 0:
                continue
            ratio = current.close / previous.close
            if ratio <= split_ratio_bounds[0] or ratio >= split_ratio_bounds[1]:
                if not (previous.is_adjusted and current.is_adjusted):
                    discontinuity = True
                    break
        if discontinuity:
            split.append(symbol)
            reasons.setdefault(symbol, tuple())
            reasons[symbol] = (*reasons[symbol], "split_discontinuity")
        if symbol in stale or discontinuity:
            quarantined.append(symbol)
    return CoverageReport(
        requested_symbols=requested,
        covered_symbols=tuple(covered),
        missing_symbols=tuple(missing),
        stale_symbols=tuple(stale),
        split_discontinuity_symbols=tuple(split),
        quarantined_symbols=tuple(quarantined),
        as_of=cutoff,
        expected_sessions=expected_sessions,
        observed_rows=observed_rows,
        reasons=reasons,
    )


def assess_market_quality(*args: object, **kwargs: object) -> CoverageReport:
    """Descriptive alias for :func:`probe_market_coverage`."""

    return probe_market_coverage(*args, **kwargs)  # type: ignore[arg-type]


def probe_50_symbols(
    bars: Iterable[DailyBar] | Mapping[str, Sequence[DailyBar]],
    symbols: Sequence[str],
    **kwargs: object,
) -> CoverageReport:
    """Run the offline quality probe for a universe of up to 50 symbols."""

    requested = tuple(symbol for symbol in symbols if symbol.strip())
    if len(dict.fromkeys(symbol.strip().upper() for symbol in requested)) > 50:
        raise ValueError("the 50-symbol market quality probe accepts at most 50 symbols")
    return probe_market_coverage(bars, symbols, **kwargs)  # type: ignore[arg-type]


probe_coverage = probe_market_coverage
