"""Small, deterministic transforms used by the bounded Turn card.

The functions in this module intentionally operate on scalar facts and simple
records.  They do not fetch data, mutate inputs, or silently turn unavailable
facts into strong signals.  ``TechnicalScore`` is the common return type;
``score`` is bounded to ``0..100`` and is ``None`` when a required component is
not available.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from math import isfinite
from typing import Any


@dataclass(frozen=True, slots=True)
class TechnicalScore:
    """A bounded score plus auditable availability and quality information."""

    score: float | None
    reason_codes: tuple[str, ...] = ()
    confidence: str = "HIGH_CONFIDENCE"

    @property
    def value(self) -> float | None:
        """Friendly scalar alias for callers that use ``value`` terminology."""

        return self.score

    @property
    def available(self) -> bool:
        return self.score is not None

    @property
    def unavailable(self) -> bool:
        return self.score is None


@dataclass(frozen=True, slots=True)
class Observation:
    """An observation and the instant at which it became known."""

    timestamp: date | datetime
    value: float
    known_at: date | datetime | None = None

    @property
    def date(self) -> date:
        return self.timestamp.date() if isinstance(self.timestamp, datetime) else self.timestamp


@dataclass(frozen=True, slots=True)
class CostBasisObservation:
    """One price/cost-basis observation used to identify a reclaim cross."""

    timestamp: date | datetime
    price: float
    cost_basis: float
    known_at: date | datetime | None = None


PercentileResult = TechnicalScore
BaseStructureResult = TechnicalScore
TechnicalObservation = Observation


def _clamp(value: float) -> float:
    return min(100.0, max(0.0, float(value)))


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _instant(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        stamp = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return stamp.astimezone(UTC)
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def _before(value: date | datetime, cutoff: date | datetime) -> bool:
    """Compare date-grain observations strictly before a date-grain cutoff."""

    if isinstance(cutoff, date) and not isinstance(cutoff, datetime):
        observed = value.date() if isinstance(value, datetime) else value
        return observed < cutoff
    return _instant(value) < _instant(cutoff)


def _after(value: date | datetime, cutoff: date | datetime) -> bool:
    if isinstance(cutoff, date) and not isinstance(cutoff, datetime):
        observed = value.date() if isinstance(value, datetime) else value
        return observed > cutoff
    return _instant(value) > _instant(cutoff)


def _observation(item: Observation | Mapping[str, Any]) -> Observation:
    if isinstance(item, Observation):
        return item
    timestamp = item.get("timestamp", item.get("date", item.get("observed_at")))
    if timestamp is None:
        raise ValueError("observation requires timestamp")
    value = item.get("value", item.get("score"))
    number = _number(value)
    if number is None:
        raise ValueError("observation value must be finite")
    known_at = item.get("known_at", item.get("knowledge_at", item.get("available_at")))
    return Observation(timestamp, number, known_at)


def _missing(reason: str = "INSUFFICIENT_COMPONENT_DATA") -> TechnicalScore:
    return TechnicalScore(None, (reason,), "LOW_CONFIDENCE")


def _mapping_value(
    facts: Mapping[str, Any] | None,
    value: Any,
    names: Sequence[str],
) -> Any:
    if value is not None:
        return value
    if facts is None:
        return None
    for name in names:
        if name in facts:
            return facts[name]
    return None


def midrank_percentile(
    value: Any,
    observations: Sequence[Observation | Mapping[str, Any]],
    *,
    as_of: date | datetime,
    grain: str = "weekly",
    min_history: int | None = None,
    history_size: int | None = None,
) -> TechnicalScore:
    """Rank ``value`` against strictly prior, point-in-time observations.

    ``known_at`` must be strictly earlier than ``as_of``.  A row dated after
    the cutoff is an input error; a row exactly on a date cutoff is the current
    row and is not history.  The default windows are 26/104 for weekly and
    60/252 for daily observations.
    """

    key = grain.strip().lower()
    if key in {"weekly", "week", "w"}:
        default_min, default_size = 26, 104
    elif key in {"daily", "day", "d"}:
        default_min, default_size = 60, 252
    else:
        raise ValueError("grain must be weekly or daily")
    required = default_min if min_history is None else int(min_history)
    limit = default_size if history_size is None else int(history_size)
    if required <= 0 or limit <= 0:
        raise ValueError("history sizes must be positive")
    current = _number(value)
    if current is None:
        return _missing()

    parsed: list[Observation] = []
    for raw in observations:
        row = _observation(raw)
        if _after(row.timestamp, as_of):
            raise ValueError("observation timestamp after as_of")
        # Missing knowledge metadata is acceptable for synthetic observations;
        # their event timestamp is the conservative knowledge timestamp.
        known = row.known_at if row.known_at is not None else row.timestamp
        if _after(known, as_of):
            raise ValueError("observation known_at after as_of")
        if _before(row.timestamp, as_of) and _before(known, as_of):
            parsed.append(row)
    ordered = sorted(parsed, key=lambda row: _instant(row.timestamp))
    history = [row.value for row in ordered[-limit:]]
    if len(history) < required:
        return TechnicalScore(50.0, ("LOW_CONFIDENCE_HISTORY",), "LOW_CONFIDENCE")
    lower = sum(item < current for item in history)
    equal = sum(item == current for item in history)
    rank = (lower + equal / 2.0) / len(history) * 100.0
    return TechnicalScore(_clamp(rank))


point_in_time_midrank_percentile = midrank_percentile
rank_percentile = midrank_percentile


def base_structure_score(
    facts: Mapping[str, Any] | None = None,
    *,
    no_new_52_week_low_20_sessions: Any = None,
    volatility_contraction: Any = None,
    volume_dryup: Any = None,
    ma20_flattening: Any = None,
    close_above_ma20: Any = None,
) -> TechnicalScore:
    """Score the five locked base-structure rules at 25/20/20/20/15."""

    if facts is not None:
        if volatility_contraction is None:
            current = _number(facts.get("volatility_20d"))
            prior = _number(facts.get("prior_volatility_20d"))
            if current is not None and prior is not None and prior >= 0:
                volatility_contraction = current <= 0.80 * prior
        if volume_dryup is None:
            current = _number(facts.get("median_volume_20d"))
            prior = _number(facts.get("prior_median_volume_20d"))
            if current is not None and prior is not None and prior >= 0:
                volume_dryup = current <= 0.80 * prior
        if ma20_flattening is None:
            slope = _number(facts.get("ma20_slope_5d"))
            close = _number(facts.get("close"))
            if slope is not None and close is not None and close > 0:
                ma20_flattening = abs(slope) <= 0.001 * close
        if close_above_ma20 is None:
            close = _number(facts.get("close"))
            ma20 = _number(facts.get("ma20"))
            if close is not None and ma20 is not None:
                close_above_ma20 = close >= ma20

    rules = (
        ("no_new_52_week_low_20_sessions", no_new_52_week_low_20_sessions, 25.0,
         ("no_new_52_week_low_20_sessions", "no_new_52w_low_20d", "no_new_52_week_low")),
        ("volatility_contraction", volatility_contraction, 20.0, ("volatility_contraction",)),
        ("volume_dryup", volume_dryup, 20.0, ("volume_dryup", "volume_dry_up", "volume_dry-up")),
        ("ma20_flattening", ma20_flattening, 20.0, ("ma20_flattening", "ma20_flat")),
        ("close_above_ma20", close_above_ma20, 15.0, ("close_above_ma20",)),
    )
    values: list[tuple[float, bool]] = []
    for _, supplied, weight, names in rules:
        raw = _mapping_value(facts, supplied, names)
        if not isinstance(raw, bool):
            return _missing()
        values.append((weight, raw))
    return TechnicalScore(_clamp(sum(weight for weight, present in values if present)))


compute_base_structure = base_structure_score
base_structure = base_structure_score


def ordinary_rs_turn_score(
    current_percentile: Any = None,
    slope_percentile: Any = None,
    *,
    facts: Mapping[str, Any] | None = None,
) -> TechnicalScore:
    """Combine ordinary-RS level and slope percentiles at 30/70."""

    current = _number(
        _mapping_value(
            facts,
            current_percentile,
            ("current_percentile", "ordinary_rs_percentile", "ordinary_rs_current_percentile"),
        )
    )
    slope = _number(_mapping_value(
        facts, slope_percentile, ("slope_percentile", "ordinary_rs_slope_percentile")
    ))
    if current is None or slope is None:
        return _missing()
    return TechnicalScore(_clamp(0.30 * _clamp(current) + 0.70 * _clamp(slope)))


ordinary_rs_turn = ordinary_rs_turn_score
ordinary_relative_strength_turn = ordinary_rs_turn_score


def mansfield_transform(value: Any) -> float | None:
    """Map a Mansfield value of -10/0/+10 to 0/50/100, with clamping."""

    number = _number(value)
    return None if number is None else _clamp((number + 10.0) * 5.0)


def mansfield_turn_score(
    level: Any = None,
    slope_percentile: Any = None,
    *,
    mansfield_level: Any = None,
    mansfield_slope_percentile: Any = None,
    facts: Mapping[str, Any] | None = None,
) -> TechnicalScore:
    """Combine transformed Mansfield level and slope at 30/70."""

    level = _mapping_value(facts, mansfield_level if mansfield_level is not None else level,
                           ("level", "mansfield_level", "mansfield"))
    slope = _mapping_value(
        facts,
        (
            mansfield_slope_percentile
            if mansfield_slope_percentile is not None
            else slope_percentile
        ),
        ("slope_percentile", "mansfield_slope_percentile"),
    )
    level_score = mansfield_transform(level)
    slope_score = _number(slope)
    if level_score is None or slope_score is None:
        return _missing()
    return TechnicalScore(_clamp(0.30 * level_score + 0.70 * _clamp(slope_score)))


mansfield_score = mansfield_turn_score


def signed_volume_ratio_score(ratio: Any) -> float | None:
    """Map a 20-session signed-volume ratio from -0.10..+0.30 to 0..100."""

    number = _number(ratio)
    return None if number is None else _clamp((number + 0.10) / 0.40 * 100.0)


def signed_volume_ratio(
    adjusted_closes: Sequence[Any],
    volumes: Sequence[Any],
    *,
    sessions: int = 20,
) -> float | None:
    """Return the signed-volume ratio for the last ``sessions`` returns.

    A 20-session ratio needs 21 closes so the first included session has a
    prior close. Missing or non-positive volume makes the component
    unavailable instead of changing the denominator silently.
    """

    if sessions <= 0:
        raise ValueError("sessions must be positive")
    if len(adjusted_closes) != len(volumes):
        raise ValueError("adjusted_closes and volumes must have equal length")
    if len(adjusted_closes) < sessions + 1:
        return None
    closes = [_number(value) for value in adjusted_closes[-(sessions + 1) :]]
    amounts = [_number(value) for value in volumes[-(sessions + 1) :]]
    if any(value is None or value <= 0 for value in closes):
        return None
    selected_volumes = amounts[1:]
    if any(value is None or value <= 0 for value in selected_volumes):
        return None
    numerator = 0.0
    denominator = 0.0
    for previous, current, volume in zip(
        closes,
        closes[1:],
        selected_volumes,
        strict=False,
    ):
        assert previous is not None and current is not None and volume is not None
        direction = 1.0 if current > previous else (-1.0 if current < previous else 0.0)
        numerator += volume * direction
        denominator += volume
    return numerator / denominator if denominator > 0 else None


def volume_accumulation_score(
    ratio: Any = None,
    prior_percentile: Any = None,
    *,
    facts: Mapping[str, Any] | None = None,
) -> TechnicalScore:
    """Combine the fixed 20D ratio transform and prior percentile at 50/50."""

    ratio = _mapping_value(
        facts, ratio, ("signed_volume_ratio_20d", "signed_volume_ratio", "ratio")
    )
    prior_percentile = _mapping_value(
        facts, prior_percentile, ("prior_percentile", "signed_volume_prior_percentile")
    )
    ratio_score = signed_volume_ratio_score(ratio)
    prior = _number(prior_percentile)
    if ratio_score is None or prior is None:
        return _missing()
    return TechnicalScore(_clamp(0.50 * ratio_score + 0.50 * _clamp(prior)))


signed_volume_score = volume_accumulation_score
volume_score = volume_accumulation_score


def _cost_observation(item: CostBasisObservation | Mapping[str, Any]) -> CostBasisObservation:
    if isinstance(item, CostBasisObservation):
        return item
    timestamp = item.get("timestamp", item.get("date", item.get("observed_at")))
    if timestamp is None:
        raise ValueError("cost-basis observation requires timestamp")
    price = _number(item.get("price", item.get("close")))
    basis = _number(item.get("cost_basis", item.get("cost_basis_90d", item.get("basis"))))
    if price is None or basis is None:
        raise ValueError("cost-basis observation requires finite price and basis")
    known_at = item.get("known_at", item.get("knowledge_at", item.get("available_at")))
    return CostBasisObservation(timestamp, price, basis, known_at)


def cost_basis_reclaim_score(
    current_price: Any = None,
    cost_basis_90d: Any = None,
    *,
    history: Sequence[CostBasisObservation | Mapping[str, Any]] = (),
    as_of: date | datetime | None = None,
    sessions: int = 10,
) -> TechnicalScore:
    """Score a 90D basis reclaim: fresh cross 100, above 50, below 0."""

    if sessions <= 0:
        raise ValueError("sessions must be positive")
    price = _number(current_price)
    basis = _number(cost_basis_90d)
    if price is None or basis is None:
        return _missing()
    rows = [_cost_observation(item) for item in history]
    if as_of is not None:
        for row in rows:
            if _after(row.timestamp, as_of):
                raise ValueError("cost-basis observation timestamp after as_of")
    rows.sort(key=lambda row: _instant(row.timestamp))
    # Include the current endpoint once.  Callers may already include it in
    # history, in which case replacing the endpoint avoids a duplicate session.
    if as_of is not None:
        rows = [row for row in rows if not (_instant(row.timestamp) == _instant(as_of))]
        rows.append(CostBasisObservation(as_of, price, basis))
    elif not rows or rows[-1].price != price or rows[-1].cost_basis != basis:
        rows.append(CostBasisObservation(date.min, price, basis))
    recent = rows[-(sessions + 1):]
    fresh_cross = any(
        previous.price < previous.cost_basis and current.price >= current.cost_basis
        for previous, current in zip(recent, recent[1:], strict=False)
    )
    if price < basis:
        return TechnicalScore(0.0, ("BELOW_COST_BASIS",))
    if fresh_cross:
        return TechnicalScore(100.0, ("FRESH_COST_BASIS_RECLAIM",))
    return TechnicalScore(50.0, ("ABOVE_COST_BASIS_NO_FRESH_CROSS",))


cost_basis_reclaim_90d = cost_basis_reclaim_score
cost_basis_reclaim = cost_basis_reclaim_score


__all__ = [
    "TechnicalScore", "Observation", "TechnicalObservation", "CostBasisObservation",
    "PercentileResult", "BaseStructureResult", "midrank_percentile",
    "point_in_time_midrank_percentile", "rank_percentile", "base_structure_score",
    "compute_base_structure", "base_structure", "ordinary_rs_turn_score",
    "ordinary_rs_turn", "ordinary_relative_strength_turn", "mansfield_transform",
    "mansfield_turn_score", "mansfield_score", "signed_volume_ratio", "signed_volume_ratio_score",
    "volume_accumulation_score", "signed_volume_score", "volume_score",
    "cost_basis_reclaim_score", "cost_basis_reclaim_90d", "cost_basis_reclaim",
]
