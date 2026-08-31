"""Point-in-time company-level component aggregation for scoring v1.

This module deliberately stops at normalized 0--100 components.  Weighting
the model remains the responsibility of :class:`ScoreEngine`, which keeps the
raw-to-component contract independently testable and auditable.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from insider_turning_engine.domain.time import us_equity_session_close


@dataclass(frozen=True, slots=True)
class CompanyInsiderComponents:
    conviction: float | None
    cluster: float | None
    opportunistic: float | None
    net_buying_absence_sales: float | None
    quality_flags: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return all(
            value is not None
            for value in (
                self.conviction,
                self.cluster,
                self.opportunistic,
                self.net_buying_absence_sales,
            )
        )

    def as_mapping(self) -> dict[str, float | None]:
        return {
            "conviction": self.conviction,
            "cluster": self.cluster,
            "opportunistic": self.opportunistic,
            "net_buying_absence_sales": self.net_buying_absence_sales,
        }


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _instant(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return None


def _get(row: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return default


def _quantile(values: Sequence[float], probability: float) -> float:
    """Return the deterministic type-7 linear quantile used by the v1 lock."""

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def prior_dollar_winsor_cap(
    values: Iterable[float],
    *,
    percentile: float = 0.995,
    minimum_observations: int = 200,
) -> tuple[float | None, tuple[str, ...]]:
    """Return a cap derived only from prior eligible universe observations."""

    if not 0.0 < percentile < 1.0:
        raise ValueError("percentile must be between zero and one")
    if minimum_observations < 1:
        raise ValueError("minimum_observations must be positive")
    history = tuple(float(value) for value in values if math.isfinite(float(value)) and value >= 0)
    if len(history) < minimum_observations:
        return None, ("LOW_CONFIDENCE_WINSOR_HISTORY",)
    return _quantile(history, percentile), ()


def aggregate_company_insider_components(
    transactions: Iterable[Mapping[str, Any]],
    *,
    as_of: date | datetime,
    prior_universe_dollar_values: Iterable[float] = (),
    winsor_minimum_observations: int = 200,
) -> CompanyInsiderComponents:
    """Aggregate trailing company components from qualified P/S transactions.

    ``knowledge_at`` is the information boundary.  A row later than ``as_of``
    is rejected rather than silently filtered, making accidental lookahead a
    test-visible error.  Conviction and opportunistic scores use qualified
    purchases only; net buying includes qualified purchases and sales.
    """

    cutoff = as_of if isinstance(as_of, datetime) else us_equity_session_close(as_of)
    if cutoff.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    cutoff = cutoff.astimezone(UTC)
    cutoff_date = cutoff.date()
    lower_90 = cutoff_date - timedelta(days=90)
    lower_30 = cutoff_date - timedelta(days=30)
    selected: list[Mapping[str, Any]] = []
    for row in transactions:
        known = _instant(_get(row, "knowledge_at", "accepted_at", "available_at"))
        if known is not None and known.astimezone(UTC) > cutoff:
            raise ValueError("transaction knowledge_at later than as_of")
        when = _date(_get(row, "transaction_date", "date"))
        if when is None or when > cutoff_date:
            if when is not None and when > cutoff_date:
                raise ValueError("transaction_date later than as_of")
            continue
        table = str(_get(row, "table_type", default="NON_DERIVATIVE")).upper()
        code = str(_get(row, "code", "transaction_code", default="")).upper()
        active = str(_get(row, "lifecycle_status", "status", default="ACTIVE")).upper()
        if table != "NON_DERIVATIVE" or code not in {"P", "S"} or active != "ACTIVE":
            continue
        if when >= lower_90:
            selected.append(row)

    cap, flags = prior_dollar_winsor_cap(
        prior_universe_dollar_values,
        minimum_observations=winsor_minimum_observations,
    )

    def dollars(row: Mapping[str, Any]) -> float | None:
        value = _number(_get(row, "value_usd", "dollar_value", "value"))
        if value is None:
            shares = _number(_get(row, "shares"))
            price = _number(_get(row, "price_per_share", "price"))
            value = shares * price if shares is not None and price is not None else None
        if value is None or value < 0:
            return None
        return min(value, cap) if cap is not None else value

    buys = [row for row in selected if str(_get(row, "code", default="")).upper() == "P"]
    sales = [row for row in selected if str(_get(row, "code", default="")).upper() == "S"]

    def weighted_score(name: str) -> float | None:
        pairs = [
            (score, weight)
            for row in buys
            if (score := _number(_get(row, name))) is not None
            and (weight := dollars(row)) is not None
            and weight > 0
        ]
        denominator = sum(weight for _, weight in pairs)
        if denominator <= 0:
            return None
        return round(sum(score * weight for score, weight in pairs) / denominator, 6)

    clusters = [
        score
        for row in buys
        if (_date(_get(row, "transaction_date", "date")) or date.min) >= lower_30
        and (score := _number(_get(row, "cluster_score"))) is not None
    ]
    buy_dollars = sum(value for row in buys if (value := dollars(row)) is not None)
    sale_dollars = sum(value for row in sales if (value := dollars(row)) is not None)
    turnover = buy_dollars + sale_dollars
    result = CompanyInsiderComponents(
        conviction=weighted_score("conviction_score"),
        cluster=max(clusters) if clusters else None,
        opportunistic=weighted_score("opportunistic_score"),
        net_buying_absence_sales=(
            round(100.0 * buy_dollars / turnover, 6) if turnover > 0 else None
        ),
        quality_flags=tuple(sorted(flags)),
    )
    if not result.available:
        return CompanyInsiderComponents(
            result.conviction,
            result.cluster,
            result.opportunistic,
            result.net_buying_absence_sales,
            tuple(sorted({*result.quality_flags, "INSUFFICIENT_COMPONENT_DATA"})),
        )
    return result


def deterministic_reason_codes(
    important: Iterable[str],
    components: Mapping[str, float | None],
    weights: Mapping[str, float],
    *,
    limit: int = 3,
) -> tuple[str, ...]:
    """Put rule flags first, then the strongest weighted contributions."""

    first = tuple(dict.fromkeys(str(code).upper() for code in important if code))
    ranked = sorted(
        (
            (float(value) * float(weights.get(name, 0.0)), name)
            for name, value in components.items()
            if value is not None and math.isfinite(float(value)) and weights.get(name, 0.0) > 0
        ),
        key=lambda item: (-item[0], item[1]),
    )
    contributions = tuple(f"{name.upper()}_CONTRIBUTION" for _, name in ranked[:limit])
    return tuple(dict.fromkeys((*first, *contributions)))


__all__ = [
    "CompanyInsiderComponents",
    "aggregate_company_insider_components",
    "deterministic_reason_codes",
    "prior_dollar_winsor_cap",
]
