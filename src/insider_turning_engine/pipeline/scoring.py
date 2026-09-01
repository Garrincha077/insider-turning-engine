"""Pure point-in-time assembly of daily company scoring outputs."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any

from insider_turning_engine.domain.time import us_equity_session_close
from insider_turning_engine.features.cluster import cluster_features
from insider_turning_engine.features.conviction import conviction_features
from insider_turning_engine.features.cost_basis import cost_basis_reclaim_facts
from insider_turning_engine.features.divergence import divergence_features
from insider_turning_engine.features.opportunistic import opportunistic_features
from insider_turning_engine.features.technical import (
    base_structure_score,
    cost_basis_reclaim_score,
    mansfield_turn_score,
    ordinary_rs_turn_score,
    volume_accumulation_score,
)
from insider_turning_engine.notifications import evaluate_alert_rules
from insider_turning_engine.scoring import CompanyState, ScoreEngine, StateMachine
from insider_turning_engine.scoring.components import aggregate_company_insider_components


class DailyScoringError(ValueError):
    """Raised when supplied scoring context breaches a PIT boundary."""


@dataclass(frozen=True, slots=True)
class DailyScoringResult:
    components: tuple[Mapping[str, Any], ...]
    signals: tuple[Mapping[str, Any], ...]
    states: tuple[Mapping[str, Any], ...]
    alerts: tuple[Mapping[str, Any], ...]

    def as_mapping(self) -> dict[str, Any]:
        return {
            "components": [_json_value(item) for item in self.components],
            "signals": [_json_value(item) for item in self.signals],
            "states": [_json_value(item) for item in self.states],
            "alerts": [_json_value(item) for item in self.alerts],
        }


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _as_of(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise DailyScoringError("as_of must be timezone-aware")
        return value.astimezone(UTC)
    return us_equity_session_close(value)


def _mapping_rows(value: Iterable[Any]) -> tuple[Any, ...]:
    return tuple(value)


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
        camel = name.split("_")[0] + "".join(part.title() for part in name.split("_")[1:])
        return value.get(camel, default)
    return getattr(value, name, default)


def _nested(value: Any, group: str, name: str, default: Any = None) -> Any:
    return _get(_get(value, group, {}), name, default)


def _stamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise DailyScoringError("knowledge timestamps must be ISO timestamps") from exc
    if parsed.tzinfo is None:
        raise DailyScoringError("knowledge timestamps must be timezone-aware")
    return parsed.astimezone(UTC)


def _issuer(row: Any) -> str:
    value = _nested(row, "issuer", "cik", _get(row, "issuer_cik"))
    return str(value).zfill(10) if value not in {None, ""} else ""


def _transaction_date(row: Any) -> date | None:
    value = _nested(row, "transaction", "transaction_date", _get(row, "transaction_date"))
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise DailyScoringError("transaction_date must be an ISO date") from exc


def _flat_row(row: Any) -> dict[str, Any]:
    transaction = _get(row, "transaction", row)
    timestamps = _get(row, "timestamps", row)
    lifecycle = _get(row, "lifecycle", row)
    security = _get(row, "security", row)
    owner = _get(row, "reporting_owner", row)
    return {
        "issuer_cik": _issuer(row),
        "owner_cik": (
            str(owner_cik).zfill(10)
            if (owner_cik := _get(owner, "cik", _get(row, "owner_cik", "")))
            not in {None, ""}
            else ""
        ),
        "transaction_date": _transaction_date(row),
        "knowledge_at": _get(timestamps, "knowledge_at", _get(row, "knowledge_at")),
        "accepted_at": _get(timestamps, "accepted_at", _get(row, "accepted_at")),
        "code": _get(transaction, "code", _get(row, "code", "")),
        "acquired_disposed": _get(
            transaction, "acquired_disposed", _get(row, "acquired_disposed", "")
        ),
        "table_type": _get(security, "table_type", _get(row, "table_type", "NON_DERIVATIVE")),
        "classification": _get(transaction, "classification", _get(row, "classification")),
        "economic_classification": _get(
            transaction, "economic_classification", _get(row, "economic_classification")
        ),
        "value_usd": _get(transaction, "value", _get(row, "value_usd", _get(row, "value"))),
        "shares": _get(transaction, "shares", _get(row, "shares")),
        "price_per_share": _get(
            transaction, "price_per_share", _get(row, "price_per_share", _get(row, "price"))
        ),
        "post_transaction_shares": _get(
            transaction, "post_transaction_shares", _get(row, "post_transaction_shares")
        ),
        "rule_10b5_1": _get(transaction, "rule_10b51", _get(row, "rule_10b5_1")),
        "lifecycle_status": _get(lifecycle, "status", _get(row, "lifecycle_status", "ACTIVE")),
        "valid_from": _get(lifecycle, "valid_from", _get(row, "valid_from")),
        "valid_to": _get(lifecycle, "valid_to", _get(row, "valid_to")),
        "relationship": _get(row, "relationship", {}),
    }


def _assert_pit(rows: Iterable[Any], *, as_of: datetime, label: str) -> None:
    for index, row in enumerate(rows):
        raw_known = _nested(
            row,
            "timestamps",
            "knowledge_at",
            _get(row, "knowledge_at", _get(row, "accepted_at")),
        )
        known = _stamp(raw_known)
        if known is not None and known > as_of:
            raise DailyScoringError(f"{label} row {index} knowledge_at later than as_of")
        event = _transaction_date(row)
        if event is not None and event > as_of.date():
            raise DailyScoringError(f"{label} row {index} transaction_date later than as_of")


def _context_by_issuer(
    rows: Iterable[Mapping[str, Any]], ticker_mapping: Mapping[str, Any], as_of: datetime
) -> dict[str, dict[str, Any]]:
    inverse: dict[str, str] = {}
    for cik, raw_ticker in ticker_mapping.items():
        if isinstance(raw_ticker, Mapping):
            raw_ticker = raw_ticker.get("ticker", raw_ticker.get("symbol"))
        ticker = str(raw_ticker or "").strip().upper()
        if ticker:
            inverse[ticker] = str(cik).zfill(10)
    selected: dict[str, tuple[str, str, str, dict[str, Any]]] = {}
    for index, raw in enumerate(rows):
        item = dict(raw)
        known = _stamp(item.get("knowledge_at", item.get("available_at", item.get("accepted_at"))))
        if known is not None and known > as_of:
            raise DailyScoringError(f"market context row {index} knowledge_at later than as_of")
        event = item.get("date", item.get("as_of"))
        if event is not None and date.fromisoformat(str(event)[:10]) > as_of.date():
            raise DailyScoringError(f"market context row {index} date later than as_of")
        raw_issuer = item.get("issuer_cik", item.get("cik"))
        if raw_issuer is None:
            raw_issuer = inverse.get(str(item.get("ticker", item.get("symbol", ""))).upper())
        if raw_issuer is None:
            continue
        issuer = str(raw_issuer).zfill(10)
        event_key = str(item.get("date", item.get("as_of", "")))
        known_key = known.isoformat() if known is not None else ""
        stable_key = json.dumps(item, sort_keys=True, default=str, separators=(",", ":"))
        candidate = (event_key, known_key, stable_key, {"issuer_cik": issuer, **item})
        if issuer not in selected or candidate[:3] > selected[issuer][:3]:
            selected[issuer] = candidate
    return {issuer: candidate[3] for issuer, candidate in selected.items()}


def _frame_by_key(frame: Any, key: str) -> dict[str, dict[str, Any]]:
    return {str(row[key]): dict(row) for row in frame.to_dicts() if row.get(key) is not None}


def _ticker(mapping: Mapping[str, Any], issuer: str) -> str | None:
    raw = mapping.get(issuer, mapping.get(str(int(issuer)) if issuer.isdigit() else issuer))
    if isinstance(raw, Mapping):
        raw = raw.get("ticker", raw.get("symbol"))
    value = str(raw or "").strip().upper()
    return value or None


def _prior(value: Mapping[str, Any], issuer: str) -> tuple[CompanyState, int]:
    raw = value.get(issuer, value.get(str(int(issuer)) if issuer.isdigit() else issuer, {}))
    if isinstance(raw, Mapping):
        state = raw.get("state", CompanyState.FALLING.value)
        failures = raw.get("failed_evaluations", 0)
    else:
        state, failures = raw or CompanyState.FALLING.value, 0
    return CompanyState(state), int(failures)


def _stale(
    issuer: str,
    ticker: str | None,
    previous: CompanyState,
    reasons: Iterable[str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    codes = tuple(sorted({"STALE_DATA_HOLD", *(str(reason) for reason in reasons)}))
    component = {"issuer_cik": issuer, "ticker": ticker, "components": None, "reason_codes": codes}
    signal = {
        "issuer_cik": issuer,
        "ticker": ticker,
        "total_score": None,
        "state": previous.value,
        "previous_state": previous.value,
        "reason_codes": codes,
    }
    state = {
        "issuer_cik": issuer,
        "state": previous.value,
        "previous_state": previous.value,
        "reason_codes": codes,
    }
    return component, signal, state


def _required_number(value: float | None) -> float:
    """Narrow a value only after the complete-component guard."""

    if value is None:
        raise DailyScoringError("missing required scoring component")
    return float(value)


def assemble_daily_scores(
    effective_rows: Iterable[Any],
    market_context_rows: Iterable[Mapping[str, Any]],
    ticker_mapping: Mapping[str, Any],
    prior_state: Mapping[str, Any],
    *,
    as_of: date | datetime,
    run_id: str,
    quality: Mapping[str, Any] | None = None,
) -> DailyScoringResult:
    """Assemble deterministic company scores from effective point-in-time inputs."""

    cutoff = _as_of(as_of)
    rows = _mapping_rows(effective_rows)
    context_rows = tuple(market_context_rows)
    _assert_pit(rows, as_of=cutoff, label="canonical")
    context = _context_by_issuer(context_rows, ticker_mapping, cutoff)
    flat = [_flat_row(row) for row in rows]
    issuers = tuple(sorted({row["issuer_cik"] for row in flat if row["issuer_cik"]}))
    if not run_id:
        raise DailyScoringError("run_id must be non-empty")

    try:
        cluster = cluster_features(rows, as_of=cutoff)
        opportunistic = opportunistic_features(rows, as_of=cutoff)
        conviction = conviction_features(rows, as_of=cutoff, cluster_context=cluster)
        cluster_by_row = _frame_by_key(cluster, "row_id")
        opportunistic_by_row = _frame_by_key(opportunistic, "row_id")
        conviction_by_row = _frame_by_key(conviction, "row_id")
        enriched: list[dict[str, Any]] = []
        for index, row in enumerate(flat):
            cluster_row = cluster_by_row.get(str(index), {})
            opportunistic_row = opportunistic_by_row.get(str(index), {})
            conviction_row = conviction_by_row.get(str(index), {})
            enriched.append(
                {
                    **row,
                    "cluster_score": cluster_row.get("cluster_score"),
                    "opportunistic_score": opportunistic_row.get("opportunistic_score"),
                    "conviction_score": conviction_row.get("conviction_score"),
                    "strong_cluster": cluster_row.get("strong_cluster", False),
                    "first_buy": opportunistic_row.get("first_buy_3y", False),
                    "largest_buy": "HISTORICAL_LARGEST_BUY"
                    in conviction_row.get("reason_codes", ()),
                }
            )
        cluster_context = [dict(row) for row in cluster.to_dicts()]
        divergence = divergence_features(
            rows,
            as_of=cutoff,
            price_context=context,
            cluster_context=cluster_context,
        )
        divergence_by_issuer = _frame_by_key(divergence, "issuer_cik")
        prices = {
            issuer: item.get("close", item.get("adj_close", item.get("price")))
            for issuer, item in context.items()
        }
        cost = cost_basis_reclaim_facts(rows, as_of=cutoff, market=prices)
        cost_by_issuer = _frame_by_key(cost, "issuer_cik")
    except ValueError as exc:
        raise DailyScoringError(str(exc)) from exc

    engine = ScoreEngine(as_of=cutoff, run_id=run_id)
    machine = StateMachine()
    components_output: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    for issuer in issuers:
        ticker = _ticker(ticker_mapping, issuer)
        previous, failures = _prior(prior_state, issuer)
        price = context.get(issuer)
        if ticker is None or price is None:
            component, signal, state = _stale(
                issuer, ticker, previous, ("MISSING_PIT_TICKER_OR_MARKET_CONTEXT",)
            )
            components_output.append(component)
            signals.append(signal)
            states.append(state)
            continue
        company = aggregate_company_insider_components(
            [row for row in enriched if row["issuer_cik"] == issuer], as_of=cutoff
        )
        divergence_row = divergence_by_issuer.get(issuer, {})
        divergence_score = divergence_row.get("divergence_score")
        cost_row = cost_by_issuer.get(issuer, {})
        cost_score = cost_basis_reclaim_score(
            current_price=cost_row.get("current_price"),
            cost_basis_90d=cost_row.get("cost_basis_90d"),
            as_of=cutoff,
        )
        ordinary_level = price.get(
            "ordinary_rs_3m",
            price.get("current_percentile", price.get("ordinary_rs_percentile")),
        )
        ordinary_slope_percentile = price.get(
            "ordinary_rs_slope_percentile",
            price.get("slope_percentile"),
        )
        market_level = price.get("mansfield_market", price.get("level"))
        market_slope_percentile = price.get(
            "mansfield_market_slope_percentile",
            price.get("mansfield_slope_percentile"),
        )
        sector_level = price.get("mansfield_sector", market_level)
        sector_slope_percentile = price.get(
            "mansfield_sector_slope_percentile",
            market_slope_percentile,
        )
        technical = {
            "base": base_structure_score(facts=price),
            "ordinary_rs": ordinary_rs_turn_score(
                ordinary_level,
                ordinary_slope_percentile,
            ),
            "mansfield_market": mansfield_turn_score(
                market_level,
                market_slope_percentile,
            ),
            "mansfield_sector": mansfield_turn_score(
                sector_level,
                sector_slope_percentile,
            ),
            "volume": volume_accumulation_score(
                price.get("signed_volume_ratio_20d", price.get("signed_volume_ratio")),
                price.get("signed_volume_prior_percentile", price.get("prior_percentile")),
            ),
            "cost_basis_reclaim": cost_score,
        }
        required = {
            **company.as_mapping(),
            "divergence": divergence_score,
            **{name: value.score for name, value in technical.items()},
        }
        missing = sorted(name for name, value in required.items() if value is None)
        if missing:
            component, signal, state = _stale(
                issuer,
                ticker,
                previous,
                (f"MISSING_{name.upper()}" for name in missing),
            )
            components_output.append(component)
            signals.append(signal)
            states.append(state)
            continue
        try:
            company_components = company.as_mapping()
            company_score = engine.company_insider(
                conviction=_required_number(company_components["conviction"]),
                cluster=_required_number(company_components["cluster"]),
                opportunistic=_required_number(company_components["opportunistic"]),
                net_buying_absence_sales=_required_number(
                    company_components["net_buying_absence_sales"]
                ),
            )
            divergence_result = engine.divergence(
                price_weakness=_required_number(divergence_row.get("price_weakness")),
                insider_activity_percentile=_required_number(
                    divergence_row.get("insider_activity_percentile")
                ),
                acceleration_cluster=_required_number(divergence_row.get("acceleration_cluster")),
                absence_relevant_sales=_required_number(
                    divergence_row.get("absence_relevant_sales")
                ),
            )
            turn = engine.turn(
                base_structure=_required_number(technical["base"].score),
                ordinary_rs_turn=_required_number(technical["ordinary_rs"].score),
                mansfield_market=_required_number(technical["mansfield_market"].score),
                mansfield_sector=_required_number(technical["mansfield_sector"].score),
                volume_accumulation=_required_number(technical["volume"].score),
                cost_basis_reclaim=_required_number(technical["cost_basis_reclaim"].score),
            )
            mansfield_total = (
                0.60 * _required_number(technical["mansfield_market"].score)
                + 0.40 * _required_number(technical["mansfield_sector"].score)
            )
            total = engine.total(
                divergence=divergence_result.score,
                conviction=company_score.components["conviction"],
                cluster=company_score.components["cluster"],
                opportunistic=company_score.components["opportunistic"],
                base=_required_number(technical["base"].score),
                ordinary_rs=_required_number(technical["ordinary_rs"].score),
                mansfield_rs=mansfield_total,
                volume=_required_number(technical["volume"].score),
            )
        except (TypeError, ValueError) as exc:
            raise DailyScoringError(f"invalid complete component set for {issuer}: {exc}") from exc
        qualified_dates = [
            row["transaction_date"]
            for row in enriched
            if row["issuer_cik"] == issuer
            and str(row["code"]).upper() == "P"
            and str(row["table_type"]).upper() == "NON_DERIVATIVE"
            and isinstance(row["transaction_date"], date)
        ]
        qualified_buy_age_days = (
            (cutoff.date() - max(qualified_dates)).days if qualified_dates else None
        )
        facts = {
            **price,
            "company_insider_score": company_score.score,
            "divergence_score": divergence_result.score,
            "turn_score": turn.score,
            "total_score": total.score,
            "qualified_buy_age_days": qualified_buy_age_days,
            "cost_basis_reclaim": _required_number(cost_score.score) >= 50,
        }
        evaluated = machine.evaluate(previous, facts, consecutive_failed_evaluations=failures)
        component_reasons = tuple(
            dict.fromkeys(
                (
                    *company_score.reason_codes,
                    *divergence_result.reason_codes,
                    *turn.reason_codes,
                )
            )
        )
        latest_purchase = max(
            (
                row
                for row in enriched
                if row["issuer_cik"] == issuer
                and str(row["code"]).upper() == "P"
                and isinstance(row["transaction_date"], date)
            ),
            key=lambda row: (row["transaction_date"], row["owner_cik"]),
            default={},
        )
        flags = tuple(
            name
            for name in ("strong_cluster", "first_buy", "largest_buy")
            if latest_purchase.get(name) is True
        )
        component = {
            "issuer_cik": issuer,
            "ticker": ticker,
            "company_insider": _json_value(asdict(company_score)),
            "divergence": _json_value(asdict(divergence_result)),
            "turn": _json_value(asdict(turn)),
            "total": _json_value(asdict(total)),
            "reason_codes": component_reasons,
        }
        signal = {
            "issuer_cik": issuer,
            "ticker": ticker,
            "total_score": total.score,
            "company_insider_score": company_score.score,
            "divergence_score": divergence_result.score,
            "turn_score": turn.score,
            "state": evaluated.state.value,
            "previous_state": evaluated.previous_state.value,
            "transition_to": evaluated.state.value if evaluated.transitioned else None,
            "reason_codes": tuple(
                dict.fromkeys((*evaluated.reason_codes, *component_reasons))
            ),
            "transaction_value_usd": latest_purchase.get("value_usd"),
            "conviction_score": latest_purchase.get("conviction_score"),
            "flags": flags,
            "no_new_52_week_low_20_sessions": price.get(
                "no_new_52_week_low_20_sessions"
            ),
            "ordinary_rs_3m_slope_4w": price.get("ordinary_rs_3m_slope_4w"),
            "mansfield_market_slope_4w": price.get("mansfield_market_slope_4w"),
            "score_version": total.score_version,
            "methodology_hash": total.methodology_hash,
            "config_hash": total.score_config_hash,
            "as_of": total.as_of,
            "run_id": total.run_id,
            "score_provenance": _json_value(asdict(total)),
        }
        state = {
            "issuer_cik": issuer,
            "state": evaluated.state.value,
            "previous_state": evaluated.previous_state.value,
            "failed_evaluations": evaluated.failed_evaluations,
            "reason_codes": evaluated.reason_codes,
        }
        snapshot_id = f"{run_id}:{issuer}:{cutoff.isoformat()}"
        candidate_rows = evaluate_alert_rules(
            signal,
            issuer_cik=issuer,
            trigger_snapshot_id=snapshot_id,
            quality=quality,
            now=cutoff,
        )
        components_output.append(component)
        signals.append(signal)
        states.append(state)
        alerts.extend(
            {
                **_json_value(asdict(candidate)),
                "score_version": total.score_version,
                "methodology_hash": total.methodology_hash,
                "config_hash": total.score_config_hash,
                "as_of": total.as_of,
                "run_id": total.run_id,
            }
            for candidate in candidate_rows
        )
    signals.sort(
        key=lambda item: (
            item["total_score"] is None,
            -(item["total_score"] or 0.0),
            item["issuer_cik"],
        )
    )
    order = {item["issuer_cik"]: index for index, item in enumerate(signals)}
    components_output.sort(key=lambda item: order[item["issuer_cik"]])
    states.sort(key=lambda item: order[item["issuer_cik"]])
    alerts.sort(
        key=lambda item: (item["issuer_cik"], item["alert_type"], item["trigger_snapshot_id"])
    )
    return DailyScoringResult(
        tuple(components_output), tuple(signals), tuple(states), tuple(alerts)
    )


__all__ = ["DailyScoringError", "DailyScoringResult", "assemble_daily_scores"]
