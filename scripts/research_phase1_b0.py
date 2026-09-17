"""Phase-1 B0 development baseline: any qualified PIT insider purchase.

Research-only descriptive runner. Selection is restricted to 2016-2020 events, exact
XNYS sessions define evaluation/entry/horizons, 2023+ market outcomes are never read,
and no production scoring object is created or modified.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

import research_market_event_audit as v1
import research_market_event_audit_v2 as p0

DEVELOPMENT_END_YEAR = 2020
DEDUP_SESSIONS = 20
PRIMARY_HORIZON = 126


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _regular(row: tuple[Any, ...] | None) -> bool:
    return row is not None and not bool(row[7]) and int(row[5]) > 0 and int(row[6]) > 0


def _aggregate(rows: list[dict[str, Any]], horizon: int) -> dict[str, Any]:
    matured = [row for row in rows if row[f"excess_{horizon}"] is not None]
    raw = [float(row[f"raw_{horizon}"]) for row in matured]
    excess = [float(row[f"excess_{horizon}"]) for row in matured]
    mae = [
        float(row[f"mae_{horizon}"])
        for row in matured
        if row[f"mae_{horizon}"] is not None
    ]
    return {
        "horizonSessions": horizon,
        "maturedOutcomeCount": len(matured),
        "distinctIssuers": len({str(row["issuerCik"]) for row in matured}),
        "rawReturnMean": statistics.fmean(raw) if raw else None,
        "rawReturnMedian": statistics.median(raw) if raw else None,
        "spyExcessMean": statistics.fmean(excess) if excess else None,
        "spyExcessMedian": statistics.median(excess) if excess else None,
        "spyExcessWinRate": (
            sum(value > 0 for value in excess) / len(excess) if excess else None
        ),
        "spyExcessP05": _percentile(excess, 0.05),
        "spyExcessP10": _percentile(excess, 0.10),
        "maeObservedCount": len(mae),
        "maeMean": statistics.fmean(mae) if mae else None,
        "maeMedian": statistics.median(mae) if mae else None,
    }


def run(*, sec_path: Path, market_root: Path, p0_summary: Path, output: Path) -> dict[str, Any]:
    p0_data = json.loads(p0_summary.read_text(encoding="utf-8"))
    tier = str(p0_data["dataQualityGate"]["tier"])
    if tier == "FAIL_BELOW_EXPLORATORY":
        raise ValueError("P0 exact-calendar data-quality gate is below Tier C")
    if p0_data.get("oosOpened") is not False:
        raise ValueError("P0 artifact violates sealed OOS boundary")

    output.mkdir(parents=True, exist_ok=True)
    events_by_ticker, sec_diag = v1._load_events(sec_path)
    market_files = v1._market_files(market_root)
    sessions = p0._expected_sessions()
    session_index = {day: index for index, day in enumerate(sessions)}

    db_path = output / "phase1-b0.sqlite"
    db_path.unlink(missing_ok=True)
    v1._build_market_db(market_files, db_path)

    candidates: list[dict[str, Any]] = []
    for ticker, events in events_by_ticker.items():
        for event in events:
            if int(event["knowledgeYear"]) > DEVELOPMENT_END_YEAR:
                continue
            if event["identityAmbiguous"]:
                continue
            evaluation_session = str(event["evaluationSession"])
            index = session_index.get(evaluation_session)
            if index is None:
                continue
            candidates.append({**event, "ticker": ticker, "evaluationIndex": index})
    candidates.sort(
        key=lambda row: (
            int(row["evaluationIndex"]),
            str(row["knowledgeAtFirst"]),
            str(row["issuerCik"]),
            str(row["ticker"]),
        )
    )

    retained: list[dict[str, Any]] = []
    duplicate_count = 0
    last_by_issuer: dict[str, int] = {}
    annual: dict[int, dict[str, int]] = {
        year: defaultdict(int) for year in range(v1.START_YEAR, DEVELOPMENT_END_YEAR + 1)
    }
    for event in candidates:
        year = int(event["knowledgeYear"])
        annual[year]["identityEligibleCandidates"] += 1
        cik = str(event["issuerCik"])
        index = int(event["evaluationIndex"])
        previous = last_by_issuer.get(cik)
        if previous is not None and index - previous <= DEDUP_SESSIONS:
            duplicate_count += 1
            annual[year]["dedupSuppressed"] += 1
            continue
        last_by_issuer[cik] = index
        retained.append(event)
        annual[year]["retainedAfterDedup"] += 1

    conn = sqlite3.connect(db_path)
    event_rows: list[dict[str, Any]] = []
    entry_missing = 0
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
            year = int(event["knowledgeYear"])
            evaluation_index = int(event["evaluationIndex"])
            entry_index = evaluation_index + 1
            if entry_index >= len(sessions):
                annual[year]["entryStudyBoundaryRightCensored"] += 1
                entry_missing += 1
                continue

            entry_session = sessions[entry_index]
            ticker = str(event["ticker"])
            stock = rows_by_ticker[ticker]
            entry = stock.get(entry_session)
            spy_entry = spy.get(entry_session)
            if not _regular(entry) or not _regular(spy_entry):
                annual[year]["missingExactEntry"] += 1
                entry_missing += 1
                continue

            annual[year]["entryMatched"] += 1
            entry_open = float(entry[1])
            spy_entry_open = float(spy_entry[1])
            result: dict[str, Any] = {
                "issuerCik": str(event["issuerCik"]),
                "ticker": ticker,
                "knowledgeYear": year,
                "knowledgeAtFirst": str(event["knowledgeAtFirst"]),
                "evaluationSession": str(event["evaluationSession"]),
                "entrySession": entry_session,
                "entryOpen": entry_open,
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
                if not _regular(exit_row):
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
                if not _regular(spy_exit):
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
                if all(_regular(row) for row in path_rows):
                    path_low = min(
                        float(row[3]) for row in path_rows if row is not None
                    )
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

    fieldnames = [
        "issuerCik",
        "ticker",
        "knowledgeYear",
        "knowledgeAtFirst",
        "evaluationSession",
        "entrySession",
        "entryOpen",
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

    horizon_results = {
        str(horizon): _aggregate(event_rows, horizon) for horizon in v1.HORIZONS
    }
    annual_summary: dict[str, dict[str, Any]] = {}
    for year, values in annual.items():
        retained_count = int(values.get("retainedAfterDedup", 0))
        matched = int(values.get("entryMatched", 0))
        annual_summary[str(year)] = {
            **dict(values),
            "exactEntryCoverageAfterDedup": matched / retained_count if retained_count else None,
        }

    summary: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "benchmark": "B0_ANY_QUALIFIED_PURCHASE",
        "status": "PHASE1_B0_DEVELOPMENT_DESCRIPTIVE_COMPLETE",
        "period": "2016-2020 event cohort",
        "outcomeMarketBoundary": "2016-2022 only",
        "p0DataQualityTier": tier,
        "eventUnit": "issuer CIK + eligible XNYS evaluation session",
        "dedupSessions": DEDUP_SESSIONS,
        "dedupKey": "issuer CIK",
        "executionClock": (
            "knowledgeAt -> first eligible XNYS close -> exact next XNYS session open"
        ),
        "horizonsSessions": list(v1.HORIZONS),
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "selection": {
            "qualifiedIssuerSessionEvents2016To2022": int(
                sec_diag["qualifiedIssuerSessionEvents"]
            ),
            "developmentIdentityEligibleCandidates": len(candidates),
            "dedupSuppressed": duplicate_count,
            "retainedAfterDedup": len(retained),
            "exactEntryMatched": len(event_rows),
            "entryAttrition": entry_missing,
            "distinctIssuersWithEntry": len({row["issuerCik"] for row in event_rows}),
        },
        "annual": annual_summary,
        "horizons": horizon_results,
        "interpretation": (
            "Development plumbing/descriptive result only. No formal alpha PASS; dependence-aware "
            "calendar-time/HAC and clustered robustness are required before formal evidence."
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
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--p0-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(
        sec_path=args.sec,
        market_root=args.market_root,
        p0_summary=args.p0_summary,
        output=args.output,
    )


if __name__ == "__main__":
    main()
