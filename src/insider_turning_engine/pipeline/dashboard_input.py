"""Project one daily run into the compact static-dashboard input contract."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from insider_turning_engine.domain.models import CanonicalTransaction
from insider_turning_engine.features.cluster import cluster_features
from insider_turning_engine.features.conviction import conviction_features
from insider_turning_engine.features.cost_basis import cost_basis_reclaim_facts
from insider_turning_engine.features.pulse import market_pulse


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def _identity_details(
    rows: Iterable[Mapping[str, Any]],
    ticker_by_cik: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {}
    for raw in rows:
        cik = str(raw.get("cik", raw.get("issuer_cik", ""))).zfill(10)
        ticker = ticker_by_cik.get(cik)
        if ticker is None or str(raw.get("ticker", raw.get("symbol", ""))).upper() != ticker:
            continue
        candidate = {
            "name": str(raw.get("name", raw.get("issuer_name", ticker))).strip() or ticker,
            "sector": raw.get("sector", raw.get("sector_etf", raw.get("sectorEtf"))),
        }
        stable = (str(raw.get("knowledge_at", "")), str(candidate))
        current = details.get(cik)
        if current is None or stable > current["_stable"]:
            details[cik] = {**candidate, "_stable": stable}
    return details


def _pulse_rows(
    records: Sequence[CanonicalTransaction],
    *,
    as_of: datetime,
    sector_by_issuer: Mapping[str, str],
) -> list[dict[str, Any]]:
    if not records:
        return []
    cluster = cluster_features(records, as_of=as_of)
    conviction = conviction_features(records, as_of=as_of, cluster_context=cluster)
    conviction_by_row = {
        str(row["row_id"]): row.get("conviction_score") for row in conviction.to_dicts()
    }
    enriched: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        row = record.canonical_dump()
        score = conviction_by_row.get(str(index))
        if score is not None:
            row["conviction_score"] = score
        enriched.append(row)
    return market_pulse(
        enriched,
        as_of=as_of,
        sector_by_issuer=sector_by_issuer,
    ).to_dicts()


def _role(record: CanonicalTransaction) -> str:
    relationship = record.relationship
    title = (relationship.officer_title or "").strip()
    if title:
        return title
    if relationship.is_director:
        return "Director"
    if relationship.is_officer:
        return "Officer"
    if relationship.is_ten_percent_owner:
        return "10% owner"
    return "Other"


def _filings(
    records: Sequence[CanonicalTransaction],
    ticker_by_cik: Mapping[str, str],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for record in records:
        code = record.transaction.code.upper()
        if code not in {"P", "S"} or record.transaction.value is None:
            continue
        ticker = ticker_by_cik.get(record.issuer.cik)
        accepted = record.timestamps.accepted_at
        if ticker is None or accepted is None:
            continue
        side = "BUY" if code == "P" else "SELL"
        key = (
            record.source.accession_number,
            record.reporting_owner.cik,
            ticker,
            side,
        )
        current = grouped.setdefault(
            key,
            {
                "ticker": ticker,
                "owner": record.reporting_owner.name,
                "role": _role(record),
                "side": side,
                "value": 0.0,
                "filedAt": accepted.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                "accession": record.source.accession_number,
                "sourceReferences": {"url": record.source.source_url},
            },
        )
        current["value"] += float(record.transaction.value)
    return sorted(
        grouped.values(),
        key=lambda row: (str(row["filedAt"]), str(row["accession"])),
        reverse=True,
    )


def build_dashboard_input(
    *,
    run_id: str,
    as_of: datetime,
    records: Sequence[CanonicalTransaction],
    identity_rows: Sequence[Mapping[str, Any]],
    ticker_by_cik: Mapping[str, str],
    sector_by_ticker: Mapping[str, str],
    scoring_context: Sequence[Mapping[str, Any]],
    components: Sequence[Mapping[str, Any]],
    signals: Sequence[Mapping[str, Any]],
    quality: Mapping[str, Any],
    score_version: str,
) -> dict[str, Any]:
    """Return an exporter-ready, deterministic dashboard projection."""

    details = _identity_details(identity_rows, ticker_by_cik)
    context = {str(row.get("issuer_cik", "")).zfill(10): row for row in scoring_context}
    component_by_issuer = {
        str(row.get("issuer_cik", "")).zfill(10): row for row in components
    }
    prices = {
        issuer: _number(row.get("close", row.get("adj_close")))
        for issuer, row in context.items()
    }
    costs = cost_basis_reclaim_facts(records, as_of=as_of, market=prices)
    cost_by_issuer = {
        str(row["issuer_cik"]).zfill(10): row for row in costs.to_dicts()
    }
    candidates: list[dict[str, Any]] = []
    for signal in signals:
        total = _number(signal.get("total_score"))
        issuer = str(signal.get("issuer_cik", "")).zfill(10)
        ticker = ticker_by_cik.get(issuer)
        component = component_by_issuer.get(issuer, {})
        if total is None or ticker is None or not component:
            continue
        total_components = component.get("total", {}).get("components", {})
        market = context.get(issuer, {})
        identity = details.get(issuer, {})
        basis = cost_by_issuer.get(issuer, {})
        candidates.append(
            {
                "ticker": ticker,
                "issuerCik": issuer,
                "company": identity.get("name", ticker),
                "sector": identity.get("sector") or sector_by_ticker.get(ticker) or "Unmapped",
                "total": total,
                "insider": _number(signal.get("company_insider_score")),
                "divergence": _number(signal.get("divergence_score")),
                "turn": _number(signal.get("turn_score")),
                "cluster": _number(total_components.get("cluster")),
                "marketRs": _number(market.get("mansfield_market")),
                "sectorRs": _number(market.get("mansfield_sector")),
                "insiderCost": _number(basis.get("cost_basis_90d")),
                "currentPrice": _number(market.get("close", market.get("adj_close"))),
                "state": signal.get("state", "FALLING"),
                "reasons": list(signal.get("reason_codes", ()))[:6],
                "sourceReferences": {
                    "runId": run_id,
                    "methodologyHash": signal.get("methodology_hash"),
                },
            }
        )
    candidates.sort(key=lambda row: (-float(row["total"]), str(row["issuerCik"])))

    sector_by_issuer = {
        cik: sector_by_ticker[ticker]
        for cik, ticker in ticker_by_cik.items()
        if ticker in sector_by_ticker
    }
    pulse = _pulse_rows(records, as_of=as_of, sector_by_issuer=sector_by_issuer)
    weekly = [row for row in pulse if row.get("grain") == "weekly"]
    market_row = next((row for row in weekly if row.get("scope") == "market"), {})
    technology = next(
        (row for row in weekly if row.get("scope") == "sector" and row.get("sector") == "XLK"),
        {},
    )
    financials = next(
        (row for row in weekly if row.get("scope") == "sector" and row.get("sector") == "XLF"),
        {},
    )
    pulse_score = _number(market_row.get("market_pulse_score"))
    pulse_history = (
        [
            {
                "date": as_of.date().isoformat(),
                "market": pulse_score,
                "technology": _number(technology.get("market_pulse_score")),
                "financials": _number(financials.get("market_pulse_score")),
            }
        ]
        if weekly
        else []
    )
    accepted = [record.timestamps.accepted_at for record in records]
    sec_watermark = max((item for item in accepted if item is not None), default=None)
    market_dates = [row.get("date") for row in scoring_context if row.get("date") is not None]
    market_watermark = max((str(item)[:10] for item in market_dates), default=None)
    return {
        "schemaVersion": "1.0.0",
        "scoreVersion": score_version,
        "generatedAt": as_of.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "status": (
            "VALIDATED"
            if quality.get("disposition") == "PASS"
            else "STALE"
            if not quality.get("benchmarkFresh", False)
            else "EXPERIMENTAL"
        ),
        "marketPulse": pulse_score,
        "pulsePercentile": pulse_score,
        "pulseHistory": pulse_history,
        "candidates": candidates,
        "filings": _filings(records, ticker_by_cik),
        "backtest": [],
        "companySeries": [],
        "quality": dict(quality),
        "watermarks": {
            "secAcceptedThrough": (
                sec_watermark.astimezone(UTC).isoformat().replace("+00:00", "Z")
                if sec_watermark is not None
                else None
            ),
            "marketSessionThrough": market_watermark,
            "fundamentalsAvailableThrough": None,
        },
    }


__all__ = ["build_dashboard_input"]
