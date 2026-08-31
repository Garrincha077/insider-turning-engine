"""Point-in-time insider conviction primitives.

This module intentionally has no persistence or clustering logic.  It accepts
canonical transactions (or a flat Polars frame) and optional, already-derived
context.  Every returned row is explainable through ``reason_codes`` and has a
``confidence`` value that is reduced when an input fact is unavailable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from math import isfinite, log10
from typing import Any

import polars as pl

from insider_turning_engine.domain.models import (
    CanonicalTransaction,
    EconomicClassification,
    TransactionClassification,
)
from insider_turning_engine.domain.time import us_equity_session_close

_ROLE_POINTS: dict[str, float] = {
    "CEO": 100.0,
    "CFO": 95.0,
    "CHAIRMAN": 90.0,
    "OFFICER": 75.0,
    "DIRECTOR": 65.0,
    "TEN_PERCENT_OWNER": 55.0,
    "OTHER": 35.0,
}
_PENALTIES = {"10B5_1": 15.0, "ROUTINE": 10.0, "SYMBOLIC": 10.0}


def _cutoff(as_of: date | datetime | None) -> tuple[date, datetime]:
    if as_of is None:
        raise ValueError("as_of is required for point-in-time conviction")
    if isinstance(as_of, datetime):
        stamp = as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)
        stamp = stamp.astimezone(UTC)
        return stamp.date(), stamp
    return as_of, us_equity_session_close(as_of)


def _finite(value: Any) -> bool:
    if value is None:
        return False
    try:
        return isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _number(value: Any) -> float | None:
    return float(value) if _finite(value) else None


def _date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _stamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        stamp = value
    else:
        try:
            stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC)


def _get(value: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            candidate = value[name]
        else:
            candidate = getattr(value, name, None)
        if candidate is not None:
            return candidate
    return default


def _nested(value: Any, parent: str, *names: str, default: Any = None) -> Any:
    direct = _get(value, *names, default=None)
    if direct is not None:
        return direct
    child = _get(value, parent, default=None)
    return _get(child, *names, default=default)


def _role(value: Any) -> str:
    direct_role = _get(value, "role", default=None)
    if direct_role is not None:
        label = getattr(direct_role, "value", str(direct_role)).upper()
        if label in _ROLE_POINTS:
            return label
    roles = _nested(value, "relationship", "normalized_roles", default=None)
    if roles:
        for candidate in roles:
            label = getattr(candidate, "value", str(candidate)).upper()
            if label in _ROLE_POINTS:
                return label
    title = str(_nested(value, "relationship", "officer_title", default="") or "").upper()
    if "CHIEF EXECUTIVE" in title or "CEO" in title:
        return "CEO"
    if "CHIEF FINANCIAL" in title or "CFO" in title:
        return "CFO"
    if "CHAIR" in title:
        return "CHAIRMAN"
    relationship = _get(value, "relationship", default=value)
    if _get(relationship, "is_officer", default=False):
        return "OFFICER"
    if _get(relationship, "is_director", default=False):
        return "DIRECTOR"
    if _get(relationship, "is_ten_percent_owner", default=False):
        return "TEN_PERCENT_OWNER"
    return "OTHER"


def role_factor(role: Any) -> float:
    """Return the deterministic 0--100 role factor for an owner/relationship."""

    label = getattr(role, "value", str(role)).upper()
    return _ROLE_POINTS.get(label, _ROLE_POINTS["OTHER"])


def _record(value: Any, row_id: int) -> dict[str, Any]:
    issuer = _nested(value, "issuer", "cik", "issuer_cik", "symbol", "ticker", default=None)
    owner = _nested(value, "reporting_owner", "cik", "owner_cik", "owner", default=None)
    tx = _get(value, "transaction", default=value)
    timestamps = _get(value, "timestamps", default=value)
    classification = _get(tx, "classification", default=None)
    economic = _get(tx, "economic_classification", "economicClassification", default=None)
    code = str(_get(tx, "code", "transaction_code", default="") or "").upper()
    acquired = str(
        _get(tx, "acquired_disposed", "acquired_disposed_code", default="") or ""
    ).upper()
    table = _get(_get(value, "security", default=value), "table_type", default=None)
    table = getattr(table, "value", table)
    value_usd = _number(_get(tx, "value", default=None))
    shares = _number(_get(tx, "shares", default=None))
    price = _number(_get(tx, "price_per_share", "transaction_price_per_share", default=None))
    for name, raw in (
        ("value", _get(tx, "value", default=None)),
        ("shares", _get(tx, "shares", default=None)),
        ("price_per_share", _get(tx, "price_per_share", default=None)),
    ):
        if raw is not None and not _finite(raw):
            raise ValueError(f"non-finite transaction {name}")
    if value_usd is None and shares is not None and price is not None:
        value_usd = shares * price
    rule = _get(tx, "rule_10b51", "rule10b51", "ten_b5_1", "is_10b5_1", default=None)
    rule = getattr(rule, "value", rule)
    routine = _get(value, "routine", "is_routine", default=None)
    event_date = _date(_get(tx, "transaction_date", "event_at", "date", default=None))
    accepted = _stamp(
        _get(
            timestamps,
            "accepted_at",
            "filing_at",
            "source_at",
            default=_get(value, "accepted_at", "filing_at", "source_at", default=None),
        )
    )
    knowledge = _stamp(
        _get(timestamps, "knowledge_at", default=_get(value, "knowledge_at", default=None))
    )
    if issuer is None:
        issuer = ""
    if owner is None:
        owner = ""
    lifecycle = _get(value, "lifecycle", default=None)
    lifecycle_status = _get(lifecycle, "status", default="ACTIVE")
    lifecycle_status = getattr(lifecycle_status, "value", lifecycle_status)
    return {
        "_row_id": row_id,
        "issuer_cik": str(issuer),
        "owner_cik": str(owner),
        "transaction_date": event_date,
        "accepted_at": accepted,
        "knowledge_at": knowledge,
        "code": code,
        "acquired_disposed": acquired,
        "table_type": str(table or "NON_DERIVATIVE"),
        "classification": getattr(classification, "value", classification),
        "economic_classification": getattr(economic, "value", economic),
        "value_usd": value_usd,
        "shares": shares,
        "price_per_share": price,
        "post_transaction_shares": _number(
            _get(tx, "post_transaction_shares", "shares_owned_following_transaction", default=None)
        ),
        "rule_10b5_1": str(rule or "UNKNOWN").upper(),
        "routine": bool(routine) if routine is not None else None,
        "role": _role(value),
        "lifecycle_status": str(lifecycle_status),
        "valid_from": _stamp(_get(lifecycle, "valid_from", "validFrom")),
        "valid_to": _stamp(_get(lifecycle, "valid_to", "validTo")),
        "symbolic": _get(value, "symbolic", "is_symbolic", default=None),
        "_raw": value,
    }


def _rows(transactions: pl.DataFrame | Sequence[Any] | Iterable[Any]) -> list[dict[str, Any]]:
    if isinstance(transactions, pl.DataFrame):
        frame = transactions.clone()
        # Polars' Python conversion can require an installed system tzdata
        # package for timezone-aware columns.  Strings retain the instant and
        # are parsed by ``_stamp`` without that optional dependency.
        temporal_names = [
            name
            for name in ("accepted_at", "knowledge_at", "source_at", "filing_at")
            if name in frame.columns
        ]
        if temporal_names:
            frame = frame.with_columns([pl.col(name).cast(pl.String) for name in temporal_names])
        result: list[dict[str, Any]] = []
        aliases = {"issuer": "issuer_cik", "owner": "owner_cik", "value": "value_usd"}
        for index, item in enumerate(frame.to_dicts()):
            for old, new in aliases.items():
                if old in item and new not in item:
                    item[new] = item[old]
            result.append(_record(item, index))
        return result
    return [_record(item, index) for index, item in enumerate(transactions)]


def _validate(rows: Sequence[dict[str, Any]], as_of: date | datetime) -> date:
    cutoff, stamp = _cutoff(as_of)
    for row in rows:
        event = row["transaction_date"]
        if event is None:
            raise ValueError("transaction row missing transaction_date")
        if event > cutoff:
            raise ValueError(f"filing transaction dated after as_of: {event}")
        for name in ("accepted_at", "knowledge_at"):
            candidate = row[name]
            if candidate is not None and candidate > stamp:
                raise ValueError(f"filing {name} later than as_of: {candidate.isoformat()}")
        for name in ("value_usd", "shares", "price_per_share", "post_transaction_shares"):
            if row[name] is not None and not _finite(row[name]):
                raise ValueError(f"non-finite transaction {name}")
    return cutoff


def _effective(row: Mapping[str, Any], as_of: date | datetime) -> bool:
    """Return whether a lifecycle row is effective at the requested cutoff."""

    _cutoff_date, stamp = _cutoff(as_of)
    status = str(row.get("lifecycle_status") or "ACTIVE").upper()
    if status.endswith("VOID"):
        return False
    valid_from = row.get("valid_from")
    valid_to = row.get("valid_to")
    if valid_from is not None and valid_from > stamp:
        return False
    if valid_to is not None and stamp >= valid_to:
        return False
    if status.endswith("SUPERSEDED") and valid_to is None:
        return False
    return status.endswith("ACTIVE") or status.endswith("SUPERSEDED")


def _buy(row: Mapping[str, Any]) -> bool:
    classification = str(row.get("classification") or "").upper()
    economic = str(row.get("economic_classification") or "").upper()
    return str(row.get("acquired_disposed") or "") in {"", "A"} and (
        str(row.get("code") or "") == "P"
        or classification == TransactionClassification.OPEN_MARKET_PURCHASE.value
        or economic == EconomicClassification.OPEN_MARKET_PURCHASE.value
    )


def _context_lookup(
    context: Any, row: Mapping[str, Any], *, names: tuple[str, ...]
) -> dict[str, Any]:
    if context is None:
        return {}
    if isinstance(context, pl.DataFrame):
        frame = context
        if frame.is_empty():
            return {}
        candidates = frame
        issuer = row["issuer_cik"]
        for key in ("issuer_cik", "issuer", "symbol", "ticker"):
            if key in candidates.columns:
                candidates = candidates.filter(pl.col(key).cast(pl.String) == issuer)
                if not candidates.is_empty():
                    break
        if "date" in candidates.columns:
            context_dates = candidates.get_column("date").cast(pl.Date, strict=False)
            if (context_dates > row["transaction_date"]).any():
                future = context_dates.filter(context_dates > row["transaction_date"]).min()
                raise ValueError(f"market context row dated after event: {future!r}")
            candidates = candidates.filter(context_dates <= row["transaction_date"])
            if candidates.is_empty():
                return {}
            candidates = candidates.sort("date").tail(1)
        return candidates.to_dicts()[0] if not candidates.is_empty() else {}
    if isinstance(context, Mapping):
        issuer = row["issuer_cik"]
        candidate = context.get(issuer, context.get(str(issuer).upper(), context))
        if isinstance(candidate, Mapping):
            return dict(candidate)
    return {}


def _percentile(value: float, prior: Sequence[float]) -> float | None:
    if not prior or not _finite(value):
        return None
    ordered = sorted(item for item in prior if _finite(item))
    if not ordered:
        return None
    less = sum(item < value for item in ordered)
    equal = sum(item == value for item in ordered)
    return (less + (equal + 1) / 2) / len(ordered) * 100.0


def prior_history_log_dollar_percentile(
    value: float | Decimal | None, prior_values: Sequence[float | Decimal]
) -> float | None:
    """Percentile of log10(1 + dollars) against strictly prior observations."""

    current = _number(value)
    prior = [_number(item) for item in prior_values]
    if current is None or current < 0:
        return None
    logs = [log10(1.0 + item) for item in prior if item is not None and item >= 0]
    return _percentile(log10(1.0 + current), logs)


def ownership_increase(
    current: float | None, prior: float | None, acquired_shares: float | None = None
) -> float | None:
    """Return 0--100 ownership-increase evidence, preserving unknown as null."""

    if current is not None and prior is not None and _finite(current) and _finite(prior):
        return 100.0 if current > prior else 0.0
    if acquired_shares is not None and _finite(acquired_shares):
        return 100.0 if acquired_shares > 0 else 0.0
    return None


def novelty(is_first_buy: bool | None) -> float | None:
    return None if is_first_buy is None else (100.0 if is_first_buy else 0.0)


def historical_largest_buy(value: float | None, prior_values: Sequence[float]) -> float | None:
    if value is None or not _finite(value):
        return None
    valid = [item for item in prior_values if _finite(item)]
    return 100.0 if not valid or value > max(valid) else 0.0


def drawdown_averaging_context(
    drawdown: float | None, prior_buy_prices: Sequence[float], current_price: float | None = None
) -> float | None:
    """Score buying in a drawdown or averaging down; market context is injected."""

    if drawdown is None or not _finite(drawdown):
        return None
    score = 100.0 if drawdown <= -0.20 else (50.0 if drawdown < 0 else 0.0)
    if current_price is not None and prior_buy_prices and _finite(current_price):
        valid = [item for item in prior_buy_prices if _finite(item)]
        if valid and current_price < max(valid):
            score = min(100.0, score + 15.0)
    return score


def conviction_features(
    transactions: pl.DataFrame | Sequence[CanonicalTransaction] | Iterable[CanonicalTransaction],
    *,
    as_of: date | datetime,
    market_context: Any = None,
    cluster_context: Any = None,
    routine_flags: Mapping[Any, bool] | None = None,
    symbolic_threshold_usd: float = 1_000.0,
) -> pl.DataFrame:
    """Build one explainable conviction row per eligible transaction.

    ``cluster_context`` and ``routine_flags`` are injected facts; this function
    never infers either algorithm.  A row dated or accepted after ``as_of`` is
    rejected to make accidental look-ahead visible to callers.
    """

    rows = _rows(transactions)
    _validate(rows, as_of)
    rows = [row for row in rows if _effective(row, as_of)]
    outputs: list[dict[str, Any]] = []
    for row in rows:
        if not _buy(row):
            continue
        prior = [
            item
            for item in rows
            if item["issuer_cik"] == row["issuer_cik"]
            and item["owner_cik"] == row["owner_cik"]
            and item["transaction_date"] < row["transaction_date"]
            and _buy(item)
        ]
        dollars = [item["value_usd"] for item in prior if item["value_usd"] is not None]
        prices = [item["price_per_share"] for item in prior if item["price_per_share"] is not None]
        first = not prior
        post_prior = [
            item
            for item in rows
            if item["issuer_cik"] == row["issuer_cik"]
            and item["owner_cik"] == row["owner_cik"]
            and item["transaction_date"] < row["transaction_date"]
            and item["post_transaction_shares"] is not None
        ]
        previous_post = (
            max(post_prior, key=lambda item: item["transaction_date"])["post_transaction_shares"]
            if post_prior
            else None
        )
        own = ownership_increase(row["post_transaction_shares"], previous_post, row["shares"])
        dollar_pct = prior_history_log_dollar_percentile(row["value_usd"], dollars)
        largest = historical_largest_buy(row["value_usd"], dollars)
        context = _context_lookup(
            market_context, row, names=("drawdown_from_52_week_high", "drawdown")
        )
        drawdown = _number(context.get("drawdown_from_52_week_high", context.get("drawdown")))
        average = drawdown_averaging_context(drawdown, prices, row["price_per_share"])
        cluster = _context_lookup(cluster_context, row, names=("cluster_score",))
        cluster_score = _number(cluster.get("cluster_score"))
        if cluster_score is None:
            cluster_score = _number(cluster.get("score"))
        routine = row["routine"]
        if routine is None and routine_flags is not None:
            routine = routine_flags.get(row["_row_id"], routine_flags.get(row["owner_cik"]))
        symbolic = row["symbolic"]
        if symbolic is None:
            symbolic = row["value_usd"] is not None and row["value_usd"] <= symbolic_threshold_usd
        penalties: list[str] = []
        if row["rule_10b5_1"] in {"YES", "TRUE"}:
            penalties.append("10B5_1")
        if routine:
            penalties.append("ROUTINE")
        if symbolic:
            penalties.append("SYMBOLIC")
        components = [
            role_factor(row["role"]),
            50.0 if dollar_pct is None else dollar_pct,
            50.0 if own is None else own,
            100.0 if first else 0.0,
            100.0 if largest == 100.0 else 0.0,
            50.0 if average is None else average,
            50.0 if cluster_score is None else cluster_score,
        ]
        score = max(
            0.0,
            min(
                100.0,
                sum(
                    weight * component
                    for weight, component in zip(
                        (0.2, 0.2, 0.15, 0.15, 0.1, 0.1, 0.1), components, strict=True
                    )
                )
                - sum(_PENALTIES[item] for item in penalties),
            ),
        )
        reasons = [f"ROLE_{row['role']}"]
        if first:
            reasons.append("FIRST_BUY")
        if largest == 100.0:
            reasons.append("LARGEST_BUY")
        if own == 100.0:
            reasons.append("OWNERSHIP_INCREASE")
        if average is not None and average > 0:
            reasons.append("DRAWDOWN_OR_AVERAGING")
        if cluster_score is not None and cluster_score >= 70:
            reasons.append("CLUSTER_CONTEXT")
        reasons.extend(penalties)
        available = sum(item is not None for item in (dollar_pct, own, average, cluster_score))
        confidence = "HIGH" if available >= 3 else ("MEDIUM" if available >= 1 else "LOW")
        outputs.append(
            {
                "row_id": row["_row_id"],
                "issuer_cik": row["issuer_cik"],
                "owner_cik": row["owner_cik"],
                "transaction_date": row["transaction_date"],
                "role": row["role"],
                "role_score": role_factor(row["role"]),
                "prior_history_log_dollar_percentile": dollar_pct,
                "ownership_increase_score": own,
                "novelty_score": novelty(first),
                "first_buy": first,
                "historical_largest_buy_score": largest,
                "largest_buy": largest == 100.0,
                "drawdown_averaging_score": average,
                "cluster_score": cluster_score,
                "penalty_points": sum(_PENALTIES[item] for item in penalties),
                "conviction_score": score,
                "reason_codes": reasons,
                "confidence": confidence,
            }
        )
    return (
        pl.DataFrame(outputs)
        if outputs
        else pl.DataFrame(
            schema={
                "issuer_cik": pl.String,
                "conviction_score": pl.Float64,
                "reason_codes": pl.List(pl.String),
                "confidence": pl.String,
            }
        )
    )


build_conviction_features = conviction_features
compute_conviction = conviction_features
conviction_score = conviction_features

__all__ = [
    "conviction_features",
    "build_conviction_features",
    "compute_conviction",
    "conviction_score",
    "role_factor",
    "prior_history_log_dollar_percentile",
    "ownership_increase",
    "novelty",
    "historical_largest_buy",
    "drawdown_averaging_context",
]
