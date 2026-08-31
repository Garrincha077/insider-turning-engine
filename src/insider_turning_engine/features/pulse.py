"""Point-in-time market and sector insider-activity pulse features.

The Pulse is deliberately storage neutral.  Inputs may be canonical
``CanonicalTransaction`` objects (or their JSON/model dumps), or a Polars
frame with flattened transaction columns.  All calculations are performed on
effective, qualified, non-derivative open-market ``P``/``S`` rows that were
known by ``as_of``.  Ratios never manufacture infinity: an unknown denominator
is represented by a null and an explicit quality reason.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from pathlib import Path
from typing import Any

import polars as pl
import yaml  # type: ignore[import-untyped]

from insider_turning_engine.domain.models import CanonicalTransaction
from insider_turning_engine.domain.time import us_equity_session_close

type TransactionsInput = (
    pl.DataFrame
    | pl.LazyFrame
    | Sequence[CanonicalTransaction | Mapping[str, Any]]
    | Iterable[CanonicalTransaction | Mapping[str, Any]]
)

_GRAINS: tuple[str, ...] = ("daily", "weekly", "4W", "13W")
_RATIO_COLUMNS: tuple[str, ...] = (
    "transaction_ps_ratio",
    "unique_insider_ratio",
    "dollar_ratio",
    "volume_ratio",
    "company_breadth",
    "conviction_weighted_ratio",
)
_WEIGHT_KEYS = (
    "transaction",
    "unique_insiders",
    "dollar",
    "volume",
    "company_breadth",
    "conviction_weighted",
)


def _as_of_datetime(value: date | datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    return us_equity_session_close(value)


def _as_date(value: date | datetime | None) -> date:
    return _as_of_datetime(value).date()


def _value(record: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    """Read snake/camel aliases from flat or nested model-dump records."""

    for name in names:
        if name in record:
            return record[name]
        camel = name.split("_")[0] + "".join(part.title() for part in name.split("_")[1:])
        if camel in record:
            return record[camel]
    return default


def _nested(record: Mapping[str, Any], group: str, *names: str, default: Any = None) -> Any:
    value = _value(record, *names)
    if value is not None:
        return value
    child = record.get(group) or record.get(group[0].lower() + group[1:])
    if isinstance(child, Mapping):
        return _value(child, *names, default=default)
    return default


def _date_from(value: Any) -> date | None:
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


def _instant_from(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            result = datetime.fromisoformat(text)
        except ValueError:
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _quality_passes(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, Mapping):
        value = _value(value, "status", default=None)
    text = str(getattr(value, "value", value)).upper()
    return text not in {"QUARANTINED", "REJECTED", "INVALID", "FALSE", "0"}


def _raw_frame(transactions: TransactionsInput) -> pl.DataFrame:
    if isinstance(transactions, pl.LazyFrame):
        return transactions.collect()
    if isinstance(transactions, pl.DataFrame):
        return transactions.clone()
    rows: list[dict[str, Any]] = []
    for item in transactions:
        if isinstance(item, CanonicalTransaction):
            rows.append(item.model_dump(mode="python"))
        elif isinstance(item, Mapping):
            rows.append(dict(item))
        else:
            raise TypeError("transactions must contain CanonicalTransaction or mapping values")
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def _normalise(
    transactions: TransactionsInput,
    *,
    as_of: datetime,
    sector_by_issuer: Mapping[str, str] | None,
) -> pl.DataFrame:
    raw = _raw_frame(transactions)
    if raw.is_empty():
        return pl.DataFrame(
            schema={
                "transaction_id": pl.String,
                "revision_id": pl.String,
                "issuer_cik": pl.String,
                "owner_id": pl.String,
                "sector": pl.String,
                "transaction_date": pl.Date,
                "side": pl.String,
                "shares": pl.Float64,
                "dollar_value": pl.Float64,
                "conviction": pl.Float64,
                "knowledge_at": pl.Datetime(time_zone="UTC"),
            }
        )
    # ``datetime.timezone.utc`` is not available in a few minimal Windows
    # Python installations used by the engine's test runner.  Removing the
    # Polars timezone metadata before Python conversion preserves the instant
    # (all timestamps are normalized to UTC below) and avoids a pyarrow/zoneinfo
    # lookup during ``to_dicts``.
    for name, dtype in raw.schema.items():
        if isinstance(dtype, pl.Datetime) and dtype.time_zone is not None:
            raw = raw.with_columns(pl.col(name).dt.replace_time_zone(None).alias(name))
    records = raw.to_dicts()
    normal: list[dict[str, Any]] = []
    for record in records:
        transaction_date = _date_from(_nested(record, "transaction", "transaction_date"))
        if transaction_date is None:
            transaction_date = _date_from(_value(record, "transaction_date", "date"))
        if transaction_date is None:
            continue
        knowledge = _instant_from(_nested(record, "timestamps", "knowledge_at"))
        if knowledge is None:
            knowledge = _instant_from(_value(record, "knowledge_at", "observed_at"))
        accepted = _instant_from(_nested(record, "timestamps", "accepted_at"))
        if accepted is None:
            accepted = _instant_from(_value(record, "accepted_at"))
        if (knowledge is not None and knowledge > as_of) or (
            accepted is not None and accepted > as_of
        ):
            continue

        lifecycle = record.get("lifecycle") or {}
        status = (
            _value(lifecycle, "status", default=_value(record, "lifecycle_status"))
            if isinstance(lifecycle, Mapping)
            else _value(record, "lifecycle_status")
        )
        # A superseded revision remains the effective historical view until
        # its successor's valid_from.  Only VOID is always excluded.
        if str(getattr(status, "value", status)).upper() in {"VOID"}:
            continue
        valid_from = (
            _instant_from(_value(lifecycle, "valid_from"))
            if isinstance(lifecycle, Mapping)
            else _instant_from(_value(record, "valid_from"))
        )
        valid_to = (
            _instant_from(_value(lifecycle, "valid_to"))
            if isinstance(lifecycle, Mapping)
            else _instant_from(_value(record, "valid_to"))
        )
        if (valid_from is not None and valid_from > as_of) or (
            valid_to is not None and as_of >= valid_to
        ):
            continue

        table_type = _nested(record, "security", "table_type", default=_value(record, "table_type"))
        is_derivative = _value(record, "is_derivative", default=None)
        table_text = str(getattr(table_type, "value", table_type)).upper()
        if is_derivative is True or table_text in {"DERIVATIVE", "D"}:
            continue
        code = _nested(record, "transaction", "code", default=_value(record, "code"))
        classification = _nested(
            record,
            "transaction",
            "economic_classification",
            default=_value(record, "economic_classification"),
        )
        code_text = str(getattr(code, "value", code)).upper()
        classification_text = str(getattr(classification, "value", classification)).upper()
        if code_text not in {"P", "S"}:
            code_text = (
                "P"
                if "PURCHASE" in classification_text
                else "S"
                if "SALE" in classification_text
                else ""
            )
        if code_text not in {"P", "S"}:
            continue
        quality = record.get("quality")
        if not _quality_passes(
            quality if quality is not None else _value(record, "quality_status", "qualified")
        ):
            continue

        issuer = record.get("issuer") or {}
        owner = record.get("reporting_owner") or record.get("reportingOwner") or {}
        issuer_cik = str(
            _value(issuer, "cik", default=_value(record, "issuer_cik", "cik", default=""))
        )
        owner_id = str(
            _value(owner, "owner_id", default=_value(record, "owner_id", "owner_cik", default=""))
        )
        sector: Any = _value(record, "sector", "sector_name", "industry")
        if sector is None and sector_by_issuer is not None:
            sector = sector_by_issuer.get(issuer_cik) or sector_by_issuer.get(
                issuer_cik.lstrip("0")
            )
        shares = _number(_nested(record, "transaction", "shares", default=_value(record, "shares")))
        price = _number(
            _nested(
                record, "transaction", "price_per_share", default=_value(record, "price_per_share")
            )
        )
        value = _number(
            _nested(record, "transaction", "value", default=_value(record, "value", "dollar_value"))
        )
        if value is None and shares is not None and price is not None:
            value = shares * price
        conviction = _number(_value(record, "conviction_score", "conviction", "conviction_weight"))
        normal.append(
            {
                "transaction_id": str(_value(record, "transaction_id", default="")),
                "revision_id": str(_value(record, "revision_id", default="")),
                "issuer_cik": issuer_cik,
                "owner_id": owner_id,
                "sector": str(sector).strip()
                if sector is not None and str(sector).strip()
                else None,
                "transaction_date": transaction_date,
                "side": code_text,
                "shares": shares,
                "dollar_value": value,
                "conviction": conviction,
                "knowledge_at": knowledge,
            }
        )
    if not normal:
        return pl.DataFrame(
            schema={
                "transaction_id": pl.String,
                "revision_id": pl.String,
                "issuer_cik": pl.String,
                "owner_id": pl.String,
                "sector": pl.String,
                "transaction_date": pl.Date,
                "side": pl.String,
                "shares": pl.Float64,
                "dollar_value": pl.Float64,
                "conviction": pl.Float64,
                "knowledge_at": pl.Datetime(time_zone="UTC"),
            }
        )
    frame = pl.DataFrame(normal)
    # A transaction's latest eligible revision is its effective point-in-time view.
    if frame.get_column("transaction_id").str.len_chars().sum() > 0:
        frame = frame.sort(["transaction_id", "knowledge_at", "revision_id"], nulls_last=True)
        frame = frame.unique("transaction_id", keep="last")
    return frame


def _weights(weights: Mapping[str, float] | None) -> dict[str, float]:
    if weights is not None:
        parsed = {key: float(weights[key]) for key in _WEIGHT_KEYS if key in weights}
    else:
        config_path = Path(__file__).resolve().parents[3] / "config" / "scoring.v1.yaml"
        try:
            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            parsed = {
                key: float(value)
                for key, value in loaded["models"]["market_pulse"]["weights"].items()
            }
        except (OSError, KeyError, TypeError, ValueError):
            parsed = {
                "transaction": 0.15,
                "unique_insiders": 0.20,
                "dollar": 0.20,
                "volume": 0.10,
                "company_breadth": 0.15,
                "conviction_weighted": 0.20,
            }
    if (
        set(parsed) != set(_WEIGHT_KEYS)
        or not all(isfinite(v) and v >= 0 for v in parsed.values())
        or abs(sum(parsed.values()) - 1.0) > 1e-9
    ):
        raise ValueError(
            "market pulse weights must contain exactly the scoring.v1 factors and sum to 1"
        )
    return parsed


def _bounds(grain: str, endpoint: date) -> tuple[date, date]:
    normalized = grain.lower()
    if normalized == "daily":
        return endpoint, endpoint
    monday = endpoint - timedelta(days=endpoint.weekday())
    if normalized == "weekly":
        return monday, endpoint
    if normalized in {"4w", "4-week", "4_week"}:
        return monday - timedelta(days=21), endpoint
    if normalized in {"13w", "13-week", "13_week"}:
        return monday - timedelta(days=84), endpoint
    raise ValueError(f"unsupported pulse grain: {grain}")


def _ratio(numerator: float, denominator: float) -> float | None:
    if not isfinite(numerator) or not isfinite(denominator) or denominator <= 0:
        return None
    result = numerator / denominator
    return result if isfinite(result) else None


def _aggregate(frame: pl.DataFrame, start: date, end: date) -> dict[str, Any]:
    current = frame.filter(
        (pl.col("transaction_date") >= pl.lit(start)) & (pl.col("transaction_date") <= pl.lit(end))
    )
    if current.is_empty():
        selected: list[dict[str, Any]] = []
    else:
        # The timestamp is only an eligibility filter and is not needed for
        # arithmetic; omit it from Python conversion (see the Windows UTC
        # zoneinfo note in ``_normalise``).
        selected = current.drop("knowledge_at").to_dicts()
    purchases = [row for row in selected if row["side"] == "P"]
    sales = [row for row in selected if row["side"] == "S"]
    reasons: list[str] = []

    def total(rows: list[dict[str, Any]], key: str) -> float:
        return sum(
            float(row[key])
            for row in rows
            if row.get(key) is not None and isfinite(float(row[key]))
        )

    p_tx, s_tx = len(purchases), len(sales)
    p_ins = {row["owner_id"] for row in purchases if row.get("owner_id")}
    s_ins = {row["owner_id"] for row in sales if row.get("owner_id")}
    p_comp = {row["issuer_cik"] for row in purchases if row.get("issuer_cik")}
    s_comp = {row["issuer_cik"] for row in sales if row.get("issuer_cik")}
    p_dollar, s_dollar = total(purchases, "dollar_value"), total(sales, "dollar_value")
    p_volume, s_volume = total(purchases, "shares"), total(sales, "shares")

    def guarded(name: str, numerator: float, denominator: float) -> float | None:
        value = _ratio(numerator, denominator)
        if value is None:
            reasons.append(f"UNKNOWN_DENOMINATOR:{name}")
        return value

    def conviction_total(rows: list[dict[str, Any]]) -> float:
        weighted: list[dict[str, Any]] = []
        for row in rows:
            amount = row.get("dollar_value")
            conviction = row.get("conviction")
            weight = conviction if conviction is not None else 1.0
            weighted.append(
                {**row, "dollar_value": (amount if amount is not None else 0.0) * weight}
            )
        return total(weighted, "dollar_value")

    p_conv = conviction_total(purchases)
    s_conv = conviction_total(sales)
    values = {
        "transaction_ps_ratio": guarded("transaction_ps_ratio", p_tx, s_tx),
        "unique_insider_ratio": guarded("unique_insider_ratio", len(p_ins), len(s_ins)),
        "dollar_ratio": guarded("dollar_ratio", p_dollar, s_dollar),
        "volume_ratio": guarded("volume_ratio", p_volume, s_volume),
        "company_breadth": guarded("company_breadth", len(p_comp), len(s_comp)),
        "conviction_weighted_ratio": guarded("conviction_weighted_ratio", p_conv, s_conv),
    }
    return {
        **values,
        "transaction_count": len(selected),
        "purchase_transactions": p_tx,
        "sale_transactions": s_tx,
        "purchase_dollars": p_dollar,
        "sale_dollars": s_dollar,
        "purchase_shares": p_volume,
        "sale_shares": s_volume,
        "buying_insiders": len(p_ins),
        "selling_insiders": len(s_ins),
        "buying_companies": len(p_comp),
        "selling_companies": len(s_comp),
        "quality_reasons": reasons,
    }


def _percentile(value: float | None, history: Sequence[float | None]) -> float | None:
    if value is None or not isfinite(value):
        return None
    prior = sorted(item for item in history if item is not None and isfinite(item))
    if not prior:
        return None
    # Mid-rank percentile over strictly prior observations, on a 0..100 scale.
    lower = sum(item < value for item in prior)
    equal = sum(item == value for item in prior)
    # Clamp the half-rank convention at the top of the empirical support;
    # unlike a raw ``rank / n`` expression this can never emit >100.
    return min(100.0, ((lower + (equal + 1) / 2) / len(prior)) * 100.0)


def market_pulse(
    transactions: TransactionsInput,
    *,
    as_of: date | datetime | None = None,
    sector_by_issuer: Mapping[str, str] | None = None,
    sector_map: Mapping[str, str] | None = None,
    grains: Sequence[str] = _GRAINS,
    weights: Mapping[str, float] | None = None,
) -> pl.DataFrame:
    """Compute current daily/weekly/4W/13W market and sector Pulse rows.

    ``as_of`` is inclusive for event dates and for acceptance/knowledge
    timestamps.  Percentiles use only complete same-grain windows whose end is
    strictly before the current window start, so adding a future row cannot
    alter a historical result.
    """

    point = _as_of_datetime(as_of)
    endpoint = point.date()
    normalized = _normalise(
        transactions, as_of=point, sector_by_issuer=sector_by_issuer or sector_map
    )
    factor_weights = _weights(weights)
    rows: list[dict[str, Any]] = []
    for grain in grains:
        start, end = _bounds(grain, endpoint)
        scopes: list[tuple[str, str | None, pl.DataFrame]] = [("market", None, normalized)]
        if "sector" in normalized.columns:
            for sector_name in sorted(
                str(value)
                for value in normalized.get_column("sector").drop_nulls().unique().to_list()
            ):
                scopes.append(
                    ("sector", sector_name, normalized.filter(pl.col("sector") == sector_name))
                )
        for scope, sector, scoped in scopes:
            aggregate = _aggregate(scoped, start, end)
            history: dict[str, list[float | None]] = {name: [] for name in _RATIO_COLUMNS}
            history_end = start - timedelta(days=1)
            # Build a strictly-before history at the natural grain.  Missing
            # windows are retained as null and therefore do not affect ranks.
            cursor = history_end
            while True:
                prior_start, prior_end = _bounds(grain, cursor)
                if prior_end > history_end:
                    cursor = prior_start - timedelta(days=1)
                    continue
                prior = _aggregate(
                    scoped.filter(
                        pl.col("knowledge_at").is_null()
                        | (pl.col("knowledge_at") <= us_equity_session_close(prior_end))
                    ),
                    prior_start,
                    prior_end,
                )
                for name in _RATIO_COLUMNS:
                    history[name].append(prior[name])
                if prior_start == date.min or (history_end - prior_start).days > 3660:
                    break
                cursor = prior_start - timedelta(days=1)
                if cursor < date(1900, 1, 1):
                    break
            percentiles = {
                f"{name}_percentile": _percentile(aggregate[name], history[name])
                for name in _RATIO_COLUMNS
            }
            score_parts = [percentiles[f"{name}_percentile"] for name in _RATIO_COLUMNS]
            non_null_scores = [float(value) for value in score_parts if value is not None]
            composite = None
            if len(non_null_scores) == len(_WEIGHT_KEYS):
                composite = sum(
                    float(value) * factor_weights[key]
                    for value, key in zip(non_null_scores, _WEIGHT_KEYS, strict=True)
                )
            else:
                aggregate["quality_reasons"].append("MISSING_FACTOR_FOR_COMPOSITE")
            rows.append(
                {
                    "as_of": endpoint,
                    "grain": grain,
                    "period": grain,
                    "period_start": start,
                    "period_end": end,
                    "scope": scope,
                    "sector": sector,
                    **aggregate,
                    **percentiles,
                    "composite_score": composite,
                    "market_pulse_score": composite,
                    "quality_status": "PASS" if not aggregate["quality_reasons"] else "WARN",
                    "quality_reasons": sorted(set(aggregate["quality_reasons"])),
                }
            )
    return (
        pl.DataFrame(rows)
        if rows
        else pl.DataFrame(
            schema={
                "as_of": pl.Date,
                "grain": pl.String,
                "period": pl.String,
                "period_start": pl.Date,
                "period_end": pl.Date,
                "scope": pl.String,
                "sector": pl.String,
            }
        )
    )


build_market_pulse = market_pulse
compute_market_pulse = market_pulse
market_pulse_features = market_pulse


__all__ = [
    "market_pulse",
    "build_market_pulse",
    "compute_market_pulse",
    "market_pulse_features",
]
