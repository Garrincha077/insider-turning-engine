"""Build a real-data, explicitly unvalidated static dashboard snapshot.

This path exists to keep the public UI useful while scoring.v1 remains a
CANDIDATE methodology. It reuses canonical parsers, feature calculators and
the score engine, but never creates alerts or a validation/backtest claim.
"""

from __future__ import annotations

import argparse
import os
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from insider_turning_engine.domain.models import CanonicalTransaction, TableType
from insider_turning_engine.export import export_dashboard
from insider_turning_engine.features.price import price_features
from insider_turning_engine.features.rs import relative_strength_features
from insider_turning_engine.ingestion.market import DailyBar, YahooChartProvider
from insider_turning_engine.ingestion.sec import (
    SECCompanyTickerSource,
    SECDailyIndexSource,
    parse_sec_filing,
)
from insider_turning_engine.ingestion.sec.historical import validate_sec_user_agent
from insider_turning_engine.normalization.amendments import resolve_amendments
from insider_turning_engine.pipeline.daily import _technical_contexts
from insider_turning_engine.pipeline.dashboard_input import build_dashboard_input
from insider_turning_engine.pipeline.scoring import assemble_daily_scores

_COMMON = re.compile(r"\b(?:common(?: stock| shares?)?|ordinary shares?)\b", re.IGNORECASE)


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
    ticker = record.issuer.ticker or ""
    return (
        bool(ticker)
        and record.timestamps.accepted_at is not None
        and record.timestamps.accepted_at <= as_of
        and record.transaction.transaction_date >= as_of.date() - timedelta(days=365)
        and record.transaction.transaction_date <= as_of.date()
        and record.transaction.code == "P"
        and record.transaction.value is not None
        and record.security.table_type is TableType.NON_DERIVATIVE
        and _COMMON.search(record.security.title) is not None
    )


def _select_issuers(
    records: Sequence[CanonicalTransaction],
    identity_rows: Sequence[Any],
    *,
    as_of: datetime,
    max_symbols: int,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    if max_symbols < 5 or max_symbols > 100:
        raise ValueError("max_symbols must be between 5 and 100")
    current = {(row.cik, row.ticker): row for row in identity_rows}
    dollars: defaultdict[str, float] = defaultdict(float)
    tickers: dict[str, str] = {}
    for record in records:
        if not _qualifying_purchase(record, as_of):
            continue
        ticker = str(record.issuer.ticker).upper()
        key = (record.issuer.cik, ticker)
        if key not in current:
            continue
        dollars[record.issuer.cik] += float(record.transaction.value or 0)
        tickers[record.issuer.cik] = ticker
    selected_ciks = sorted(dollars, key=lambda cik: (-dollars[cik], cik))[:max_symbols]
    ticker_by_cik = {cik: tickers[cik] for cik in selected_ciks}
    selected_identities: list[dict[str, Any]] = []
    for cik, ticker in ticker_by_cik.items():
        row = current[(cik, ticker)]
        selected_identities.append(
            {
                "cik": cik,
                "ticker": ticker,
                "name": row.name,
                "exchange": row.exchange,
                "security_type": "COMMON_STOCK",
                "knowledge_at": row.knowledge_at,
                "sector": "Unmapped",
                # Until the live path has a point-in-time SIC history, SPY is
                # an explicit technical proxy rather than an invented sector.
                "sector_etf": "SPY",
            }
        )
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
) -> tuple[dict[str, tuple[DailyBar, ...]], dict[str, str]]:
    provider = YahooChartProvider(cache_dir=cache_dir)
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
    return bars, failures


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
    max_symbols: int = 40,
    now: datetime | None = None,
) -> LiveExperimentalResult:
    """Fetch real inputs and atomically publish one experimental snapshot."""

    point = (now or datetime.now(UTC)).astimezone(UTC)
    validated_user_agent = validate_sec_user_agent(user_agent)
    run_id = f"run_live_{point:%Y%m%dT%H%M%SZ}"
    root = Path(cache_dir)
    filing_days = _business_days(point.date() - timedelta(days=1), lookback_business_days)
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

    identity_source = SECCompanyTickerSource(
        validated_user_agent,
        cache_dir=root / "sec-identity",
    )
    try:
        identity_result = identity_source.fetch()
    finally:
        identity_source.close()
    ticker_by_cik, identity_rows = _select_issuers(
        records,
        identity_result.records,
        as_of=point,
        max_symbols=max_symbols,
    )
    if not ticker_by_cik:
        raise RuntimeError("live SEC window has no exchange-mapped common-stock purchases")

    requested_symbols = {*ticker_by_cik.values(), "SPY"}
    fetched_market, market_failures = _fetch_market(
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
    if "SPY" not in market:
        raise RuntimeError("SPY benchmark is unavailable; live snapshot is blocked")
    available_tickers = {symbol for symbol in ticker_by_cik.values() if symbol in market}
    ticker_by_cik = {
        cik: ticker for cik, ticker in ticker_by_cik.items() if ticker in available_tickers
    }
    identity_rows = [row for row in identity_rows if row["ticker"] in available_tickers]
    selected_records = [record for record in records if record.issuer.cik in ticker_by_cik]
    all_bars = [bar for rows in market.values() for bar in rows]
    price_frame = price_features(all_bars, as_of=point)
    sector_by_symbol = {ticker: "SPY" for ticker in ticker_by_cik.values()}
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

    requested_candidates = len(requested_symbols) - 1
    coverage = _measurement(len(available_tickers), requested_candidates, 0.90)
    parse_quality = _measurement(
        sec_parsed,
        sec_parsed + sec_quarantines + sec_failures,
        0.995,
    )
    latest_market = max(bar.date for symbol in available_tickers for bar in market[symbol])
    spy_latest = max(bar.date for bar in market["SPY"])
    benchmark_fresh = spy_latest >= latest_market and (point.date() - spy_latest).days <= 4
    issues = {
        "BACKTEST_NOT_RUN",
        "CURRENT_TICKER_MAP_SURVIVORSHIP_BIAS",
        "LIVE_EXPERIMENTAL_ROLLING_WINDOW",
        "SCORING_METHODOLOGY_INCOMPLETE",
        "SECTOR_RS_PROXY_SPY",
        "YAHOO_MARKET_DATA_FALLBACK",
    }
    if sec_quarantines:
        issues.add("SEC_QUARANTINE_ROWS_EXCLUDED")
    if amendment_quarantines:
        issues.add("ROLLING_WINDOW_AMENDMENT_PREDECESSOR_MISSING")
    if sec_failures:
        issues.add("SEC_FILING_DAY_FAILURE")
    if market_failures:
        issues.add("MARKET_SYMBOL_FAILURES")
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
    for candidate in candidates:
        candidate["sector"] = "Unmapped / SPY proxy"
        candidate["reasons"] = list(
            dict.fromkeys([*candidate["reasons"], "LIVE_EXPERIMENTAL", "SECTOR_RS_PROXY_SPY"])
        )[:6]
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
    parser.add_argument("--max-symbols", type=int, default=40)
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
