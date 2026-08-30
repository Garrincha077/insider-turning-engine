"""Point-in-time price-versus-insider-activity divergence features."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from math import isfinite
from typing import Any

import polars as pl

from insider_turning_engine.domain.models import CanonicalTransaction

from .conviction import _buy, _effective, _finite, _number, _rows, _validate

ACTIVITY_WINDOW_DAYS = 30
_WEIGHTS = {
    "price_weakness": 0.35,
    "insider_activity_percentile": 0.35,
    "acceleration_cluster": 0.20,
    "absence_relevant_sales": 0.10,
}


def _active(row: dict[str, Any]) -> bool:
    status = str(row.get("lifecycle_status") or "ACTIVE").upper()
    return status == "ACTIVE" or status.endswith(".ACTIVE")


def _sale(row: Mapping[str, Any]) -> bool:
    classification = str(row.get("classification") or "").upper()
    economic = str(row.get("economic_classification") or "").upper()
    return str(row.get("acquired_disposed") or "") in {"", "D"} and (
        str(row.get("code") or "") == "S"
        or classification == "OPEN_MARKET_SALE"
        or economic == "OPEN_MARKET_SALE"
    )


def _clamp(value: float) -> float:
    return min(100.0, max(0.0, value))


def _percentile(value: float, prior: Sequence[float]) -> float | None:
    values = sorted(item for item in prior if isfinite(item))
    if not values:
        return None
    lower = sum(item < value for item in values)
    equal = sum(item == value for item in values)
    return _clamp((lower + (equal + 1) / 2) / len(values) * 100.0)


def price_weakness_score(
    *, return_3m: Any = None, drawdown_from_52_week_high: Any = None
) -> float | None:
    """Map negative 3-month return/drawdown facts to a bounded 0--100 score."""

    return_ = _number(return_3m)
    drawdown = _number(drawdown_from_52_week_high)
    values: list[float] = []
    if return_ is not None:
        values.append(_clamp((-return_ / 0.20) * 100.0))
    if drawdown is not None:
        values.append(_clamp((-drawdown / 0.40) * 100.0))
    return max(values) if values else None


def _as_stamp(as_of: date | datetime) -> tuple[date, datetime]:
    if isinstance(as_of, datetime):
        stamp = as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=UTC)
        return stamp.date(), stamp.astimezone(UTC)
    return as_of, datetime.combine(as_of, time.max, tzinfo=UTC)


def _context_records(context: Any, *, as_of: date | datetime) -> list[dict[str, Any]]:
    """Normalize precomputed price/cluster facts and reject future knowledge."""

    cutoff, stamp = _as_stamp(as_of)
    if context is None:
        return []
    if isinstance(context, pl.DataFrame):
        source = context.to_dicts()
    elif isinstance(context, Mapping):
        source = []
        for issuer, value in context.items():
            if isinstance(value, Mapping):
                source.append({"issuer_cik": issuer, **value})
    else:
        source = [dict(value) for value in context if isinstance(value, Mapping)]
    records: list[dict[str, Any]] = []
    for item in source:
        issuer = item.get("issuer_cik", item.get("issuer", item.get("symbol", item.get("ticker"))))
        if issuer is None:
            continue
        event = item.get("date", item.get("as_of", cutoff))
        if isinstance(event, datetime):
            event = event.date()
        if not isinstance(event, date):
            event = date.fromisoformat(str(event)[:10])
        if event > cutoff:
            raise ValueError("context row dated after as_of")
        for name in ("available_at", "accepted_at", "knowledge_at"):
            raw = item.get(name)
            if raw is None:
                continue
            value = raw
            if not isinstance(value, datetime):
                value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if value.tzinfo is None:
                raise ValueError(f"context {name} must be timezone-aware")
            if value.astimezone(UTC) > stamp:
                raise ValueError(f"context {name} later than as_of")
        records.append({"issuer_cik": str(issuer), "date": event, **item})
    return records


def _latest_context(records: Sequence[dict[str, Any]], issuer: str) -> dict[str, Any]:
    matching = [item for item in records if str(item["issuer_cik"]) == issuer]
    return max(matching, key=lambda item: item["date"]) if matching else {}


def _dollar(row: Mapping[str, Any]) -> float:
    value = row.get("value_usd")
    if value is not None and _finite(value):
        return max(0.0, float(value))
    shares, price = row.get("shares"), row.get("price_per_share")
    if shares is not None and price is not None and _finite(shares) and _finite(price):
        return max(0.0, float(shares) * float(price))
    return 0.0


def _empty() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "issuer_cik": pl.String,
            "as_of": pl.Date,
            "divergence_score": pl.Float64,
            "reason_codes": pl.List(pl.String),
            "confidence": pl.String,
        }
    )


def divergence_features(
    transactions: pl.DataFrame | Sequence[CanonicalTransaction] | Iterable[CanonicalTransaction],
    *,
    as_of: date | datetime,
    price_context: Any = None,
    cluster_context: Any = None,
    activity_window_days: int = ACTIVITY_WINDOW_DAYS,
) -> pl.DataFrame:
    """Build issuer-level divergence rows using the frozen v1 factor weights.

    The 35/35/20/10 weighted score is emitted only when every required factor
    is available.  Current activity is compared only with complete windows
    ending before the current window starts; current or future activity never
    enters its own percentile.
    """

    if activity_window_days <= 0:
        raise ValueError("activity_window_days must be positive")
    rows = _rows(transactions)
    cutoff = _validate(rows, as_of)
    rows = [row for row in rows if _effective(row, as_of)]
    price_rows = _context_records(price_context, as_of=as_of)
    cluster_rows = _context_records(cluster_context, as_of=as_of)
    active = [row for row in rows if _active(row)]
    issuers = sorted({str(row["issuer_cik"]) for row in active if row["issuer_cik"]})
    results: list[dict[str, Any]] = []
    start = cutoff - timedelta(days=activity_window_days - 1)
    for issuer in issuers:
        issuer_rows = [row for row in active if row["issuer_cik"] == issuer]
        current = [row for row in issuer_rows if start <= row["transaction_date"] <= cutoff]
        purchases = [row for row in current if _buy(row)]
        purchase_dollars = sum(_dollar(row) for row in purchases)
        relevant_sales = [row for row in current if _sale(row) and _dollar(row) > 0]

        history: list[float] = []
        cursor_end = start - timedelta(days=1)
        # Calendar windows are complete and strictly prior.  The bound avoids
        # unbounded work on malformed, very old input streams.
        for _ in range(120):
            cursor_start = cursor_end - timedelta(days=activity_window_days - 1)
            period = [
                row
                for row in issuer_rows
                if cursor_start <= row["transaction_date"] <= cursor_end and _buy(row)
            ]
            history.append(sum(_dollar(row) for row in period))
            if not any(row["transaction_date"] < cursor_start for row in issuer_rows):
                break
            cursor_end = cursor_start - timedelta(days=1)
        activity_percentile = _percentile(purchase_dollars, history)
        prior_activity = history[0] if history else None
        if prior_activity is None:
            acceleration = None
        elif prior_activity <= 0:
            acceleration = 100.0 if purchase_dollars > 0 else 0.0
        else:
            acceleration = _clamp((purchase_dollars / prior_activity - 1.0) * 100.0)

        price = _latest_context(price_rows, issuer)
        explicit_price = _number(price.get("price_weakness_score"))
        weakness = (
            explicit_price
            if explicit_price is not None
            else price_weakness_score(
                return_3m=price.get("return_3m"),
                drawdown_from_52_week_high=price.get(
                    "drawdown_from_52_week_high", price.get("drawdown")
                ),
            )
        )
        cluster = _latest_context(cluster_rows, issuer)
        cluster_score = _number(cluster.get("cluster_score", cluster.get("score")))
        acceleration_cluster = (
            max(value for value in (acceleration, cluster_score) if value is not None)
            if acceleration is not None or cluster_score is not None
            else None
        )
        no_sales = 100.0 if not relevant_sales else 0.0
        components = {
            "price_weakness": weakness,
            "insider_activity_percentile": activity_percentile,
            "acceleration_cluster": acceleration_cluster,
            "absence_relevant_sales": no_sales,
        }
        missing = [name for name, value in components.items() if value is None]
        score = None
        if not missing:
            complete = {
                name: float(value) for name, value in components.items() if value is not None
            }
            score = sum(complete[name] * weight for name, weight in _WEIGHTS.items())
        reasons = ["NO_RELEVANT_SALES" if not relevant_sales else "RELEVANT_SALES_PRESENT"]
        if activity_percentile is None:
            reasons.append("NO_STRICT_PRIOR_ACTIVITY_HISTORY")
        if cluster_score is not None:
            reasons.append("CLUSTER_CONTEXT")
        if acceleration is not None and acceleration > 0:
            reasons.append("BUYING_ACCELERATION")
        if weakness is not None and weakness >= 50:
            reasons.append("PRICE_WEAKNESS")
        reasons.extend(f"MISSING_{name.upper()}" for name in missing)
        results.append(
            {
                "issuer_cik": issuer,
                "as_of": cutoff,
                "activity_window_days": activity_window_days,
                "purchase_dollars": purchase_dollars,
                "relevant_sale_count": len(relevant_sales),
                "price_weakness": weakness,
                "insider_activity_percentile": activity_percentile,
                "buying_acceleration": acceleration,
                "cluster_score": cluster_score,
                "acceleration_cluster": acceleration_cluster,
                "absence_relevant_sales": no_sales,
                "divergence_score": score,
                "reason_codes": reasons,
                "confidence": "HIGH" if score is not None else "LOW",
            }
        )
    return pl.DataFrame(results).sort("issuer_cik") if results else _empty()


compute_divergence = divergence_features
divergence_score = divergence_features
build_divergence_features = divergence_features

__all__ = [
    "ACTIVITY_WINDOW_DAYS",
    "price_weakness_score",
    "divergence_features",
    "compute_divergence",
    "divergence_score",
    "build_divergence_features",
]
