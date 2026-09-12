"""Daily factual research producer from reusable, immutable SEC checkpoints.

No Telegram send or predictive gate bypass occurs in this module. The output
keeps partial SEC and market evidence explicit, while integrity failures abort.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

from insider_turning_engine.domain.research import ResearchScore, SeriesPoint
from insider_turning_engine.domain.session_calendar import latest_closed_session, session_lag
from insider_turning_engine.export import export_dashboard, validate_dashboard_directory
from insider_turning_engine.features.price import price_features
from insider_turning_engine.features.rs import relative_strength_features
from insider_turning_engine.ingestion.market import DailyBar
from insider_turning_engine.ingestion.sec.daily_index import SECDailyIndexSource
from insider_turning_engine.ingestion.sec.historical import _write_json
from insider_turning_engine.ingestion.sec.identity_store import ReleaseIdentityStore
from insider_turning_engine.ingestion.sec.release_store import ReleaseCheckpointStore
from insider_turning_engine.normalization.amendments import resolve_amendments
from insider_turning_engine.normalization.identity import _EXCLUDED_TEXT
from insider_turning_engine.pipeline.daily import _technical_contexts
from insider_turning_engine.pipeline.dashboard_input import build_dashboard_input
from insider_turning_engine.pipeline.identity_observations import acquire_identity_observations
from insider_turning_engine.pipeline.live_experimental import _SECTORS, _fetch_market, _measurement
from insider_turning_engine.pipeline.live_inputs import _COMMON_STOCK, _select_market_universe
from insider_turning_engine.pipeline.research_archive import ResearchArchive
from insider_turning_engine.pipeline.research_history import ResearchHistory, research_history
from insider_turning_engine.pipeline.research_snapshot import (
    build_research_snapshot,
    economic_events,
)
from insider_turning_engine.pipeline.scoring import assemble_daily_scores
from insider_turning_engine.pipeline.sec_acquisition import acquire_range


def discover_research_days(source: SECDailyIndexSource, *, end: date) -> tuple[date, ...]:
    """Inventory a 90-day window within the adapter's 32-day request contract."""
    first = end - timedelta(days=89)
    cursor = end
    days: set[date] = set()
    while cursor >= first:
        start = max(first, cursor - timedelta(days=31))
        batch = source.discover_days(start, cursor)
        if any(day < start or day > cursor for day in batch):
            raise ValueError("SEC discovery returned a day outside the requested range")
        days.update(batch)
        cursor = start - timedelta(days=1)
    return tuple(sorted(days))


def market_shards(
    symbols: Sequence[str], *, cache_dir: Path,
) -> tuple[dict[str, tuple[DailyBar, ...]], dict[str, str]]:
    """Three deterministic disjoint shards; existing providers/cache/fallback retained."""
    selected = sorted(set(symbols))
    shards = [selected[index::3] for index in range(3) if selected[index::3]]
    bars: dict[str, tuple[DailyBar, ...]] = {}
    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        jobs = [executor.submit(_fetch_market, shard, cache_dir=cache_dir) for shard in shards]
        for job in jobs:
            batch, failed, _sources, _cross_validated = job.result()
            bars.update(batch)
            failures.update({symbol: "MARKET_PROVIDER_UNAVAILABLE" for symbol in failed})
    return bars, failures


def materialize_research(
    history: ResearchHistory, *, identity_rows: Sequence[Mapping[str, Any]],
    market: Mapping[str, Sequence[DailyBar]], as_of: datetime, run_id: str,
    output: Path, prior_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministic offline core shared by live orchestration and acceptance tests."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    point = as_of.astimezone(UTC)
    prior = dict(prior_state or {})
    for state in prior.values():
        if (not isinstance(state, dict) or state.get("state") not in {
            "FALLING", "INSIDER_ACCUMULATION", "BASE_FORMING", "EARLY_TURN", "CONFIRMED_TURN"}
            or not isinstance(state.get("established", False), bool)
            or type(state.get("failed_evaluations", 0)) is not int
            or state.get("failed_evaluations", 0) < 0):
            raise ValueError("invalid prior research state")
    closed = latest_closed_session(point)
    available = [row for row in history.records if row.timestamps.knowledge_at <= point
                 and row.timestamps.recorded_at <= point
                 and row.transaction.transaction_date <= point.date()]
    resolution = resolve_amendments(available, as_of=point)
    _events, _owners, blocked, _count = economic_events(available, as_of=point)
    blocked |= history.quarantined_issuers
    joint_issuers = {event.issuer_cik for event in _events if len(event.owners) > 1}
    active, identities, symbols, benchmarks = _select_market_universe(
        available, identity_rows, as_of=point)
    ticker_by_cik = {str(row["cik"]): str(row["ticker"]) for row in identities}
    identities_by_cik = {str(row["cik"]): {**row, "sector": _SECTORS.get(
        str(row.get("sector_etf")), "Unmapped")} for row in identities}
    sectors = {str(row["ticker"]): str(row["sector_etf"]) for row in identities
               if row.get("sector_etf") in _SECTORS}
    # No open-session or future provider observations may enter this snapshot.
    bars = {symbol: tuple(row for row in rows if row.available_at is not None
                          and row.available_at <= point and row.date <= closed)
            for symbol, rows in market.items()}
    fresh = {symbol: rows for symbol, rows in bars.items() if rows
             and (lag := session_lag(max(row.date for row in rows), as_of=point)) is not None
             and lag <= 1}
    priced = {symbol for symbol in symbols if symbol in fresh}
    benchmark_fresh = all(symbol in fresh for symbol in benchmarks)
    technical_symbols = {symbol for symbol in priced if "SPY" in fresh
                         and sectors.get(symbol) in fresh}
    scoring_identity = {cik: ticker for cik, ticker in ticker_by_cik.items()
                        if ticker in technical_symbols and cik not in blocked | joint_issuers}
    all_bars = [row for symbol in sorted(fresh) for row in fresh[symbol]]
    price_frame = price_features(all_bars, as_of=point) if all_bars else pl.DataFrame()
    rs_frame = (relative_strength_features(
        all_bars, as_of=point, sector_by_symbol=sectors, universe_symbols=tuple(symbols))
        if "SPY" in fresh and technical_symbols else pl.DataFrame())
    contexts = (_technical_contexts(price_frame=price_frame, rs_frame=rs_frame,
                                    identity=scoring_identity, as_of=point)
                if not price_frame.is_empty() and not rs_frame.is_empty() else [])
    effective = [row for row in resolution.effective_records if row.issuer.cik not in blocked
                 and row.issuer.cik in ticker_by_cik and _COMMON_STOCK.search(row.security.title)
                 and not _EXCLUDED_TEXT.search(row.security.title)]
    scoring = assemble_daily_scores(effective, contexts, scoring_identity, prior_state or {},
                                    as_of=point, run_id=run_id,
                                    quality={"quality_gate_passed": False})
    parsed = sum(day.parse_rows for day in history.evidence)
    rejected = sum(day.quarantined_rows + day.failures for day in history.evidence)
    issues = {"DAILY_FACTUAL_RESEARCH", "SCORING_METHODOLOGY_INCOMPLETE", "BACKTEST_NOT_RUN",
              "CURRENT_TICKER_MAP_SURVIVORSHIP_BIAS", "OBSERVED_SEC_WINDOW_NOT_MARKET_CENSUS"}
    if not benchmark_fresh:
        issues.add("BENCHMARK_UNAVAILABLE_TECHNICAL_SCORES_WITHHELD")
    if any(not day.complete for day in history.evidence):
        issues.add("SEC_DAY_PARTIAL_DIGEST_BLOCKED")
    if len(priced) != len(symbols):
        issues.add("MARKET_COVERAGE_PARTIAL")
    quality = {
        "disposition": "DEGRADED", "canonicalValid": True, "methodologyComplete": False,
        "benchmarkFresh": benchmark_fresh, "parseSuccess": _measurement(parsed, parsed + rejected,
                                                                          0.995),
        "marketCoverage": _measurement(len(priced), len(symbols), 0.9),
        "coreBranchCoverage": _measurement(0, 0, 0.85), "issues": sorted(issues),
    }
    legacy = build_dashboard_input(
        run_id=run_id, as_of=point, records=effective,
        identity_rows=list(identities_by_cik.values()), ticker_by_cik=ticker_by_cik,
        sector_by_ticker=sectors, scoring_context=contexts, components=scoring.components,
        signals=scoring.signals, quality=quality, score_version="scoring.v1",
        include_legacy_pulse=False,
    )
    # Watermarks describe available sources, not just fully scored companies.
    accepted = [row.timestamps.accepted_at for row in available
                if row.timestamps.accepted_at is not None]
    legacy["watermarks"]["secAcceptedThrough"] = max(accepted).isoformat() if accepted else None
    legacy["watermarks"]["marketSessionThrough"] = max(
        (bar.date.isoformat() for rows in fresh.values() for bar in rows), default=None)
    states = {cik: dict(row) for cik, row in prior.items()}
    states.update({str(row["issuer_cik"]): {**prior.get(str(row["issuer_cik"]), {}),
                                          **dict(row)} for row in scoring.states})
    context_by_cik = {str(row["issuer_cik"]): row for row in contexts}
    for candidate in legacy["candidates"]:
        cik = candidate["issuerCik"]
        previous = (prior_state or {}).get(cik, {})
        current = states.get(cik, {})
        # Unknown initial state must not be presented as observed FALLING merely
        # because the legacy state machine starts its internal enum there.
        price = context_by_cik.get(cik, {})
        falling = (price.get("return_3m") is not None and price["return_3m"] < 0
                   and price.get("close") is not None and price.get("ma50") is not None
                   and price["close"] < price["ma50"])
        current["established"] = bool(previous.get("established")
                                      or candidate["state"] != "FALLING" or falling)
        current["last_evaluated_session"] = closed.isoformat()
        if not current["established"]:
            candidate["sourceReferences"]["initialStateUnestablished"] = True
        if previous and previous.get("state") != current.get("state"):
            current["changed_at"] = point.isoformat()
        elif previous:
            current["changed_at"] = previous.get("changed_at")
        candidate["sourceReferences"]["configHash"] = next(
            (row.get("config_hash") for row in scoring.signals if row["issuer_cik"] == cik), None)
    rs_lookup = {(str(row["symbol"]), str(row["date"])[:10]): row
                 for row in rs_frame.to_dicts()} if not rs_frame.is_empty() else {}
    series: list[SeriesPoint] = []
    for cik, ticker in sorted(ticker_by_cik.items()):
        for bar in sorted(fresh.get(ticker, ()), key=lambda row: row.date):
            if bar.date < point.date() - timedelta(days=366):
                continue
            relative = rs_lookup.get((ticker, bar.date.isoformat()), {})
            series.append(SeriesPoint(
                issuer_cik=cik, date=bar.date, price=float(bar.adj_close or bar.close),
                volume=bar.volume, market_rs=relative.get("mansfield_market"),
                sector_rs=relative.get("mansfield_sector"),
            ))
    research = build_research_snapshot(
        available, as_of=point, run_id=run_id, identities=identities_by_cik,
        expected_sec_days=history.expected_days, day_evidence=history.evidence,
        candidate_rows=legacy["candidates"], company_series=series,
        sec_day_by_accession=history.sec_day_by_accession,
        quarantined_issuers=history.quarantined_issuers,
    )
    for score in research.research_scores:
        source: dict[str, Any] = next((row for row in legacy["candidates"] if row["issuerCik"]
                       == score.issuer_cik), {})
        if source.get("sourceReferences", {}).get("initialStateUnestablished"):
            score.state = "UNKNOWN"
        previous = (prior_state or {}).get(score.issuer_cik, {})
        if previous.get("last_evaluated_session") == closed.isoformat():
            states[score.issuer_cik] = dict(previous)
            score.state = ResearchScore.model_validate({**score.model_dump(),
                "state": previous["state"] if previous.get("established") else "UNKNOWN"}).state
            score.reasons = sorted({*score.reasons, "SAME_SESSION_STATE_REUSED"})
        if score.total is None and previous.get("established"):
            score.state = ResearchScore.model_validate({**score.model_dump(),
                                                        "state": previous["state"]}).state
            score.reasons = sorted({*score.reasons, "STALE_DATA_HOLD"})
            states[score.issuer_cik] = {**previous, "reason_codes": ["STALE_DATA_HOLD"]}
        changed_at = states.get(score.issuer_cik, {}).get("changed_at")
        score.state_changed_at = datetime.fromisoformat(changed_at) if changed_at else None
    legacy["researchSnapshot"] = research.model_dump(by_alias=True, mode="json")
    export_dashboard(legacy, output, run_id=run_id, as_of=point, generated_at=point)
    validate_dashboard_directory(output, require_settings=True)
    return {"runId": run_id, "asOf": point.isoformat(), "states": states,
            "companies": len(research.companies), "events": len(research.economic_transactions),
            "activeIssuerCount": len(active), "latestSecDay": max(history.expected_days).isoformat()
            if history.expected_days else None, "digestReady": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", type=Path, default=Path("app/public/data"))
    parser.add_argument("--work", type=Path, default=Path("work/daily-research"))
    parser.add_argument("--prior-state", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print("DRY_RUN: no network or state mutation; pass --execute for daily research")
        return
    user_agent = os.environ.get("SEC_USER_AGENT", "")
    started = datetime.now(UTC)
    end = started.astimezone(ZoneInfo("America/New_York")).date() - timedelta(days=1)
    store = ReleaseCheckpointStore(args.repository, target=args.target)
    with_source = SECDailyIndexSource(user_agent, cache_dir=args.work / "sec-cache")
    try:
        # Only current days are acquired here. Older gaps belong to resumable backfill.
        acquire_range(with_source, store, start=end - timedelta(days=6), end=end,
                      root=args.work / "acquisition", newest_first=True)
        days = discover_research_days(with_source, end=end)
    finally:
        with_source.close()
    checkpoints = [checkpoint for day in days if (checkpoint := store.latest(day)) is not None]
    history = research_history(checkpoints, expected_days=days)
    print(f"SEC_INPUTS: {len(checkpoints)}/{len(days)} days, {len(history.records)} owner rows",
          flush=True)
    if not history.records:
        raise RuntimeError("no verified canonical SEC facts; previous snapshot preserved")
    point = datetime.now(UTC)
    run_id = f"run_research_{started:%Y%m%dT%H%M%SZ}"
    ciks = sorted({row.issuer.cik for row in history.records
                   if row.transaction.code in {"P", "S"}})
    identity_store = ReleaseIdentityStore(args.repository, target=args.target)
    print(f"IDENTITY_REFRESH: {len(ciks)} requested issuers", flush=True)
    previous = identity_store.latest()
    previous_path = args.work / "prior-identities.json"
    if previous is not None:
        previous_path.parent.mkdir(parents=True, exist_ok=True)
        previous_path.write_text(json.dumps(previous, sort_keys=True), encoding="utf-8")
    acquire_identity_observations(ciks, user_agent=user_agent, run_id=run_id,
                                   output=args.work / "identities",
                                   previous=previous_path if previous is not None else None)
    identities = json.loads((args.work / "identities" / "identities.json").read_text("utf-8"))
    identity_store.persist(identities)
    point = datetime.now(UTC)
    _active, _identity, symbols, benchmarks = _select_market_universe(
        history.records, identities, as_of=point)
    print(f"MARKET_REFRESH: {len(symbols)} stocks, {len(benchmarks)} benchmarks", flush=True)
    market, failures = market_shards((*symbols, *benchmarks), cache_dir=args.work / "market")
    print(f"MARKET_INPUTS: {len(market)} available, {len(failures)} failures", flush=True)
    prior = json.loads(args.prior_state.read_text("utf-8")) \
        if args.prior_state and args.prior_state.exists() else {}
    report = materialize_research(
        history, identity_rows=identities, market=market, as_of=datetime.now(UTC),
        run_id=run_id, output=args.output, prior_state=prior,
    )
    report["marketFailures"] = failures
    report["durationSeconds"] = round((datetime.now(UTC) - started).total_seconds(), 1)
    _write_json(args.work / "daily-report.json", report)
    print("RESEARCH_VALIDATED: archiving before operational state commit", flush=True)
    # The snapshot must be independently recoverable BEFORE committing score state.
    receipt = ResearchArchive(args.repository, target=args.target).publish(args.output)
    report["archive"] = receipt
    _write_json(args.work / "daily-report.json", report)
    _write_json(args.work / "incoming-state" / "prior-states.json", report["states"])
    _write_json(args.work / "incoming-state" / "watermarks.json", {
        "schemaVersion": "2.0.0", "runId": run_id, "asOf": report["asOf"],
        "researchSnapshot": receipt, "lastObservedSecDay": report["latestSecDay"],
        # Per-day immutable checkpoints are the acquisition progress ledger.
        # Partial research publication never advances the canonical SEC cursor.
        "canonicalCursorAdvanced": False,
    })
    print(f"RESEARCH_SNAPSHOT {run_id}: {report['companies']} companies, {report['events']} events")


if __name__ == "__main__":
    main()
