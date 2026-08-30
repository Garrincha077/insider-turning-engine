"""Point-in-time routine versus opportunistic insider-purchase facts.

The classifier intentionally produces facts per purchase rather than trying to
infer a permanent attribute of an insider.  Its history always ends strictly
before the purchase being classified, so a later filing cannot re-label an
older purchase.  Sparse history is a data-quality condition, not evidence of
either behaviour.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any

import polars as pl

from insider_turning_engine.domain.models import CanonicalTransaction

from .conviction import _buy, _effective, _finite, _rows, _validate

HISTORY_DAYS = 2 * 365
FIRST_BUY_DAYS = 3 * 365
REENTRY_DAYS = 365
MIN_PRIOR_TRANSACTIONS = 4


def _active(row: dict[str, Any]) -> bool:
    status = str(row.get("lifecycle_status") or "ACTIVE").upper()
    return status == "ACTIVE" or status.endswith(".ACTIVE")


def _coefficient_of_variation(values: Sequence[float]) -> float | None:
    if not values:
        return None
    centre = sum(values) / len(values)
    if centre <= 0:
        return None
    variance = sum((item - centre) ** 2 for item in values) / len(values)
    return float(variance**0.5 / centre)


def _empty() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "row_id": pl.Int64,
            "issuer_cik": pl.String,
            "owner_cik": pl.String,
            "transaction_date": pl.Date,
            "opportunistic_score": pl.Float64,
            "is_routine": pl.Boolean,
            "is_opportunistic": pl.Boolean,
            "reason_codes": pl.List(pl.String),
            "confidence": pl.String,
        }
    )


def opportunistic_features(
    transactions: pl.DataFrame | Sequence[CanonicalTransaction] | Iterable[CanonicalTransaction],
    *,
    as_of: date | datetime,
    history_days: int = HISTORY_DAYS,
    first_buy_days: int = FIRST_BUY_DAYS,
    reentry_days: int = REENTRY_DAYS,
) -> pl.DataFrame:
    """Classify eligible purchases using only earlier same-owner activity.

    A row with fewer than four prior owner/issuer transactions in the prior two
    years receives neutral 50 and ``LOW_CONFIDENCE``.  Two auditable exceptions
    are retained: no earlier purchase in three years (``FIRST_BUY_3Y``), and a
    purchase following a one-year purchase hiatus (``INSIDER_REENTRY``).
    """

    if min(history_days, first_buy_days, reentry_days) <= 0:
        raise ValueError("history windows must be positive")
    rows = _rows(transactions)
    _validate(rows, as_of)
    rows = [row for row in rows if _effective(row, as_of)]
    eligible = [row for row in rows if _active(row)]
    output: list[dict[str, Any]] = []
    for row in eligible:
        if not _buy(row):
            continue
        event = row["transaction_date"]
        assert isinstance(event, date)
        owner_history = [
            item
            for item in eligible
            if item["issuer_cik"] == row["issuer_cik"]
            and item["owner_cik"] == row["owner_cik"]
            and item["transaction_date"] < event
        ]
        history_start = event - timedelta(days=history_days)
        prior_window = [item for item in owner_history if item["transaction_date"] >= history_start]
        prior_buys = [item for item in owner_history if _buy(item)]
        first_buy_start = event - timedelta(days=first_buy_days)
        buys_3y = [item for item in prior_buys if item["transaction_date"] >= first_buy_start]
        last_buy = max((item["transaction_date"] for item in prior_buys), default=None)
        first_buy = not buys_3y
        reentry = last_buy is not None and (event - last_buy).days >= reentry_days
        reasons: list[str] = []
        if first_buy:
            reasons.append("FIRST_BUY_3Y")
        if reentry:
            reasons.append("INSIDER_REENTRY")

        current_price = row["price_per_share"]
        prior_prices = [
            float(item["price_per_share"])
            for item in prior_buys
            if item["price_per_share"] is not None and _finite(item["price_per_share"])
        ]
        averaging_down = (
            current_price is not None
            and _finite(current_price)
            and bool(prior_prices)
            and float(current_price) < min(prior_prices)
        )
        if averaging_down:
            reasons.append("AVERAGING_DOWN")

        # Sparse history is deliberately neutral unless a long absence is an
        # independently observable fact.  The exception still keeps a visible
        # history reason because it should not be mistaken for high confidence.
        if len(prior_window) < MIN_PRIOR_TRANSACTIONS:
            reasons.append("LOW_HISTORY")
            if not (first_buy or reentry):
                output.append(
                    {
                        "row_id": row["_row_id"],
                        "issuer_cik": row["issuer_cik"],
                        "owner_cik": row["owner_cik"],
                        "transaction_date": event,
                        "prior_transaction_count_2y": len(prior_window),
                        "first_buy_3y": first_buy,
                        "insider_reentry": reentry,
                        "averaging_down": averaging_down,
                        "is_routine": None,
                        "is_opportunistic": None,
                        "opportunistic_score": 50.0,
                        "reason_codes": reasons + ["NEUTRAL_INSUFFICIENT_HISTORY"],
                        "confidence": "LOW_CONFIDENCE",
                    }
                )
                continue

        prior_purchase_dates = sorted(item["transaction_date"] for item in prior_buys)
        gaps = [
            float((right - left).days)
            for left, right in zip(prior_purchase_dates, prior_purchase_dates[1:], strict=False)
            if (right - left).days > 0
        ]
        values = [
            float(item["value_usd"])
            for item in prior_buys
            if item["value_usd"] is not None
            and _finite(item["value_usd"])
            and item["value_usd"] > 0
        ]
        gap_cv = _coefficient_of_variation(gaps)
        value_cv = _coefficient_of_variation(values)
        cadence = median(gaps) if gaps else None
        routine = (
            gap_cv is not None
            and value_cv is not None
            and cadence is not None
            and 14 <= cadence <= 180
            and gap_cv <= 0.50
            and value_cv <= 0.75
        )
        if routine:
            reasons.append("ROUTINE_CADENCE")
        else:
            reasons.append("OPPORTUNISTIC_NON_ROUTINE")
        if first_buy or reentry:
            reasons.append("OPPORTUNISTIC_NOVELTY")
        score = 20.0 if routine else 80.0
        if first_buy or reentry:
            score = max(score, 90.0)
        output.append(
            {
                "row_id": row["_row_id"],
                "issuer_cik": row["issuer_cik"],
                "owner_cik": row["owner_cik"],
                "transaction_date": event,
                "prior_transaction_count_2y": len(prior_window),
                "first_buy_3y": first_buy,
                "insider_reentry": reentry,
                "averaging_down": averaging_down,
                "is_routine": routine,
                "is_opportunistic": not routine,
                "opportunistic_score": score,
                "reason_codes": reasons,
                "confidence": "HIGH" if gap_cv is not None and value_cv is not None else "MEDIUM",
            }
        )
    if not output:
        return _empty()
    return pl.DataFrame(output).sort(["issuer_cik", "transaction_date", "owner_cik", "row_id"])


routine_opportunistic_features = opportunistic_features
classify_opportunistic = opportunistic_features
opportunistic_classification = opportunistic_features

__all__ = [
    "HISTORY_DAYS",
    "FIRST_BUY_DAYS",
    "REENTRY_DAYS",
    "MIN_PRIOR_TRANSACTIONS",
    "opportunistic_features",
    "routine_opportunistic_features",
    "classify_opportunistic",
    "opportunistic_classification",
]
