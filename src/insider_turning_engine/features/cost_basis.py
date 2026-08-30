"""Point-in-time insider purchase cost-basis and reclaim facts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any

import polars as pl

from .conviction import _buy, _cutoff, _effective, _finite, _number, _rows, _validate

WINDOWS: tuple[int, ...] = (30, 90, 180, 365)


def _qualified(rows: Sequence[dict[str, Any]], *, as_of: date | datetime) -> list[dict[str, Any]]:
    cutoff = _validate(rows, as_of)
    result: list[dict[str, Any]] = []
    for row in rows:
        if row["transaction_date"] > cutoff or not _effective(row, as_of) or not _buy(row):
            continue
        if str(row["table_type"]).upper() != "NON_DERIVATIVE":
            continue
        if (
            row["shares"] is None
            or row["shares"] <= 0
            or row["price_per_share"] is None
            or row["price_per_share"] <= 0
        ):
            continue
        if not _finite(row["shares"]) or not _finite(row["price_per_share"]):
            raise ValueError("non-finite qualified purchase quantity")
        result.append(row)
    return result


def qualified_non_derivative_purchases(
    transactions: pl.DataFrame | Sequence[Any] | Iterable[Any], *, as_of: date | datetime
) -> pl.DataFrame:
    """Select active, priced, non-derivative open-market ``P`` purchases."""

    rows = _qualified(_rows(transactions), as_of=as_of)
    records = [
        {
            "row_id": row["_row_id"],
            "issuer_cik": row["issuer_cik"],
            "owner_cik": row["owner_cik"],
            "transaction_date": row["transaction_date"],
            "shares": row["shares"],
            "price_per_share": row["price_per_share"],
            "value_usd": row["value_usd"],
            "role": row["role"],
            "rule_10b5_1": row["rule_10b5_1"],
        }
        for row in rows
    ]
    if not records:
        return pl.DataFrame(
            schema={
                "issuer_cik": pl.String,
                "owner_cik": pl.String,
                "transaction_date": pl.Date,
                "shares": pl.Float64,
                "price_per_share": pl.Float64,
            }
        )
    return pl.DataFrame(records).sort(["issuer_cik", "transaction_date", "owner_cik"])


def _market_rows(market: Any, as_of: date | datetime) -> dict[str, float]:
    cutoff, stamp = _cutoff(as_of)
    if market is None:
        return {}
    if isinstance(market, Mapping):
        output: dict[str, float] = {}
        for key, value in market.items():
            candidate = value
            if isinstance(value, Mapping):
                candidate = value.get("close", value.get("adj_close", value.get("price")))
                available = value.get("available_at")
                parsed = (
                    datetime.fromisoformat(str(available).replace("Z", "+00:00"))
                    if available
                    else None
                )
                if parsed is not None and (parsed.tzinfo is None or parsed.astimezone() > stamp):
                    raise ValueError("market row available_at later than as_of")
            if candidate is not None and not _finite(candidate):
                raise ValueError("non-finite market price")
            number = _number(candidate)
            if number is not None and number > 0:
                output[str(key)] = number
        return output
    if isinstance(market, pl.DataFrame):
        frame = market.clone()
        symbol = (
            "symbol"
            if "symbol" in frame.columns
            else ("ticker" if "ticker" in frame.columns else "issuer_cik")
        )
        price = (
            "close"
            if "close" in frame.columns
            else ("adj_close" if "adj_close" in frame.columns else "price")
        )
        if symbol not in frame.columns or price not in frame.columns:
            raise ValueError("market frame requires symbol and close")
        if "date" in frame.columns:
            dates = frame.get_column("date").cast(pl.Date, strict=False)
            if (dates > cutoff).any():
                raise ValueError("market row dated after as_of")
            frame = frame.filter(dates <= cutoff)
        if "available_at" in frame.columns:
            available = frame.get_column("available_at").cast(pl.Datetime, strict=False)
            if (available.is_not_null() & (available > stamp.replace(tzinfo=None))).any():
                raise ValueError("market row available_at later than as_of")
            frame = frame.filter(available.is_null() | (available <= stamp.replace(tzinfo=None)))
            frame = frame.with_columns(pl.col("available_at").cast(pl.String))
        output = {}
        for row in frame.sort("date").to_dicts() if "date" in frame.columns else frame.to_dicts():
            if row.get(price) is not None and not _finite(row.get(price)):
                raise ValueError("non-finite market price")
            number = _number(row.get(price))
            if number is not None and number > 0:
                output[str(row[symbol])] = number
        return output
    output = {}
    for item in market:
        symbol = str(getattr(item, "symbol", getattr(item, "ticker", "")))
        row_date = getattr(item, "date", cutoff)
        available = getattr(item, "available_at", None)
        available_stamp = available if isinstance(available, datetime) else None
        if row_date > cutoff:
            raise ValueError("market row dated after as_of")
        if available_stamp is not None and (
            available_stamp.tzinfo is None or available_stamp.astimezone() > stamp
        ):
            raise ValueError("market row available_at later than as_of")
        raw_price = getattr(item, "adj_close", getattr(item, "close", None))
        if raw_price is not None and not _finite(raw_price):
            raise ValueError("non-finite market price")
        number = _number(raw_price)
        if number is not None and number > 0:
            output[symbol] = number
    return output


def _basis(
    rows: Sequence[dict[str, Any]],
    cutoff: date,
    window: int,
    issuer: str | None = None,
    owner: str | None = None,
) -> tuple[float | None, float, float]:
    lower = cutoff - timedelta(days=window)
    selected = [
        row
        for row in rows
        if row["transaction_date"] >= lower
        and row["transaction_date"] <= cutoff
        and (issuer is None or row["issuer_cik"] == issuer)
        and (owner is None or row["owner_cik"] == owner)
    ]
    quantity = sum(float(row["shares"]) for row in selected)
    dollars = sum(float(row["shares"]) * float(row["price_per_share"]) for row in selected)
    return (dollars / quantity if quantity > 0 else None, quantity, dollars)


def weighted_cost_basis(
    transactions: pl.DataFrame | Sequence[Any] | Iterable[Any],
    *,
    as_of: date | datetime,
    windows: Sequence[int] = WINDOWS,
) -> pl.DataFrame:
    """Return share-weighted purchase basis by issuer for calendar-day windows."""

    rows = _qualified(_rows(transactions), as_of=as_of)
    cutoff, _ = _cutoff(as_of)
    issuers = sorted({row["issuer_cik"] for row in rows})
    records: list[dict[str, Any]] = []
    for issuer in issuers:
        record: dict[str, Any] = {"issuer_cik": issuer, "as_of": cutoff}
        for window in windows:
            basis, quantity, dollars = _basis(rows, cutoff, int(window), issuer=issuer)
            record[f"cost_basis_{window}d"] = basis
            record[f"purchase_shares_{window}d"] = quantity
            record[f"purchase_dollars_{window}d"] = dollars
        records.append(record)
    if not records:
        return pl.DataFrame(schema={"issuer_cik": pl.String, "as_of": pl.Date})
    return pl.DataFrame(records).sort("issuer_cik")


def insider_profit_loss(
    transactions: pl.DataFrame | Sequence[Any] | Iterable[Any],
    *,
    as_of: date | datetime,
    market: Any = None,
    windows: Sequence[int] = WINDOWS,
) -> pl.DataFrame:
    """Compute unrealized P/L against each insider's weighted purchase basis."""

    rows = _qualified(_rows(transactions), as_of=as_of)
    cutoff, _ = _cutoff(as_of)
    prices = _market_rows(market, as_of)
    keys = sorted({(row["issuer_cik"], row["owner_cik"]) for row in rows})
    records: list[dict[str, Any]] = []
    for issuer, owner in keys:
        current = prices.get(issuer)
        if current is None:
            current = prices.get(issuer.upper())
        record: dict[str, Any] = {
            "issuer_cik": issuer,
            "owner_cik": owner,
            "as_of": cutoff,
            "current_price": current,
        }
        reasons: list[str] = []
        for window in windows:
            basis, quantity, _ = _basis(rows, cutoff, int(window), issuer=issuer, owner=owner)
            record[f"cost_basis_{window}d"] = basis
            record[f"insider_pnl_{window}d"] = (
                (current - basis) * quantity if current is not None and basis is not None else None
            )
            if basis is None:
                reasons.append(f"NO_PURCHASE_{window}D")
        record["reason_codes"] = reasons or (
            ["MISSING_MARKET_PRICE"] if current is None else ["P_L_AVAILABLE"]
        )
        record["confidence"] = "LOW" if current is None else ("MEDIUM" if reasons else "HIGH")
        records.append(record)
    return (
        pl.DataFrame(records)
        if records
        else pl.DataFrame(
            schema={"issuer_cik": pl.String, "owner_cik": pl.String, "as_of": pl.Date}
        )
    )


def cost_basis_reclaim_facts(
    transactions: pl.DataFrame | Sequence[Any] | Iterable[Any],
    *,
    as_of: date | datetime,
    market: Any = None,
    windows: Sequence[int] = WINDOWS,
) -> pl.DataFrame:
    """Return whether the latest eligible market price reclaims purchase basis."""

    basis = weighted_cost_basis(transactions, as_of=as_of, windows=windows)
    prices = _market_rows(market, as_of)
    if basis.is_empty():
        return basis.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("current_price"),
            pl.lit(None, dtype=pl.Boolean).alias("cost_basis_reclaim"),
        )
    records: list[dict[str, Any]] = []
    for row in basis.to_dicts():
        issuer = str(row["issuer_cik"])
        current = prices.get(issuer, prices.get(issuer.upper()))
        reclaim_values = [
            current is not None
            and row.get(f"cost_basis_{window}d") is not None
            and current >= row[f"cost_basis_{window}d"]
            for window in windows
        ]
        canonical_window = 90 if 90 in windows else int(windows[0])
        canonical_basis = row.get(f"cost_basis_{canonical_window}d")
        record = dict(row)
        record["current_price"] = current
        for window, value in zip(windows, reclaim_values, strict=True):
            record[f"cost_basis_reclaim_{window}d"] = (
                value
                if current is not None and row.get(f"cost_basis_{window}d") is not None
                else None
            )
        record["cost_basis_reclaim"] = (
            current is not None and canonical_basis is not None and current >= canonical_basis
        )
        record["reason_codes"] = (
            ["COST_BASIS_RECLAIMED"]
            if record["cost_basis_reclaim"]
            else (["BELOW_COST_BASIS"] if current is not None else ["MISSING_MARKET_PRICE"])
        )
        record["confidence"] = (
            "HIGH" if current is not None and canonical_basis is not None else "LOW"
        )
        records.append(record)
    return pl.DataFrame(records)


qualified_purchases = qualified_non_derivative_purchases
compute_cost_basis = weighted_cost_basis
cost_basis_features = cost_basis_reclaim_facts
insider_pnl = insider_profit_loss
cost_basis_reclaim = cost_basis_reclaim_facts

__all__ = [
    "WINDOWS",
    "qualified_non_derivative_purchases",
    "qualified_purchases",
    "weighted_cost_basis",
    "compute_cost_basis",
    "cost_basis_features",
    "insider_profit_loss",
    "insider_pnl",
    "cost_basis_reclaim_facts",
    "cost_basis_reclaim",
]
