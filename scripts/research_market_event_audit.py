"""Research-only issuer-session audit of the 2016-2022 Alpaca market backfill.

This audit never reads 2023+ data and never changes production scoring. It joins
only the predeclared simple-baseline insider purchase universe to regular market
sessions, quantifies attrition, flags historical ticker identity collisions, and
keeps zero-volume/zero-trade terminal candidates out of ordinary sessions.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import pandas as pd

HORIZONS = (21, 63, 126, 252)
START_YEAR = 2016
END_YEAR = 2022
SEALED_YEAR = 2023
IDENTITY_PLACEHOLDERS = frozenset({"NA", "NONE"})


def _bool(value: object) -> bool:
    return str(value).strip().lower() == "true"


def _qualified_purchase(row: dict[str, Any]) -> bool:
    transaction = row.get("transaction", {})
    security = row.get("security", {})
    return (
        security.get("tableType") == "NON_DERIVATIVE"
        and transaction.get("code") == "P"
        and transaction.get("acquiredDisposed") == "A"
        and transaction.get("economicClassification") == "OPEN_MARKET_PURCHASE"
    )


def _evaluation_session(knowledge: str, calendar: Any) -> str:
    """Return the first XNYS session whose close is eligible after knowledgeAt."""
    timestamp = pd.Timestamp(knowledge)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")

    local_day = timestamp.tz_convert("America/New_York").normalize().tz_localize(None)
    if calendar.is_session(local_day):
        session = local_day
        if timestamp <= calendar.session_close(session):
            return str(session.date())
        return str(calendar.next_session(session).date())

    return str(calendar.date_to_session(local_day, direction="next").date())


def _load_events(sec_path: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    calendar = xcals.get_calendar("XNYS")
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    effective_rows = 0
    qualified_rows = 0
    qualified_rows_by_year: dict[int, int] = defaultdict(int)

    with sec_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            knowledge = str(row["timestamps"]["knowledgeAt"])
            year = int(knowledge[:4])
            if year >= SEALED_YEAR:
                raise ValueError("sealed OOS boundary violated by SEC input")
            if not START_YEAR <= year <= END_YEAR:
                continue
            effective_rows += 1
            if not _qualified_purchase(row):
                continue

            qualified_rows += 1
            qualified_rows_by_year[year] += 1
            cik = str(row.get("issuer", {}).get("cik") or "")
            evaluation_session = _evaluation_session(knowledge, calendar)
            key = (cik, evaluation_session)
            event = grouped.setdefault(
                key,
                {
                    "issuerCik": cik,
                    "evaluationSession": evaluation_session,
                    "knowledgeYear": year,
                    "knowledgeAtFirst": knowledge,
                    "knowledgeAtLast": knowledge,
                    "tickers": set(),
                    "rawQualifiedRows": 0,
                },
            )
            event["rawQualifiedRows"] += 1
            event["knowledgeAtFirst"] = min(str(event["knowledgeAtFirst"]), knowledge)
            event["knowledgeAtLast"] = max(str(event["knowledgeAtLast"]), knowledge)
            ticker_raw = row.get("issuer", {}).get("ticker")
            if ticker_raw:
                event["tickers"].add(str(ticker_raw).strip().upper())

    total_events = len(grouped)
    events_by_year: dict[int, int] = defaultdict(int)
    missing_ticker_events = 0
    placeholder_only_events = 0
    placeholder_with_real_events = 0
    multi_real_ticker_events = 0
    by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ticker_session_ciks: dict[tuple[str, str], set[str]] = defaultdict(set)

    for event in grouped.values():
        year = int(event["knowledgeYear"])
        events_by_year[year] += 1
        tickers = sorted(event.pop("tickers"))
        if not tickers:
            missing_ticker_events += 1
            continue

        real_tickers = [ticker for ticker in tickers if ticker not in IDENTITY_PLACEHOLDERS]
        placeholder_tickers = [ticker for ticker in tickers if ticker in IDENTITY_PLACEHOLDERS]
        if not real_tickers:
            placeholder_only_events += 1
            continue
        if placeholder_tickers:
            placeholder_with_real_events += 1
        if len(real_tickers) != 1:
            multi_real_ticker_events += 1
            continue

        ticker = real_tickers[0]
        event["ticker"] = ticker
        event["identityAmbiguous"] = False
        by_ticker[ticker].append(event)
        ticker_session_ciks[(ticker, str(event["evaluationSession"]))].add(
            str(event["issuerCik"])
        )

    collisions = {
        key: sorted(ciks)
        for key, ciks in ticker_session_ciks.items()
        if len({cik for cik in ciks if cik}) > 1
    }
    collision_events = 0
    for ticker, events in by_ticker.items():
        for event in events:
            key = (ticker, str(event["evaluationSession"]))
            if key in collisions:
                event["identityAmbiguous"] = True
                collision_events += 1

    diagnostics = {
        "effectiveSecRows2016To2022": effective_rows,
        "rawQualifiedPurchaseRows": qualified_rows,
        "rawQualifiedPurchaseRowsByYear": dict(sorted(qualified_rows_by_year.items())),
        "qualifiedIssuerSessionEvents": total_events,
        "qualifiedIssuerSessionEventsByYear": dict(sorted(events_by_year.items())),
        "issuerSessionEventsMissingTicker": missing_ticker_events,
        "issuerSessionEventsPlaceholderOnly": placeholder_only_events,
        "issuerSessionEventsPlaceholderWithRealTicker": placeholder_with_real_events,
        "issuerSessionEventsWithMultipleRealTickers": multi_real_ticker_events,
        "identityPlaceholders": sorted(IDENTITY_PLACEHOLDERS),
        "tickerSessionIdentityCollisions": len(collisions),
        "issuerSessionEventsInTickerCollisions": collision_events,
        "collisions": collisions,
    }
    return by_ticker, diagnostics


def _market_files(market_root: Path) -> list[Path]:
    files = sorted(market_root.rglob("canonical-market-*.csv"))
    if not files:
        raise ValueError("no canonical market CSV files found")
    years = []
    for path in files:
        year = int(path.stem.rsplit("-", 1)[-1])
        if not START_YEAR <= year <= END_YEAR:
            raise ValueError(f"out-of-bounds market file: {path}")
        years.append(year)
    if set(years) != set(range(START_YEAR, END_YEAR + 1)):
        raise ValueError(f"expected market years 2016-2022, got {sorted(set(years))}")
    return files


def _build_market_db(files: list[Path], db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            PRAGMA temp_store=MEMORY;
            CREATE TABLE market (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER NOT NULL,
                trade_count INTEGER NOT NULL,
                terminal INTEGER NOT NULL
            );
            """
        )
        insert_sql = (
            "INSERT INTO market "
            "(ticker,date,open,high,low,close,volume,trade_count,terminal) "
            "VALUES (?,?,?,?,?,?,?,?,?)"
        )
        total_rows = 0
        terminal_rows = 0
        duplicate_rows = 0
        seen_keys: set[tuple[str, str]] = set()
        batch: list[tuple[object, ...]] = []

        for path in files:
            with path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                for row in reader:
                    ticker = str(row["ticker"]).strip().upper()
                    day = str(row["date"])[:10]
                    year = int(day[:4])
                    if not START_YEAR <= year <= END_YEAR:
                        raise ValueError(
                            f"sealed OOS boundary violated by market row {ticker} {day}"
                        )
                    key = (ticker, day)
                    if key in seen_keys:
                        duplicate_rows += 1
                        continue
                    seen_keys.add(key)
                    terminal = _bool(row.get("terminal_candidate"))
                    if terminal:
                        terminal_rows += 1
                    batch.append(
                        (
                            ticker,
                            day,
                            float(row["open"]),
                            float(row["high"]),
                            float(row["low"]),
                            float(row["close"]),
                            int(float(row.get("volume") or 0)),
                            int(float(row.get("trade_count") or 0)),
                            int(terminal),
                        )
                    )
                    total_rows += 1
                    if len(batch) >= 50_000:
                        conn.executemany(insert_sql, batch)
                        batch.clear()
        if batch:
            conn.executemany(insert_sql, batch)
        conn.execute("CREATE INDEX market_ticker_date_idx ON market(ticker, date)")
        conn.commit()
        return {
            "marketRowsRead": total_rows,
            "marketRowsInserted": total_rows - duplicate_rows,
            "duplicateTickerDateRowsIgnored": duplicate_rows,
            "terminalCandidateRows": terminal_rows,
        }
    finally:
        conn.close()


def _regular_sessions(rows: list[tuple[Any, ...]]) -> tuple[list[str], list[float]]:
    dates: list[str] = []
    closes: list[float] = []
    for day, _open, _high, _low, close, volume, trade_count, terminal in rows:
        if not terminal and int(volume) > 0 and int(trade_count) > 0:
            dates.append(str(day))
            closes.append(float(close))
    return dates, closes


def _terminal_tail(rows: list[tuple[Any, ...]]) -> dict[str, Any] | None:
    if not rows:
        return None
    index = len(rows)
    while index > 0:
        row = rows[index - 1]
        if not bool(row[7]):
            break
        index -= 1
    if index == len(rows):
        return None
    tail = rows[index:]
    closes = [float(row[4]) for row in tail]
    flat_ohlc = all(
        float(row[1]) == float(row[2]) == float(row[3]) == float(row[4]) for row in tail
    )
    constant_close = max(closes) - min(closes) <= 1e-9
    return {
        "startDate": str(tail[0][0]),
        "rows": len(tail),
        "close": closes[0],
        "constantClose": constant_close,
        "flatOhlc": flat_ohlc,
        "strictTerminalValueCandidate": bool(constant_close and flat_ohlc),
    }


def _spy_expected_sessions() -> set[str]:
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range("2016-01-01", "2022-12-31")
    return {str(value.date()) for value in sessions}


def audit(*, sec_path: Path, market_root: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    events_by_ticker, sec_diag = _load_events(sec_path)
    files = _market_files(market_root)
    db_path = output / "market-audit.sqlite"
    if db_path.exists():
        db_path.unlink()
    market_diag = _build_market_db(files, db_path)

    conn = sqlite3.connect(db_path)
    split_stats: dict[str, dict[str, Any]] = {
        "development2016To2020": defaultdict(int),
        "validation2021To2022": defaultdict(int),
    }
    horizon_stats: dict[str, dict[int, dict[str, int]]] = {
        split: {h: defaultdict(int) for h in HORIZONS} for split in split_stats
    }
    missing_tickers: dict[str, int] = defaultdict(int)
    terminal_tails: list[dict[str, Any]] = []
    terminal_interaction_events = 0
    entry_matched_total = 0
    identity_collision_events = 0

    try:
        for ticker, events in sorted(events_by_ticker.items()):
            rows = conn.execute(
                "SELECT date,open,high,low,close,volume,trade_count,terminal "
                "FROM market WHERE ticker=? ORDER BY date",
                (ticker,),
            ).fetchall()
            regular_dates, _regular_closes = _regular_sessions(rows)
            tail = _terminal_tail(rows)
            if tail is not None:
                terminal_tails.append({"ticker": ticker, **tail})

            for event in events:
                split = (
                    "development2016To2020"
                    if int(event["knowledgeYear"]) <= 2020
                    else "validation2021To2022"
                )
                stats = split_stats[split]
                stats["qualifiedWithSingleRealTicker"] += 1
                if event["identityAmbiguous"]:
                    stats["tickerSessionIdentityAmbiguous"] += 1
                    identity_collision_events += 1
                    continue
                stats["identityEligible"] += 1
                if not regular_dates:
                    stats["noRegularMarketHistory"] += 1
                    missing_tickers[ticker] += 1
                    continue

                evaluation_session = str(event["evaluationSession"])
                entry_index = bisect.bisect_right(regular_dates, evaluation_session)
                if entry_index >= len(regular_dates):
                    stats["noNextRegularSession"] += 1
                    missing_tickers[ticker] += 1
                    continue
                entry_date = regular_dates[entry_index]
                stats["entryMatched"] += 1
                entry_matched_total += 1

                tail_start = str(tail["startDate"]) if tail is not None else None
                event_terminal_interaction = False
                for horizon in HORIZONS:
                    hstats = horizon_stats[split][horizon]
                    hstats["entryMatched"] += 1
                    target_index = entry_index + horizon
                    if target_index < len(regular_dates):
                        hstats["regularHorizonObserved"] += 1
                        continue
                    if tail_start is not None and tail_start > entry_date:
                        hstats["terminalBeforeHorizon"] += 1
                        event_terminal_interaction = True
                    else:
                        hstats["rightCensoredBefore2023"] += 1
                if event_terminal_interaction:
                    terminal_interaction_events += 1
                    stats["eventsTouchingTerminalTail"] += 1

        spy_rows = conn.execute(
            "SELECT date,open,high,low,close,volume,trade_count,terminal "
            "FROM market WHERE ticker='SPY' ORDER BY date"
        ).fetchall()
        spy_regular, _ = _regular_sessions(spy_rows)
    finally:
        conn.close()
        db_path.unlink(missing_ok=True)

    expected_spy = _spy_expected_sessions()
    observed_spy = set(spy_regular)
    missing_spy = sorted(expected_spy - observed_spy)
    extra_spy = sorted(observed_spy - expected_spy)

    total_events = int(sec_diag["qualifiedIssuerSessionEvents"])
    missing_ticker = int(sec_diag["issuerSessionEventsMissingTicker"])
    placeholder_only = int(sec_diag["issuerSessionEventsPlaceholderOnly"])
    multi_real_ticker = int(sec_diag["issuerSessionEventsWithMultipleRealTickers"])
    identity_missing = missing_ticker + placeholder_only
    with_usable_ticker = total_events - identity_missing
    ambiguous_total = multi_real_ticker + identity_collision_events
    identity_eligible = with_usable_ticker - ambiguous_total
    entry_coverage_eligible = entry_matched_total / identity_eligible if identity_eligible else 0.0
    raw_missing_ticker_rate = missing_ticker / total_events if total_events else 0.0
    identity_missing_rate = identity_missing / total_events if total_events else 0.0
    identity_ambiguous_rate = ambiguous_total / with_usable_ticker if with_usable_ticker else 0.0

    strict_terminal_tails = sum(
        1 for row in terminal_tails if row["strictTerminalValueCandidate"]
    )
    gate_checks = {
        "spyComplete": not missing_spy,
        "eligibleEntryCoverageAtLeast95Pct": entry_coverage_eligible >= 0.95,
        "qualifiedIdentityMissingOrPlaceholderAtMost1Pct": identity_missing_rate <= 0.01,
        "identityAmbiguityAtMost0_5Pct": identity_ambiguous_rate <= 0.005,
        "oosClosed": True,
        "terminalRowsExcludedFromRegularSessions": True,
    }
    gate_pass = all(gate_checks.values())

    collisions_json = [
        {"ticker": ticker, "evaluationSession": session, "issuerCiks": ciks}
        for (ticker, session), ciks in sorted(sec_diag.pop("collisions").items())
    ]
    (output / "identity-collisions.json").write_text(
        json.dumps(collisions_json, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "terminal-tails.json").write_text(
        json.dumps(terminal_tails, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    missing_ranked = [
        {"ticker": ticker, "qualifiedIssuerSessionsMissingEntry": count}
        for ticker, count in sorted(missing_tickers.items(), key=lambda item: (-item[1], item[0]))
    ]
    (output / "missing-entry-tickers.json").write_text(
        json.dumps(missing_ranked, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary: dict[str, Any] = {
        "schemaVersion": "1.2.0",
        "dataset": "Issuer-session market coverage and terminal audit",
        "period": "2016-2022",
        "baselineUniverse": "non-derivative open-market purchase P/A",
        "eventUnit": "issuer CIK + first eligible XNYS evaluation session",
        "executionClock": (
            "knowledgeAt -> first eligible daily evaluation close -> next session open"
        ),
        "identityPolicy": (
            "NA/NONE are research-only placeholder identities; raw SEC evidence is unchanged"
        ),
        "regularSessionRule": "terminal_candidate=false AND volume>0 AND trade_count>0",
        "horizonsSessions": list(HORIZONS),
        "sec": sec_diag,
        "market": market_diag,
        "entry": {
            "qualifiedIssuerSessionEvents": total_events,
            "issuerSessionEventsWithUsableTicker": with_usable_ticker,
            "identityMissingOrPlaceholderEvents": identity_missing,
            "identityPlaceholderOnlyEvents": placeholder_only,
            "identityAmbiguousEvents": ambiguous_total,
            "identityEligibleEvents": identity_eligible,
            "entryMatchedEvents": entry_matched_total,
            "eligibleEntryCoverage": entry_coverage_eligible,
            "rawMissingTickerRate": raw_missing_ticker_rate,
            "identityMissingOrPlaceholderRate": identity_missing_rate,
            "identityAmbiguousRateAmongUsableTickered": identity_ambiguous_rate,
        },
        "splits": {split: dict(values) for split, values in split_stats.items()},
        "horizonAvailability": {
            split: {str(h): dict(values) for h, values in horizons.items()}
            for split, horizons in horizon_stats.items()
        },
        "spy": {
            "expectedSessions": len(expected_spy),
            "observedRegularSessions": len(observed_spy),
            "missingSessions": missing_spy,
            "extraSessions": extra_spy,
        },
        "terminalAudit": {
            "terminalTailSymbols": len(terminal_tails),
            "strictTerminalValueCandidateSymbols": strict_terminal_tails,
            "qualifiedEventsTouchingTerminalTail": terminal_interaction_events,
            "policy": (
                "zero-volume/zero-trade terminal candidates are excluded from ordinary sessions; "
                "trailing constant flat-OHLC values are diagnostic terminal-value candidates only; "
                "unknown terminal outcomes are never silently imputed"
            ),
        },
        "gateChecks": gate_checks,
        "gateRecommendation": "PASS_FOR_SIMPLE_BASELINE" if gate_pass else "REVIEW_ATTRITION",
        "marketDataJoined": gate_pass,
        "canonicalReady": False,
        "signalReady": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "status": "MARKET_ISSUER_SESSION_AUDIT_COMPLETE",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sec", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(sec_path=args.sec, market_root=args.market_root, output=args.output)


if __name__ == "__main__":
    main()
