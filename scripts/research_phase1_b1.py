"""Phase-1 B1 development baseline: CMP trader-level opportunistic purchases.

Research only.  The primary classifier follows Cohen, Malloy & Pomorski's annual
trader-level routine/opportunistic construction using open-market P/S history:

* At the start of calendar year Y, inspect Y-3, Y-2 and Y-1 only.
* An owner must have at least one eligible trade in each of those three years.
* A common calendar month represented in all three prior years => routine.
* Otherwise the classified owner is opportunistic.
* Once routine, routine persists.  Opportunistic persists until a later three-year
  same-month pattern appears, after which routine persists.

Only owner-month history whose first SEC filing date is strictly before January 1
of the classification year is eligible.  Current-year purchases therefore cannot
re-label themselves.  B1 signal events are qualified PIT open-market purchases by
owners classified opportunistic for the purchase's knowledge year.

Selection is development-only (2016-2020 XNYS evaluation sessions); outcomes use
2016-2022 market data and never read 2023+; production scoring is untouched.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import exchange_calendars as xcals

import research_market_event_audit as v1
import research_market_event_audit_v2 as p0
import research_phase1_b0 as b0

DEVELOPMENT_START = "2016-01-01"
DEVELOPMENT_END = "2020-12-31"
DEVELOPMENT_START_YEAR = 2016
DEVELOPMENT_END_YEAR = 2020
CLASSIFIER_HISTORY_YEARS = 3
DEDUP_SESSIONS = 20
PRIMARY_HORIZON = 126


def _load_cmp_history(root: Path) -> tuple[dict[str, dict[int, dict[int, date]]], dict[str, int]]:
    """Load and re-aggregate owner/month history across yearly extraction artifacts."""

    paths = sorted(path for path in root.rglob("*.csv") if path.is_file())
    if not paths:
        raise ValueError("no CMP owner-month CSV history found")

    earliest: dict[tuple[str, int, int], date] = {}
    rows_read = 0
    for path in paths:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"ownerCik", "tradeYear", "tradeMonth", "firstFiledDate"}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError(f"CMP history file missing required fields: {path}")
            for row in reader:
                rows_read += 1
                owner = str(row["ownerCik"]).strip().zfill(10)
                year = int(row["tradeYear"])
                month = int(row["tradeMonth"])
                filed = date.fromisoformat(str(row["firstFiledDate"]))
                if year >= v1.SEALED_YEAR or filed.year >= v1.SEALED_YEAR:
                    raise ValueError("sealed OOS boundary violated by CMP history")
                if not owner.isdigit() or len(owner) != 10 or not 1 <= month <= 12:
                    raise ValueError("invalid owner/month in CMP history")
                key = (owner, year, month)
                previous = earliest.get(key)
                if previous is None or filed < previous:
                    earliest[key] = filed

    history: dict[str, dict[int, dict[int, date]]] = defaultdict(lambda: defaultdict(dict))
    for (owner, year, month), filed in earliest.items():
        history[owner][year][month] = filed

    return history, {
        "files": len(paths),
        "rowsRead": rows_read,
        "distinctOwnerYearMonths": len(earliest),
        "distinctOwners": len(history),
    }


def _annual_classifications(
    history: dict[str, dict[int, dict[int, date]]],
    *,
    start_year: int = DEVELOPMENT_START_YEAR,
    end_year: int = DEVELOPMENT_END_YEAR,
) -> tuple[dict[tuple[str, int], str], dict[str, Any]]:
    """Classify owners at each Jan-1 boundary using only previously filed history."""

    labels: dict[tuple[str, int], str] = {}
    classified_since: dict[str, int] = {}
    routine_since: dict[str, int] = {}
    annual_counts: dict[str, dict[str, int]] = {}

    for year in range(start_year, end_year + 1):
        cutoff = date(year, 1, 1)
        counts: dict[str, int] = defaultdict(int)
        for owner in sorted(history):
            if owner in routine_since:
                labels[owner, year] = "ROUTINE"
                counts["routine"] += 1
                counts["alreadyRoutine"] += 1
                continue

            prior_years = tuple(range(year - CLASSIFIER_HISTORY_YEARS, year))
            months_by_year: list[set[int]] = []
            complete = True
            for prior_year in prior_years:
                eligible_months = {
                    month
                    for month, first_filed in history[owner].get(prior_year, {}).items()
                    if first_filed < cutoff
                }
                if not eligible_months:
                    complete = False
                months_by_year.append(eligible_months)

            common_months = set.intersection(*months_by_year) if complete else set()
            if common_months:
                labels[owner, year] = "ROUTINE"
                routine_since[owner] = year
                classified_since.setdefault(owner, year)
                counts["routine"] += 1
                counts["newlyRoutine"] += 1
                continue

            if owner in classified_since:
                labels[owner, year] = "OPPORTUNISTIC"
                counts["opportunistic"] += 1
                counts["persistedOpportunistic"] += 1
                continue

            if complete:
                labels[owner, year] = "OPPORTUNISTIC"
                classified_since[owner] = year
                counts["opportunistic"] += 1
                counts["newlyOpportunistic"] += 1
            else:
                labels[owner, year] = "UNCLASSIFIED"
                counts["unclassified"] += 1

        counts["classified"] = counts.get("routine", 0) + counts.get("opportunistic", 0)
        annual_counts[str(year)] = dict(counts)

    diagnostics = {
        "annual": annual_counts,
        "everClassifiedOwners": len(classified_since),
        "everRoutineOwners": len(routine_since),
        "everOpportunisticOwners": sum(
            any(labels.get((owner, year)) == "OPPORTUNISTIC" for year in range(start_year, end_year + 1))
            for owner in history
        ),
    }
    return labels, diagnostics


def _real_ticker(value: object) -> str | None:
    if value is None:
        return None
    ticker = str(value).strip().upper()
    if not ticker or ticker in v1.IDENTITY_PLACEHOLDERS:
        return None
    return ticker


def _load_b1_events(
    sec_path: Path,
    labels: dict[tuple[str, int], str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Build PIT issuer-session B1 events from canonical opportunistic-owner purchases."""

    calendar = xcals.get_calendar("XNYS")
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    diag: dict[str, int] = defaultdict(int)

    with sec_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if not v1._qualified_purchase(row):
                continue
            knowledge = str(row["timestamps"]["knowledgeAt"])
            knowledge_year = int(knowledge[:4])
            if knowledge_year >= v1.SEALED_YEAR:
                raise ValueError("sealed OOS boundary violated by canonical SEC input")
            if not DEVELOPMENT_START_YEAR <= knowledge_year <= DEVELOPMENT_END_YEAR:
                continue
            diag["qualifiedPurchaseRowsDevelopmentKnowledgeYears"] += 1

            owner = str(row.get("reportingOwner", {}).get("cik") or "").strip()
            if owner:
                owner = owner.zfill(10)
            label = labels.get((owner, knowledge_year), "UNCLASSIFIED")
            diag[f"ownerLabel_{label}"] += 1
            if label != "OPPORTUNISTIC":
                continue

            issuer = str(row.get("issuer", {}).get("cik") or "")
            if not issuer:
                diag["missingIssuerCik"] += 1
                continue
            evaluation = v1._evaluation_session(knowledge, calendar)
            if not (DEVELOPMENT_START <= evaluation <= DEVELOPMENT_END):
                diag["developmentBoundaryExcludedByEvaluationSession"] += 1
                continue

            key = (issuer, evaluation)
            event = grouped.setdefault(
                key,
                {
                    "issuerCik": issuer,
                    "evaluationSession": evaluation,
                    "knowledgeAtFirst": knowledge,
                    "knowledgeAtLast": knowledge,
                    "owners": set(),
                    "tickers": set(),
                    "rawOpportunisticPurchaseRows": 0,
                },
            )
            event["knowledgeAtFirst"] = min(str(event["knowledgeAtFirst"]), knowledge)
            event["knowledgeAtLast"] = max(str(event["knowledgeAtLast"]), knowledge)
            event["owners"].add(owner)
            event["rawOpportunisticPurchaseRows"] += 1
            ticker = _real_ticker(row.get("issuer", {}).get("ticker"))
            if ticker:
                event["tickers"].add(ticker)

    events: list[dict[str, Any]] = []
    ticker_session_ciks: dict[tuple[str, str], set[str]] = defaultdict(set)
    provisional: list[dict[str, Any]] = []
    for event in grouped.values():
        tickers = sorted(event.pop("tickers"))
        owners = sorted(event.pop("owners"))
        if not tickers:
            diag["eventMissingTicker"] += 1
            continue
        if len(tickers) != 1:
            diag["eventMultipleRealTickers"] += 1
            continue
        normalized = {
            **event,
            "ticker": tickers[0],
            "opportunisticOwnerCount": len(owners),
            "opportunisticOwnerIds": owners,
        }
        provisional.append(normalized)
        ticker_session_ciks[(tickers[0], str(event["evaluationSession"]))].add(
            str(event["issuerCik"])
        )

    collisions = {
        key for key, ciks in ticker_session_ciks.items() if len({cik for cik in ciks if cik}) > 1
    }
    for event in provisional:
        key = (str(event["ticker"]), str(event["evaluationSession"]))
        if key in collisions:
            diag["tickerSessionIdentityAmbiguous"] += 1
            continue
        events.append(event)

    events.sort(
        key=lambda row: (
            str(row["evaluationSession"]),
            str(row["knowledgeAtFirst"]),
            str(row["issuerCik"]),
        )
    )
    diag["opportunisticIssuerSessionEventsIdentityEligible"] = len(events)
    return events, dict(diag)


def _deduplicate(
    events: list[dict[str, Any]], sessions: list[str]
) -> tuple[list[dict[str, Any]], int]:
    session_index = {day: index for index, day in enumerate(sessions)}
    retained: list[dict[str, Any]] = []
    suppressed = 0
    last_by_issuer: dict[str, int] = {}
    for event in events:
        index = session_index.get(str(event["evaluationSession"]))
        if index is None:
            continue
        issuer = str(event["issuerCik"])
        previous = last_by_issuer.get(issuer)
        if previous is not None and index - previous <= DEDUP_SESSIONS:
            suppressed += 1
            continue
        last_by_issuer[issuer] = index
        retained.append({**event, "evaluationIndex": index})
    return retained, suppressed


def _outcomes(
    *,
    retained: list[dict[str, Any]],
    market_files: list[Path],
    sessions: list[str],
    output: Path,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    db_path = output / "phase1-b1.sqlite"
    db_path.unlink(missing_ok=True)
    v1._build_market_db(market_files, db_path)
    conn = sqlite3.connect(db_path)
    attrition: dict[str, int] = defaultdict(int)
    event_rows: list[dict[str, Any]] = []
    try:
        spy_rows = conn.execute(
            "SELECT date,open,high,low,close,volume,trade_count,terminal "
            "FROM market WHERE ticker='SPY' ORDER BY date"
        ).fetchall()
        spy = {str(row[0]): row for row in spy_rows}
        rows_by_ticker: dict[str, dict[str, tuple[Any, ...]]] = {}
        for ticker in sorted({str(event["ticker"]) for event in retained}):
            rows = conn.execute(
                "SELECT date,open,high,low,close,volume,trade_count,terminal "
                "FROM market WHERE ticker=? ORDER BY date",
                (ticker,),
            ).fetchall()
            rows_by_ticker[ticker] = {str(row[0]): row for row in rows}

        for event in retained:
            evaluation_index = int(event["evaluationIndex"])
            entry_index = evaluation_index + 1
            if entry_index >= len(sessions):
                attrition["entryStudyBoundaryRightCensored"] += 1
                continue
            entry_session = sessions[entry_index]
            ticker = str(event["ticker"])
            stock = rows_by_ticker[ticker]
            entry = stock.get(entry_session)
            spy_entry = spy.get(entry_session)
            if not b0._regular(entry) or not b0._regular(spy_entry):
                attrition["missingExactEntry"] += 1
                continue

            entry_open = float(entry[1])
            spy_entry_open = float(spy_entry[1])
            result: dict[str, Any] = {
                "issuerCik": str(event["issuerCik"]),
                "ticker": ticker,
                "knowledgeAtFirst": str(event["knowledgeAtFirst"]),
                "evaluationSession": str(event["evaluationSession"]),
                "entrySession": entry_session,
                "entryOpen": entry_open,
                "opportunisticOwnerCount": int(event["opportunisticOwnerCount"]),
                "rawOpportunisticPurchaseRows": int(event["rawOpportunisticPurchaseRows"]),
            }
            for horizon in v1.HORIZONS:
                raw_key = f"raw_{horizon}"
                excess_key = f"excess_{horizon}"
                mae_key = f"mae_{horizon}"
                exit_key = f"exit_{horizon}"
                reason_key = f"reason_{horizon}"
                target_index = entry_index + horizon
                if target_index >= len(sessions):
                    result.update(
                        {
                            raw_key: None,
                            excess_key: None,
                            mae_key: None,
                            exit_key: None,
                            reason_key: "STUDY_BOUNDARY_RIGHT_CENSORED",
                        }
                    )
                    continue
                exit_session = sessions[target_index]
                exit_row = stock.get(exit_session)
                spy_exit = spy.get(exit_session)
                if not b0._regular(exit_row):
                    result.update(
                        {
                            raw_key: None,
                            excess_key: None,
                            mae_key: None,
                            exit_key: exit_session,
                            reason_key: "MISSING_EXACT_EXIT_BAR",
                        }
                    )
                    continue
                if not b0._regular(spy_exit):
                    result.update(
                        {
                            raw_key: None,
                            excess_key: None,
                            mae_key: None,
                            exit_key: exit_session,
                            reason_key: "MISSING_EXACT_SPY_EXIT_BAR",
                        }
                    )
                    continue
                raw_return = float(exit_row[4]) / entry_open - 1.0
                spy_return = float(spy_exit[4]) / spy_entry_open - 1.0
                path_rows = [stock.get(day) for day in sessions[entry_index : target_index + 1]]
                if all(b0._regular(row) for row in path_rows):
                    path_low = min(float(row[3]) for row in path_rows if row is not None)
                    mae = path_low / entry_open - 1.0
                else:
                    mae = None
                result.update(
                    {
                        raw_key: raw_return,
                        excess_key: raw_return - spy_return,
                        mae_key: mae,
                        exit_key: exit_session,
                        reason_key: None,
                    }
                )
            event_rows.append(result)
    finally:
        conn.close()
        db_path.unlink(missing_ok=True)
    return event_rows, dict(attrition)


def _comparison(
    b1_horizons: dict[str, dict[str, Any]], b0_summary: dict[str, Any] | None
) -> dict[str, Any]:
    if b0_summary is None:
        return {}
    comparison: dict[str, Any] = {}
    for horizon in v1.HORIZONS:
        key = str(horizon)
        base = b0_summary["horizons"][key]
        current = b1_horizons[key]
        comparison[key] = {
            "spyExcessMeanDelta": current["spyExcessMean"] - base["spyExcessMean"],
            "spyExcessMedianDelta": current["spyExcessMedian"] - base["spyExcessMedian"],
            "spyExcessWinRateDelta": current["spyExcessWinRate"] - base["spyExcessWinRate"],
            "maturedOutcomeCountRatio": (
                current["maturedOutcomeCount"] / base["maturedOutcomeCount"]
                if base["maturedOutcomeCount"]
                else None
            ),
        }
    return comparison


def run(
    *,
    sec_path: Path,
    cmp_history_root: Path,
    market_root: Path,
    p0_summary: Path,
    output: Path,
    b0_summary: Path | None = None,
) -> dict[str, Any]:
    p0_data = json.loads(p0_summary.read_text(encoding="utf-8"))
    tier = str(p0_data["dataQualityGate"]["tier"])
    if tier == "FAIL_BELOW_EXPLORATORY":
        raise ValueError("P0 exact-calendar data-quality gate is below Tier C")
    if p0_data.get("oosOpened") is not False:
        raise ValueError("P0 artifact violates sealed OOS boundary")

    output.mkdir(parents=True, exist_ok=True)
    history, history_diag = _load_cmp_history(cmp_history_root)
    labels, classifier_diag = _annual_classifications(history)
    events, event_diag = _load_b1_events(sec_path, labels)
    sessions = p0._expected_sessions()
    retained, dedup_suppressed = _deduplicate(events, sessions)
    event_rows, attrition = _outcomes(
        retained=retained,
        market_files=v1._market_files(market_root),
        sessions=sessions,
        output=output,
    )

    fieldnames = [
        "issuerCik",
        "ticker",
        "knowledgeAtFirst",
        "evaluationSession",
        "entrySession",
        "entryOpen",
        "opportunisticOwnerCount",
        "rawOpportunisticPurchaseRows",
    ]
    for horizon in v1.HORIZONS:
        fieldnames.extend(
            [
                f"exit_{horizon}",
                f"raw_{horizon}",
                f"excess_{horizon}",
                f"mae_{horizon}",
                f"reason_{horizon}",
            ]
        )
    with (output / "events.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(event_rows)

    horizons = {str(horizon): b0._aggregate(event_rows, horizon) for horizon in v1.HORIZONS}
    b0_data = (
        json.loads(b0_summary.read_text(encoding="utf-8"))
        if b0_summary is not None and b0_summary.exists()
        else None
    )

    summary: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "benchmark": "B1_CMP_TRADER_LEVEL_OPPORTUNISTIC_PURCHASE",
        "status": "PHASE1_B1_DEVELOPMENT_DESCRIPTIVE_COMPLETE",
        "period": "2016-2020 XNYS evaluation-session cohort",
        "outcomeMarketBoundary": "2016-2022 only",
        "p0DataQualityTier": tier,
        "definition": {
            "classificationLevel": "reporting-owner CIK (trader level)",
            "classificationTiming": "start of each calendar year",
            "historyYears": 3,
            "historyTradeUniverse": "non-derivative open-market P/A and S/D",
            "routineRule": "at least one eligible trade in each prior year and a common calendar month across all three",
            "opportunisticRule": "at least one eligible trade in each prior year and no common calendar month across all three",
            "persistenceRule": "opportunistic persists until routine pattern emerges; routine then persists",
            "signalRule": "qualified canonical purchase by an owner classified opportunistic for knowledge year",
        },
        "historyQualityFlags": [
            "SEC_BULK_FILING_DATE_ANNUAL_CUTOFF",
            "ORIGINAL_FORMS_3_4_5_ONLY",
            "AMENDMENTS_EXCLUDED_FROM_CLASSIFIER_HISTORY",
        ],
        "eventUnit": "issuer CIK + opportunistic-purchase XNYS evaluation session",
        "dedupSessions": DEDUP_SESSIONS,
        "dedupKey": "issuer CIK",
        "executionClock": "knowledgeAt -> first eligible XNYS close -> exact next XNYS session open",
        "horizonsSessions": list(v1.HORIZONS),
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "history": history_diag,
        "classifier": classifier_diag,
        "selection": {
            "eventDiagnostics": event_diag,
            "dedupSuppressed": dedup_suppressed,
            "retainedAfterDedup": len(retained),
            "exactEntryMatched": len(event_rows),
            "entryAttrition": attrition,
            "distinctIssuersWithEntry": len({row["issuerCik"] for row in event_rows}),
        },
        "horizons": horizons,
        "comparisonVsB0": _comparison(horizons, b0_data),
        "interpretation": (
            "Development descriptive result only. CMP history uses a conservative annual filing-date "
            "cutoff and original Forms 3/4/5. Formal alpha claims require calendar-time/HAC and "
            "dependence-aware robustness; 2023+ remains sealed."
        ),
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "canonicalReady": False,
        "signalReady": False,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sec", type=Path, required=True)
    parser.add_argument("--cmp-history-root", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--p0-summary", type=Path, required=True)
    parser.add_argument("--b0-summary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(
        sec_path=args.sec,
        cmp_history_root=args.cmp_history_root,
        market_root=args.market_root,
        p0_summary=args.p0_summary,
        b0_summary=args.b0_summary,
        output=args.output,
    )


if __name__ == "__main__":
    main()
