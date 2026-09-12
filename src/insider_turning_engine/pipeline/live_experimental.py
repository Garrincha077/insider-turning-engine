"""Build a real-data, explicitly unvalidated static dashboard snapshot.

This path exists to keep the public UI useful while scoring.v1 remains a
CANDIDATE methodology. It reuses canonical parsers, feature calculators and
the score engine, but never creates alerts or a validation/backtest claim.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

from insider_turning_engine.domain.models import CanonicalTransaction, TableType
from insider_turning_engine.export import export_dashboard
from insider_turning_engine.features.price import price_features
from insider_turning_engine.features.rs import relative_strength_features
from insider_turning_engine.ingestion.market import (
    DailyBar,
    RedundantEODProvider,
    StooqMarketDataProvider,
    YahooChartProvider,
)
from insider_turning_engine.ingestion.sec import (
    SECDailyIndexSource,
    parse_sec_filing,
)
from insider_turning_engine.ingestion.sec.historical import validate_sec_user_agent
from insider_turning_engine.ingestion.sec.identity_store import ReleaseIdentityStore
from insider_turning_engine.normalization.amendments import resolve_amendments
from insider_turning_engine.notifications import build_settings_status, load_notification_policy
from insider_turning_engine.pipeline.daily import _technical_contexts
from insider_turning_engine.pipeline.dashboard_input import build_dashboard_input
from insider_turning_engine.pipeline.identity_observations import acquire_identity_observations
from insider_turning_engine.pipeline.live_inputs import _identity_candidates
from insider_turning_engine.pipeline.scoring import assemble_daily_scores

_COMMON = re.compile(r"\b(?:common(?: stock| shares?)?|ordinary shares?)\b", re.IGNORECASE)
_SECTORS = {
    "XLB": "Materials", "XLC": "Communication services", "XLE": "Energy",
    "XLF": "Financials", "XLI": "Industrials", "XLK": "Technology", "XLP": "Consumer staples",
    "XLRE": "Real estate", "XLU": "Utilities", "XLV": "Healthcare", "XLY": "Consumer discretionary",
}


@dataclass(frozen=True, slots=True)
class LiveExperimentalResult:
    output_dir: Path
    run_id: str
    filing_days: tuple[date, ...]
    canonical_rows: int
    candidates: int
    filings: int
    market_coverage: float
    issues: tuple[str, ...]


def _business_days(through: date, count: int) -> tuple[date, ...]:
    if count < 1 or count > 20:
        raise ValueError("lookback business days must be between 1 and 20")
    days: list[date] = []
    current = through
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current -= timedelta(days=1)
    return tuple(sorted(days))


def _measurement(numerator: int, denominator: int, threshold: float) -> dict[str, Any]:
    rate = numerator / denominator if denominator else None
    result = (
        "PASS"
        if rate is not None and rate >= threshold
        else ("FAIL" if rate is not None else "NOT_EVALUATED")
    )
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": round(rate, 12) if rate is not None else None,
        "threshold": threshold,
        "result": result,
    }


def _qualifying_purchase(record: CanonicalTransaction, as_of: datetime) -> bool:
    return (
        record.timestamps.accepted_at is not None
        and record.timestamps.accepted_at <= as_of
        and record.timestamps.knowledge_at <= as_of
        and record.transaction.transaction_date >= as_of.date() - timedelta(days=365)
        and record.transaction.transaction_date <= as_of.date()
        and record.transaction.code == "P"
        and record.transaction.acquired_disposed == "A"
        and record.security.table_type is TableType.NON_DERIVATIVE
        and record.transaction.shares is not None
        and record.transaction.shares > 0
        and record.transaction.price_per_share is not None
        and record.transaction.price_per_share > 0
        and record.transaction.value is not None
        and _COMMON.search(record.security.title) is not None
    )


def _select_issuers(
    records: Sequence[CanonicalTransaction],
    identity_rows: Sequence[Mapping[str, Any]],
    *,
    as_of: datetime,
    max_symbols: int,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    if max_symbols < 0:
        raise ValueError("max_symbols must be zero (all) or a positive integer")
    titles = {record.issuer.cik: record.security.title for record in records
              if _qualifying_purchase(record, as_of)}
    current = _identity_candidates(identity_rows, as_of=as_of, common_stock_titles=titles)
    dollars: defaultdict[str, float] = defaultdict(float)
    tickers: dict[str, str] = {}
    for record in records:
        if not _qualifying_purchase(record, as_of):
            continue
        identity = current.get(record.issuer.cik)
        if identity is None:
            continue
        dollars[record.issuer.cik] += float(record.transaction.value or 0)
        tickers[record.issuer.cik] = identity["ticker"]
    selected_ciks = sorted(dollars, key=lambda cik: (-dollars[cik], cik))
    if max_symbols:
        selected_ciks = selected_ciks[:max_symbols]
    ticker_by_cik = {cik: tickers[cik] for cik in selected_ciks}
    selected_identities: list[dict[str, Any]] = []
    for cik in ticker_by_cik:
        row = dict(current[cik])
        etf = row["sector_etf"]
        row["sector"] = f"{_SECTORS[etf]} / {etf} (SIC)" if etf in _SECTORS else "Unmapped"
        selected_identities.append(row)
    return ticker_by_cik, selected_identities


def _fetch_sec_records(
    *,
    days: Sequence[date],
    user_agent: str,
    cache_dir: Path,
    run_id: str,
    now: datetime,
) -> tuple[list[CanonicalTransaction], int, int, int, int, datetime]:
    source = SECDailyIndexSource(user_agent, cache_dir=cache_dir)
    records: list[CanonicalTransaction] = []
    quarantines = 0
    failures = 0
    try:
        for day in days:
            try:
                page = source.fetch_day(day)
            except RuntimeError:
                failures += 1
                continue
            quarantines += len(page.quarantines)
            for raw in page.records:
                if raw.payload is None:
                    failures += 1
                    continue
                parsed = parse_sec_filing(
                    raw.payload,
                    {
                        "accession_number": raw.accession_number,
                        "source_url": raw.source_url,
                        "accepted_at": raw.accepted_at,
                        "observed_at": raw.retrieved_at,
                        "run_id": run_id,
                    },
                )
                records.extend(parsed.records)
                quarantines += len(parsed.quarantines)
    finally:
        source.close()
    # A live materialization is known only after provider retrieval completes.
    # Use the batch's actual maximum knowledge time, never the invocation time.
    knowledge_cutoff = max(
        (record.timestamps.knowledge_at for record in records),
        default=now,
    )
    parsed_count = len(records)
    resolution = resolve_amendments(records, as_of=knowledge_cutoff)
    return (
        list(resolution.effective_records),
        parsed_count,
        quarantines,
        failures,
        len(resolution.quarantines),
        knowledge_cutoff,
    )


def _fetch_market(
    symbols: Iterable[str], *, cache_dir: Path
) -> tuple[dict[str, tuple[DailyBar, ...]], dict[str, str], dict[str, str], set[str]]:
    provider = RedundantEODProvider(
        (
            StooqMarketDataProvider(
                cache_dir=cache_dir,
                max_attempts=1,
                cache_ttl_seconds=86_400,
            ),
            YahooChartProvider(cache_dir=cache_dir),
        )
    )
    bars: dict[str, tuple[DailyBar, ...]] = {}
    failures: dict[str, str] = {}
    try:
        for symbol in sorted(set(symbols)):
            try:
                bars[symbol] = provider.fetch_daily(symbol)
            except (ValueError, RuntimeError, OSError) as exc:
                failures[symbol] = str(exc)[:300]
    finally:
        provider.close()
    return bars, failures, dict(provider.selected_provider), set(provider.cross_validated_symbols)


def _company_series(
    rs_frame: pl.DataFrame, candidates: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    costs = {str(row["ticker"]): row.get("insiderCost") for row in candidates}
    output: list[dict[str, Any]] = []
    if rs_frame.is_empty():
        return output
    for ticker, cost in sorted(costs.items()):
        rows = (
            rs_frame.filter(pl.col("symbol") == ticker)
            .sort("date")
            .tail(26)
            .select("date", "adj_close", "mansfield_market")
            .to_dicts()
        )
        for row in rows:
            price = row.get("adj_close")
            if price is None:
                continue
            output.append(
                {
                    "ticker": ticker,
                    "date": str(row["date"]),
                    "price": float(price),
                    "cost": float(cost) if cost is not None else None,
                    "mansfield": (
                        float(row["mansfield_market"])
                        if row.get("mansfield_market") is not None
                        else None
                    ),
                }
            )
    return output


def generate_live_experimental_dashboard(
    *,
    output_dir: str | Path,
    cache_dir: str | Path,
    user_agent: str,
    lookback_business_days: int = 5,
    max_symbols: int = 0,
    now: datetime | None = None,
    identity_repository: str | None = None,
    identity_target: str | None = None,
) -> LiveExperimentalResult:
    """Fetch real inputs and atomically publish one experimental snapshot."""

    point = (now or datetime.now(UTC)).astimezone(UTC)
    validated_user_agent = validate_sec_user_agent(user_agent)
    run_id = f"run_live_{point:%Y%m%dT%H%M%SZ}"
    root = Path(cache_dir)
    if bool(identity_repository) != bool(identity_target):
        raise ValueError("identity repository and full commit target must be supplied together")
    requested_days = _business_days(
        point.astimezone(ZoneInfo("America/New_York")).date() - timedelta(days=1),
        lookback_business_days,
    )
    discovery = SECDailyIndexSource(validated_user_agent)
    try:
        filing_days = discovery.discover_days(requested_days[0], requested_days[-1])
    finally:
        discovery.close()
    (
        records,
        sec_parsed,
        sec_quarantines,
        sec_failures,
        amendment_quarantines,
        point,
    ) = _fetch_sec_records(
        days=filing_days,
        user_agent=validated_user_agent,
        cache_dir=root / "sec",
        run_id=run_id,
        now=point,
    )
    if not records:
        raise RuntimeError("live SEC window produced no canonical ownership rows")

    active_ciks = sorted({record.issuer.cik for record in records
                          if _qualifying_purchase(record, point)})
    if not active_ciks:
        raise RuntimeError("live SEC window has no qualified purchases")
    store = (ReleaseIdentityStore(identity_repository, target=identity_target)
             if identity_repository and identity_target else None)
    previous_rows = store.latest() if store else None
    identity_root = root / "identity-observations" / run_id
    previous_path = root / f"{run_id}-prior-identities.json"
    if previous_rows is not None:
        previous_path.parent.mkdir(parents=True, exist_ok=True)
        previous_path.write_text(json.dumps(previous_rows, sort_keys=True), encoding="utf-8")
    identity_report = acquire_identity_observations(
        active_ciks, user_agent=validated_user_agent, run_id=run_id, output=identity_root,
        previous=previous_path if previous_rows is not None else None,
    )
    identity_history = json.loads((identity_root / "identities.json").read_text(encoding="utf-8"))
    identity_receipt = store.persist(identity_history) if store else None
    # This preview is a current materialization, NOT a historical daily-close
    # backtest. Never move current identity evidence back to the SEC filing day.
    point = max(point, datetime.fromisoformat(identity_report["observedThrough"]))
    ticker_by_cik, identity_rows = _select_issuers(
        records,
        identity_history,
        as_of=point,
        max_symbols=max_symbols,
    )
    if not ticker_by_cik:
        raise RuntimeError("live SEC window has no exchange-mapped common-stock purchases")

    requested_candidates = len(ticker_by_cik)
    sector_by_symbol = {row["ticker"]: row["sector_etf"] for row in identity_rows
                        if row["sector_etf"] in _SECTORS}
    benchmarks = {"SPY", *sector_by_symbol.values()}
    requested_symbols = {*ticker_by_cik.values(), *benchmarks}
    fetched_market, market_failures, market_sources, cross_validated = _fetch_market(
        requested_symbols, cache_dir=root / "market"
    )
    market = {
        symbol: tuple(
            bar
            for bar in rows
            if bar.available_at is not None and bar.available_at <= point
        )
        for symbol, rows in fetched_market.items()
    }
    market = {symbol: rows for symbol, rows in market.items() if rows}
    if not benchmarks <= market.keys():
        raise RuntimeError("required market/sector benchmark unavailable; live snapshot blocked")
    available_tickers = {symbol for symbol in ticker_by_cik.values() if symbol in market}
    coverage = _measurement(len(available_tickers), requested_candidates, 0.90)
    if coverage["result"] != "PASS":
        raise RuntimeError("live market coverage below 90%; previous snapshot preserved")
    ticker_by_cik = {
        cik: ticker for cik, ticker in ticker_by_cik.items() if ticker in available_tickers
    }
    identity_rows = [row for row in identity_rows if row["ticker"] in available_tickers]
    selected_records = [record for record in records if record.issuer.cik in ticker_by_cik]
    all_bars = [bar for rows in market.values() for bar in rows]
    price_frame = price_features(all_bars, as_of=point)
    rs_frame = relative_strength_features(
        all_bars,
        as_of=point,
        sector_by_symbol=sector_by_symbol,
        universe_symbols=tuple(ticker_by_cik.values()),
    )
    scoring_context = _technical_contexts(
        price_frame=price_frame,
        rs_frame=rs_frame,
        identity=ticker_by_cik,
        as_of=point,
    )
    scoring = assemble_daily_scores(
        selected_records,
        scoring_context,
        ticker_by_cik,
        {},
        as_of=point,
        run_id=run_id,
        quality={"quality_gate_passed": False},
    )

    parse_quality = _measurement(
        sec_parsed,
        sec_parsed + sec_quarantines + sec_failures,
        0.995,
    )
    latest_market = max(bar.date for symbol in available_tickers for bar in market[symbol])
    spy_latest = max(bar.date for bar in market["SPY"])
    spy_sessions = sorted({bar.date for bar in market["SPY"]})
    previous_session = spy_sessions[max(0, len(spy_sessions) - 2)]
    benchmark_fresh = (
        spy_latest >= latest_market and (point.date() - spy_latest).days <= 4
        and all(max(bar.date for bar in market[symbol]) >= previous_session
                for symbol in benchmarks)
    )
    if not benchmark_fresh:
        raise RuntimeError("stale market/sector benchmark; previous snapshot preserved")
    issues = {
        "BACKTEST_NOT_RUN",
        "CURRENT_TICKER_MAP_SURVIVORSHIP_BIAS",
        "LIVE_EXPERIMENTAL_ROLLING_WINDOW",
        "SCORING_METHODOLOGY_INCOMPLETE",
        "CURRENT_SIC_SECTOR_PROXY_V1_1",
        "PURCHASE_ACTIVE_WINDOW_SELECTION_BIAS",
    }
    if any(source == "yahoo-chart-experimental" for source in market_sources.values()):
        issues.add("YAHOO_MARKET_DATA_FALLBACK")
    if set(market_sources) != cross_validated:
        issues.add("MARKET_SINGLE_SOURCE_ONLY")
    if sec_quarantines:
        issues.add("SEC_QUARANTINE_ROWS_EXCLUDED")
    if amendment_quarantines:
        issues.add("ROLLING_WINDOW_AMENDMENT_PREDECESSOR_MISSING")
    if sec_failures:
        issues.add("SEC_FILING_DAY_FAILURE")
    if market_failures:
        issues.add("MARKET_SYMBOL_FAILURES")
    if identity_report["unresolvedIssuerCount"]:
        issues.add("UNRESOLVED_CURRENT_IDENTITIES_EXCLUDED")
    if len(sector_by_symbol) < requested_candidates:
        issues.add("UNMAPPED_SECTOR_NO_SCORE")
    if identity_receipt is None:
        issues.add("IDENTITY_HISTORY_LOCAL_ONLY")
    quality = {
        "disposition": "DEGRADED",
        "canonicalValid": True,
        "methodologyComplete": False,
        "benchmarkFresh": benchmark_fresh,
        "parseSuccess": parse_quality,
        "marketCoverage": coverage,
        "coreBranchCoverage": _measurement(0, 0, 0.85),
        "issues": sorted(issues),
    }
    dashboard = build_dashboard_input(
        run_id=run_id,
        as_of=point,
        records=selected_records,
        identity_rows=identity_rows,
        ticker_by_cik=ticker_by_cik,
        sector_by_ticker=sector_by_symbol,
        scoring_context=scoring_context,
        components=scoring.components,
        signals=scoring.signals,
        quality=quality,
        score_version="scoring.v1",
    )
    candidates = list(dashboard["candidates"])
    if not candidates:
        raise RuntimeError("live inputs produced no complete experimental score candidates")
    identity_by_ticker = {row["ticker"]: row for row in identity_rows}
    for candidate in candidates:
        candidate["reasons"] = list(
            dict.fromkeys(["LIVE_EXPERIMENTAL", "CURRENT_SIC_SECTOR_PROXY_V1_1",
                           *candidate["reasons"]])
        )[:6]
        identity = identity_by_ticker[candidate["ticker"]]
        candidate["sourceReferences"].update({
            "identityKnownAt": identity["knowledge_at"],
            "identitySource": identity["provenance"]["metadata_url"],
            "identityHash": identity["provenance"]["metadata_hash"],
            "sectorMappingVersion": identity["provenance"]["sector_mapping_version"],
            "sectorMappingHash": identity["provenance"]["sector_mapping_hash"],
        })
        if identity_receipt:
            candidate["sourceReferences"]["identityRelease"] = identity_receipt["url"]
    dashboard["companySeries"] = _company_series(rs_frame, candidates)
    dashboard["backtest"] = []
    dashboard["quality"] = quality
    dashboard["watermarks"] = {
        "secAcceptedThrough": max(
            record.timestamps.accepted_at
            for record in selected_records
            if record.timestamps.accepted_at is not None
        ).isoformat(),
        "marketSessionThrough": latest_market.isoformat(),
        "fundamentalsAvailableThrough": None,
    }
    policy = load_notification_policy()
    dashboard["settingsStatus"] = build_settings_status(
        policy,
        environment=os.environ.get("DASHBOARD_ENVIRONMENT", "production"),
        alerts_allowed=False,
        blocking_reasons=sorted({*issues, "QUALITY_GATE_NOT_PASS"}),
        secrets=os.environ,
        generated_at=point,
    )
    export_dashboard(
        dashboard,
        output_dir,
        run_id=run_id,
        generated_at=point,
        as_of=point,
        chunk_by_ticker=True,
    )
    return LiveExperimentalResult(
        output_dir=Path(output_dir),
        run_id=run_id,
        filing_days=filing_days,
        canonical_rows=len(records),
        candidates=len(candidates),
        filings=len(dashboard["filings"]),
        market_coverage=float(coverage["rate"] or 0.0),
        issues=tuple(sorted(issues)),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("app/public/data"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache/live-experimental"))
    parser.add_argument("--lookback-business-days", type=int, default=5)
    parser.add_argument("--max-symbols", type=int, default=0)
    parser.add_argument("--identity-repository")
    parser.add_argument("--identity-target")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print("DRY_RUN: pass --execute to fetch SEC and market data")
        return
    result = generate_live_experimental_dashboard(
        output_dir=args.output,
        cache_dir=args.cache_dir,
        user_agent=os.environ.get("SEC_USER_AGENT", ""),
        lookback_business_days=args.lookback_business_days,
        max_symbols=args.max_symbols,
        identity_repository=args.identity_repository,
        identity_target=args.identity_target,
    )
    print(
        f"LIVE_EXPERIMENTAL {result.run_id}: {result.candidates} candidates, "
        f"{result.filings} filings, market coverage {result.market_coverage:.1%}"
    )


if __name__ == "__main__":
    main()


__all__ = [
    "LiveExperimentalResult",
    "generate_live_experimental_dashboard",
]
