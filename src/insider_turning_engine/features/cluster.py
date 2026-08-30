"""Bounded, owner-independent insider cluster facts."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from typing import Any

import polars as pl

from insider_turning_engine.domain.models import CanonicalTransaction

from .conviction import _buy, _effective, _rows, _validate

CLUSTER_WINDOW_DAYS = 30
IMPORTANT_OWNER_COUNT = 2
STRONG_OWNER_COUNT = 3


def _active(row: dict[str, Any]) -> bool:
    status = str(row.get("lifecycle_status") or "ACTIVE").upper()
    return status == "ACTIVE" or status.endswith(".ACTIVE")


def _empty() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "row_id": pl.Int64,
            "issuer_cik": pl.String,
            "transaction_date": pl.Date,
            "cluster_score": pl.Float64,
            "important_cluster": pl.Boolean,
            "strong_cluster": pl.Boolean,
            "reason_codes": pl.List(pl.String),
            "confidence": pl.String,
        }
    )


def cluster_features(
    transactions: pl.DataFrame | Sequence[CanonicalTransaction] | Iterable[CanonicalTransaction],
    *,
    as_of: date | datetime,
    window_days: int = CLUSTER_WINDOW_DAYS,
) -> pl.DataFrame:
    """Return purchase-level clusters using only purchases known on that date.

    A cluster is based on distinct reporting-owner CIKs, never filing row
    count.  The inclusive lookback is bounded by ``window_days`` and ends at
    the target transaction date.  Thus same-day rows can corroborate one
    another, while later rows cannot alter historical evidence.
    """

    if window_days <= 0:
        raise ValueError("window_days must be positive")
    rows = _rows(transactions)
    _validate(rows, as_of)
    rows = [row for row in rows if _effective(row, as_of)]
    buys = [row for row in rows if _active(row) and _buy(row)]
    results: list[dict[str, Any]] = []
    for row in buys:
        event = row["transaction_date"]
        assert isinstance(event, date)
        members = [
            item
            for item in buys
            if item["issuer_cik"] == row["issuer_cik"]
            and event - timedelta(days=window_days) <= item["transaction_date"] <= event
        ]
        owners = sorted({str(item["owner_cik"]) for item in members if item["owner_cik"]})
        owner_count = len(owners)
        strong = owner_count >= STRONG_OWNER_COUNT
        important = owner_count >= IMPORTANT_OWNER_COUNT
        score = 100.0 if strong else (70.0 if important else 0.0)
        reasons = [f"INDEPENDENT_OWNER_COUNT_{owner_count}"]
        if strong:
            reasons.append("STRONG_CLUSTER")
        elif important:
            reasons.append("IMPORTANT_CLUSTER")
        else:
            reasons.append("NO_CLUSTER")
        results.append(
            {
                "row_id": row["_row_id"],
                "issuer_cik": row["issuer_cik"],
                "owner_cik": row["owner_cik"],
                "transaction_date": event,
                "cluster_window_days": window_days,
                "cluster_owner_count": owner_count,
                "cluster_owner_ids": owners,
                "important_cluster": important,
                "strong_cluster": strong,
                "cluster_score": score,
                "reason_codes": reasons,
                "confidence": "HIGH",
            }
        )
    if not results:
        return _empty()
    return pl.DataFrame(results).sort(["issuer_cik", "transaction_date", "owner_cik", "row_id"])


insider_cluster_features = cluster_features
compute_cluster = cluster_features
cluster_score = cluster_features

__all__ = [
    "CLUSTER_WINDOW_DAYS",
    "IMPORTANT_OWNER_COUNT",
    "STRONG_OWNER_COUNT",
    "cluster_features",
    "insider_cluster_features",
    "compute_cluster",
    "cluster_score",
]
