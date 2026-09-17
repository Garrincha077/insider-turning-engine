"""Exact-calendar P0 market audit with tiered research data-quality gates.

Research only. This module reuses the bounded SEC/market loaders from the v1 audit,
but evaluates entry and horizons on the exact XNYS calendar. It never reads 2023+
market outcomes and never changes production scoring.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import research_market_event_audit as v1

TIER_THRESHOLDS: dict[str, dict[str, float]] = {
    "A_HIGH_CONFIDENCE": {
        "entryCoverageMin": 0.95,
        "identityMissingMax": 0.01,
        "identityAmbiguityMax": 0.005,
        "totalIdentityProblemMax": 0.015,
        "worstYearEntryCoverageMin": 0.90,
        "spyCoverageMin": 1.00,
    },
    "B_RESEARCH_GRADE": {
        "entryCoverageMin": 0.90,
        "identityMissingMax": 0.03,
        "identityAmbiguityMax": 0.01,
        "totalIdentityProblemMax": 0.04,
        "worstYearEntryCoverageMin": 0.85,
        "spyCoverageMin": 0.995,
    },
    "C_EXPLORATORY": {
        "entryCoverageMin": 0.80,
        "identityMissingMax": 0.075,
        "identityAmbiguityMax": 0.02,
        "totalIdentityProblemMax": 0.09,
        "worstYearEntryCoverageMin": 0.70,
        "spyCoverageMin": 0.99,
    },
}


def _expected_sessions() -> tuple[str, ...]:
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range("2016-01-01", "2022-12-31")
    return tuple(str(value.date()) for value in sessions)


def _is_regular(row: tuple[Any, ...]) -> bool:
    return not bool(row[7]) and int(row[5]) > 0 and int(row[6]) > 0


def _regular_dates(rows: list[tuple[Any, ...]]) -> set[str]:
    return {str(row[0]) for row in rows if _is_regular(row)}


def _tier_checks(metrics: dict[str, float], thresholds: dict[str, float]) -> dict[str, bool]:
    return {
        "entryCoverage": metrics["entryCoverage"] >= thresholds["entryCoverageMin"],
        "identityMissing": metrics["identityMissing"] <= thresholds["identityMissingMax"],
        "identityAmbiguity": metrics["identityAmbiguity"] <= thresholds["identityAmbiguityMax"],
        "totalIdentityProblem": (
            metrics["totalIdentityProblem"] <= thresholds["totalIdentityProblemMax"]
        ),
        "worstYearEntryCoverage": (
            metrics["worstYearEntryCoverage"] >= thresholds["worstYearEntryCoverageMin"]
        ),
        "spyCoverage": metrics["spyCoverage"] >= thresholds["spyCoverageMin"],
    }


def select_data_quality_tier(metrics: dict[str, float]) -> tuple[str, dict[str, dict[str, bool]]]:
    checks = {
        tier: _tier_checks(metrics, thresholds)
        for tier, thresholds in TIER_THRESHOLDS.items()
    }
    for tier in ("A_HIGH_CONFIDENCE", "B_RESEARCH_GRADE", "C_EXPLORATORY"):
        if all(checks[tier].values()):
            return tier, checks
    return "FAIL_BELOW_EXPLORATORY", checks


def audit(*, sec_path: Path, market_root: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    events_by_ticker, sec_diag = v1._load_events(sec_path)
    market_files = v1._market_files(market_root)
    expected_sessions = _expected_sessions()
    session_index = {day: index for index, day in enumerate(expected_sessions)}
    last_study_session = expected_sessions[-1]

    db_path = output / "market-audit.sqlite"
    db_path.unlink(missing_ok=True)
    market_diag = v1._build_market_db(market_files, db_path)

    split_stats: dict[str, dict[str, int]] = {
        "development2016To2020": defaultdict(int),
        "validation2021To2022": defaultdict(int),
    }
    year_stats: dict[int, dict[str, int]] = {
        year: defaultdict(int) for year in range(v1.START_YEAR, v1.END_YEAR + 1)
    }
    horizon_stats: dict[str, dict[int, dict[str, int]]] = {
        split: {horizon: defaultdict(int) for horizon in v1.HORIZONS}
        for split in split_stats
    }
    missing_tickers: dict[str, int] = defaultdict(int)
    terminal_tails: list[dict[str, Any]] = []
    entry_matched_total = 0
    entry_boundary_censored_total = 0
    identity_collision_events = 0
    terminal_interaction_events = 0

    conn = sqlite3.connect(db_path)
    try:
        for ticker, events in sorted(events_by_ticker.items()):
            rows = conn.execute(
                "SELECT date,open,high,low,close,volume,trade_count,terminal "
                "FROM market WHERE ticker=? ORDER BY date",
                (ticker,),
            ).fetchall()
            by_date = {str(row[0]): row for row in rows}
            regular_dates = _regular_dates(rows)
            tail = v1._terminal_tail(rows)
            if tail is not None:
                terminal_tails.append({"ticker": ticker, **tail})
            tail_start = str(tail["startDate"]) if tail is not None else None

            for event in events:
                year = int(event["knowledgeYear"])
                split = (
                    "development2016To2020" if year <= 2020 else "validation2021To2022"
                )
                stats = split_stats[split]
                ystats = year_stats[year]
                stats["qualifiedWithSingleRealTicker"] += 1
                ystats["qualifiedWithSingleRealTicker"] += 1

                if event["identityAmbiguous"]:
                    stats["tickerSessionIdentityAmbiguous"] += 1
                    ystats["tickerSessionIdentityAmbiguous"] += 1
                    identity_collision_events += 1
                    continue

                stats["identityEligible"] += 1
                ystats["identityEligible"] += 1
                if not regular_dates:
                    stats["noRegularMarketHistory"] += 1
                    ystats["noRegularMarketHistory"] += 1
                    missing_tickers[ticker] += 1
                    continue

                evaluation_session = str(event["evaluationSession"])
                evaluation_index = session_index.get(evaluation_session)
                if evaluation_index is None:
                    if evaluation_session > last_study_session:
                        stats["evaluationStudyBoundaryRightCensored"] += 1
                        ystats["evaluationStudyBoundaryRightCensored"] += 1
                        entry_boundary_censored_total += 1
                        continue
                    raise ValueError(
                        f"evaluation session outside bounded XNYS calendar: {evaluation_session}"
                    )

                entry_index = evaluation_index + 1
                if entry_index >= len(expected_sessions):
                    stats["entryStudyBoundaryRightCensored"] += 1
                    ystats["entryStudyBoundaryRightCensored"] += 1
                    entry_boundary_censored_total += 1
                    continue

                entry_date = expected_sessions[entry_index]
                entry_row = by_date.get(entry_date)
                if entry_row is None or not _is_regular(entry_row):
                    if tail_start is not None and tail_start <= entry_date:
                        stats["terminalBeforeOrAtEntry"] += 1
                        ystats["terminalBeforeOrAtEntry"] += 1
                    else:
                        stats["missingExactEntryBar"] += 1
                        ystats["missingExactEntryBar"] += 1
                    missing_tickers[ticker] += 1
                    continue

                stats["entryMatched"] += 1
                ystats["entryMatched"] += 1
                entry_matched_total += 1
                touches_terminal = False

                for horizon in v1.HORIZONS:
                    hstats = horizon_stats[split][horizon]
                    hstats["entryMatched"] += 1
                    target_index = entry_index + horizon
                    if target_index >= len(expected_sessions):
                        hstats["studyBoundaryRightCensored"] += 1
                        continue
                    target_date = expected_sessions[target_index]
                    target_row = by_date.get(target_date)
                    if target_row is not None and _is_regular(target_row):
                        hstats["exactHorizonObserved"] += 1
                    elif tail_start is not None and entry_date < tail_start <= target_date:
                        hstats["terminalBeforeHorizon"] += 1
                        touches_terminal = True
                    else:
                        hstats["missingExactHorizonBar"] += 1

                if touches_terminal:
                    stats["eventsTouchingTerminalTail"] += 1
                    ystats["eventsTouchingTerminalTail"] += 1
                    terminal_interaction_events += 1

        spy_rows = conn.execute(
            "SELECT date,open,high,low,close,volume,trade_count,terminal "
            "FROM market WHERE ticker='SPY' ORDER BY date"
        ).fetchall()
        observed_spy = _regular_dates(spy_rows)
    finally:
        conn.close()
        db_path.unlink(missing_ok=True)

    expected_spy = set(expected_sessions)
    missing_spy = sorted(expected_spy - observed_spy)
    extra_spy = sorted(observed_spy - expected_spy)

    total_events = int(sec_diag["qualifiedIssuerSessionEvents"])
    missing_ticker = int(sec_diag["issuerSessionEventsMissingTicker"])
    placeholder_only = int(sec_diag["issuerSessionEventsPlaceholderOnly"])
    multi_real_ticker = int(sec_diag["issuerSessionEventsWithMultipleRealTickers"])
    identity_missing = missing_ticker + placeholder_only
    usable_ticker = total_events - identity_missing
    ambiguous_total = multi_real_ticker + identity_collision_events
    identity_eligible = usable_ticker - ambiguous_total
    entry_assessable = identity_eligible - entry_boundary_censored_total

    entry_coverage = entry_matched_total / entry_assessable if entry_assessable else 0.0
    identity_missing_rate = identity_missing / total_events if total_events else 0.0
    identity_ambiguity_rate = ambiguous_total / usable_ticker if usable_ticker else 0.0
    total_identity_problem_rate = (
        (identity_missing + ambiguous_total) / total_events if total_events else 0.0
    )
    spy_coverage = len(observed_spy & expected_spy) / len(expected_spy) if expected_spy else 0.0

    coverage_by_year: dict[str, float | None] = {}
    observed_year_coverages: list[float] = []
    for year, values in year_stats.items():
        boundary = int(values.get("evaluationStudyBoundaryRightCensored", 0)) + int(
            values.get("entryStudyBoundaryRightCensored", 0)
        )
        assessable = int(values.get("identityEligible", 0)) - boundary
        matched = int(values.get("entryMatched", 0))
        coverage = matched / assessable if assessable else None
        coverage_by_year[str(year)] = coverage
        if coverage is not None:
            observed_year_coverages.append(coverage)
    worst_year_coverage = min(observed_year_coverages) if observed_year_coverages else 0.0

    metrics = {
        "entryCoverage": entry_coverage,
        "identityMissing": identity_missing_rate,
        "identityAmbiguity": identity_ambiguity_rate,
        "totalIdentityProblem": total_identity_problem_rate,
        "worstYearEntryCoverage": worst_year_coverage,
        "spyCoverage": spy_coverage,
    }
    tier, tier_checks = select_data_quality_tier(metrics)
    research_gate_pass = tier != "FAIL_BELOW_EXPLORATORY"

    collisions = [
        {"ticker": ticker, "evaluationSession": session, "issuerCiks": ciks}
        for (ticker, session), ciks in sorted(sec_diag.pop("collisions").items())
    ]
    (output / "identity-collisions.json").write_text(
        json.dumps(collisions, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "terminal-tails.json").write_text(
        json.dumps(terminal_tails, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    missing_ranked = [
        {"ticker": ticker, "qualifiedIssuerSessionsMissingExactEntry": count}
        for ticker, count in sorted(missing_tickers.items(), key=lambda item: (-item[1], item[0]))
    ]
    (output / "missing-entry-tickers.json").write_text(
        json.dumps(missing_ranked, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    summary: dict[str, Any] = {
        "schemaVersion": "2.1.0",
        "dataset": "Exact-XNYS issuer-session market coverage and terminal audit",
        "period": "2016-2022",
        "baselineUniverse": "non-derivative open-market purchase P/A",
        "eventUnit": "issuer CIK + first eligible XNYS evaluation session",
        "executionClock": (
            "knowledgeAt -> first eligible XNYS evaluation close -> exact next XNYS session open"
        ),
        "horizonClock": "exact entry XNYS session + 21/63/126/252 XNYS sessions",
        "horizonsSessions": list(v1.HORIZONS),
        "sec": sec_diag,
        "market": market_diag,
        "entry": {
            "qualifiedIssuerSessionEvents": total_events,
            "issuerSessionEventsWithUsableTicker": usable_ticker,
            "identityMissingOrPlaceholderEvents": identity_missing,
            "identityAmbiguousEvents": ambiguous_total,
            "identityEligibleEvents": identity_eligible,
            "studyBoundaryRightCensoredBeforeEntry": entry_boundary_censored_total,
            "identityEligibleAssessableForEntry": entry_assessable,
            "entryMatchedEvents": entry_matched_total,
            "eligibleExactEntryCoverage": entry_coverage,
            "identityMissingOrPlaceholderRate": identity_missing_rate,
            "identityAmbiguousRateAmongUsableTickered": identity_ambiguity_rate,
            "totalIdentityProblemRate": total_identity_problem_rate,
            "entryCoverageByKnowledgeYear": coverage_by_year,
            "worstYearExactEntryCoverage": worst_year_coverage,
        },
        "splits": {key: dict(value) for key, value in split_stats.items()},
        "yearStats": {str(year): dict(value) for year, value in year_stats.items()},
        "horizonAvailability": {
            split: {str(horizon): dict(values) for horizon, values in horizons.items()}
            for split, horizons in horizon_stats.items()
        },
        "spy": {
            "expectedSessions": len(expected_spy),
            "observedRegularSessions": len(observed_spy & expected_spy),
            "coverage": spy_coverage,
            "missingSessions": missing_spy,
            "extraSessions": extra_spy,
        },
        "terminalAudit": {
            "terminalTailSymbols": len(terminal_tails),
            "qualifiedEventsTouchingTerminalTail": terminal_interaction_events,
            "terminalRowsExcludedFromRegularSessions": True,
            "missingOutcomesImputed": False,
        },
        "dataQualityGate": {
            "tier": tier,
            "metrics": metrics,
            "thresholds": TIER_THRESHOLDS,
            "checks": tier_checks,
            "invariants": {
                "oosClosed": True,
                "exactXnysEntrySessionRequired": True,
                "exactXnysHorizonSessionRequired": True,
                "studyBoundaryCensoringExcludedFromEntryCoverage": True,
                "terminalRowsExcludedFromRegularSessions": True,
                "missingOutcomesNotImputed": True,
            },
        },
        "gateRecommendation": {
            "A_HIGH_CONFIDENCE": "PASS_HIGH_CONFIDENCE",
            "B_RESEARCH_GRADE": "PASS_RESEARCH_GRADE",
            "C_EXPLORATORY": "PASS_EXPLORATORY",
        }.get(tier, "REVIEW_ATTRITION"),
        "marketDataJoined": research_gate_pass,
        "highConfidenceMarketDataJoined": tier == "A_HIGH_CONFIDENCE",
        "canonicalReady": False,
        "signalReady": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "researchOnly": True,
        "status": "MARKET_ISSUER_SESSION_AUDIT_V2_COMPLETE",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
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
