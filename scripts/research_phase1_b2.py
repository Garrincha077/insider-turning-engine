"""Phase-1 B2 development baseline: independent-owner purchase clusters.

Research only. B2 is predeclared as at least two distinct reporting-owner CIKs whose
qualified open-market purchases fall within a 30-calendar-day transaction-date window.
A cluster becomes observable only on the XNYS evaluation session when the necessary
filing evidence is public. The >=3-owner subset is reported separately as B2_STRONG.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import exchange_calendars as xcals

import research_market_event_audit as v1
import research_market_event_audit_v2 as p0
import research_phase1_b0 as b0

WINDOW_DAYS = 30
IMPORTANT_OWNER_COUNT = 2
STRONG_OWNER_COUNT = 3
DEDUP_SESSIONS = 20
PRIMARY_HORIZON = 126
DEVELOPMENT_START = "2016-01-01"
DEVELOPMENT_END = "2020-12-31"
HISTORY_START_YEAR = 2015


def _real_ticker(value: object) -> str | None:
    if value is None:
        return None
    ticker = str(value).strip().upper()
    if not ticker or ticker in v1.IDENTITY_PLACEHOLDERS:
        return None
    return ticker


def _normalize_purchase_rows(sec_path: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    calendar = xcals.get_calendar("XNYS")
    rows: list[dict[str, Any]] = []
    diag: dict[str, int] = defaultdict(int)
    with sec_path.open(encoding="utf-8") as stream:
        for seq, line in enumerate(stream):
            if not line.strip():
                continue
            raw = json.loads(line)
            if not v1._qualified_purchase(raw):
                continue
            knowledge = str(raw["timestamps"]["knowledgeAt"])
            knowledge_year = int(knowledge[:4])
            if knowledge_year >= v1.SEALED_YEAR:
                raise ValueError("sealed OOS boundary violated by SEC input")
            if knowledge_year < HISTORY_START_YEAR or knowledge_year > 2020:
                continue
            diag["qualifiedRowsRead"] += 1
            issuer_cik = str(raw.get("issuer", {}).get("cik") or "")
            owner_cik = str(raw.get("reportingOwner", {}).get("cik") or "")
            tx_date = raw.get("transaction", {}).get("transactionDate")
            if not issuer_cik or not tx_date:
                diag["missingIssuerOrTransactionDate"] += 1
                continue
            if not owner_cik:
                diag["missingOwnerCik"] += 1
                continue
            evaluation_session = v1._evaluation_session(knowledge, calendar)
            rows.append(
                {
                    "sourceSeq": seq,
                    "issuerCik": issuer_cik,
                    "ownerCik": owner_cik,
                    "transactionDate": str(tx_date),
                    "knowledgeAt": knowledge,
                    "evaluationSession": evaluation_session,
                    "ticker": _real_ticker(raw.get("issuer", {}).get("ticker")),
                }
            )
    rows.sort(
        key=lambda row: (
            str(row["evaluationSession"]),
            str(row["knowledgeAt"]),
            str(row["issuerCik"]),
            int(row["sourceSeq"]),
        )
    )
    return rows, dict(diag)


def _cluster_trigger_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return PIT cluster trigger sessions without retroactive dating.

    Rows disclosed on the same evaluation session are added together. A trigger is
    emitted only if at least one newly visible row participates in a trailing 30-day
    transaction window with >=2 distinct owners. This also handles a delayed filing
    that completes the trailing window of a previously known later transaction.
    """

    by_issuer_session: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        by_issuer_session[str(row["issuerCik"])][str(row["evaluationSession"])].append(row)

    events: list[dict[str, Any]] = []
    for issuer_cik, session_rows in by_issuer_session.items():
        known: list[dict[str, Any]] = []
        for session in sorted(session_rows):
            new_rows = session_rows[session]
            known.extend(new_rows)
            new_ids = {int(row["sourceSeq"]) for row in new_rows}
            best_owners: set[str] = set()
            best_anchor: str | None = None
            for anchor in known:
                anchor_date = date.fromisoformat(str(anchor["transactionDate"]))
                start = anchor_date - timedelta(days=WINDOW_DAYS)
                members = [
                    row
                    for row in known
                    if start <= date.fromisoformat(str(row["transactionDate"])) <= anchor_date
                ]
                if not any(int(row["sourceSeq"]) in new_ids for row in members):
                    continue
                owners = {str(row["ownerCik"]) for row in members if row.get("ownerCik")}
                if len(owners) > len(best_owners):
                    best_owners = owners
                    best_anchor = anchor_date.isoformat()
            if len(best_owners) < IMPORTANT_OWNER_COUNT:
                continue
            if not (DEVELOPMENT_START <= session <= DEVELOPMENT_END):
                continue
            tickers = sorted({str(row["ticker"]) for row in new_rows if row.get("ticker")})
            events.append(
                {
                    "issuerCik": issuer_cik,
                    "evaluationSession": session,
                    "knowledgeAtFirst": min(str(row["knowledgeAt"]) for row in new_rows),
                    "knowledgeAtLast": max(str(row["knowledgeAt"]) for row in new_rows),
                    "tickers": tickers,
                    "clusterOwnerCount": len(best_owners),
                    "clusterOwnerIds": sorted(best_owners),
                    "clusterAnchorTransactionDate": best_anchor,
                    "strongCluster": len(best_owners) >= STRONG_OWNER_COUNT,
                }
            )
    events.sort(
        key=lambda row: (
            str(row["evaluationSession"]),
            str(row["knowledgeAtFirst"]),
            str(row["issuerCik"]),
        )
    )
    return events


def _identity_eligible(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    diag: dict[str, int] = defaultdict(int)
    provisional: list[dict[str, Any]] = []
    ticker_session_ciks: dict[tuple[str, str], set[str]] = defaultdict(set)
    for event in events:
        tickers = list(event["tickers"])
        if not tickers:
            diag["missingTicker"] += 1
            continue
        if len(tickers) != 1:
            diag["multipleRealTickers"] += 1
            continue
        row = {**event, "ticker": tickers[0]}
        provisional.append(row)
        ticker_session_ciks[(tickers[0], str(event["evaluationSession"]))].add(
            str(event["issuerCik"])
        )

    collisions = {
        key
        for key, ciks in ticker_session_ciks.items()
        if len({cik for cik in ciks if cik}) > 1
    }
    eligible: list[dict[str, Any]] = []
    for event in provisional:
        key = (str(event["ticker"]), str(event["evaluationSession"]))
        if key in collisions:
            diag["tickerSessionIdentityAmbiguous"] += 1
            continue
        eligible.append(event)
    diag["identityEligible"] = len(eligible)
    return eligible, dict(diag)


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
    *, retained: list[dict[str, Any]], market_files: list[Path], sessions: list[str], output: Path
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    db_path = output / "phase1-b2.sqlite"
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
                "clusterOwnerCount": int(event["clusterOwnerCount"]),
                "strongCluster": bool(event["strongCluster"]),
                "clusterAnchorTransactionDate": event["clusterAnchorTransactionDate"],
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
    b2_horizons: dict[str, dict[str, Any]], b0_summary: dict[str, Any] | None
) -> dict[str, Any]:
    if b0_summary is None:
        return {}
    result: dict[str, Any] = {}
    for horizon in v1.HORIZONS:
        key = str(horizon)
        base = b0_summary["horizons"][key]
        cluster = b2_horizons[key]
        result[key] = {
            "spyExcessMeanDelta": cluster["spyExcessMean"] - base["spyExcessMean"],
            "spyExcessMedianDelta": cluster["spyExcessMedian"] - base["spyExcessMedian"],
            "spyExcessWinRateDelta": cluster["spyExcessWinRate"] - base["spyExcessWinRate"],
            "maturedOutcomeCountRatio": (
                cluster["maturedOutcomeCount"] / base["maturedOutcomeCount"]
                if base["maturedOutcomeCount"]
                else None
            ),
        }
    return result


def run(
    *,
    sec_path: Path,
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
    rows, source_diag = _normalize_purchase_rows(sec_path)
    triggers = _cluster_trigger_events(rows)
    eligible, identity_diag = _identity_eligible(triggers)
    sessions = p0._expected_sessions()
    retained, dedup_suppressed = _deduplicate(eligible, sessions)
    market_files = v1._market_files(market_root)
    event_rows, attrition = _outcomes(
        retained=retained, market_files=market_files, sessions=sessions, output=output
    )

    fieldnames = [
        "issuerCik",
        "ticker",
        "knowledgeAtFirst",
        "evaluationSession",
        "entrySession",
        "entryOpen",
        "clusterOwnerCount",
        "strongCluster",
        "clusterAnchorTransactionDate",
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

    primary_horizons = {
        str(horizon): b0._aggregate(event_rows, horizon) for horizon in v1.HORIZONS
    }
    strong_rows = [row for row in event_rows if bool(row["strongCluster"])]
    strong_horizons = {
        str(horizon): b0._aggregate(strong_rows, horizon) for horizon in v1.HORIZONS
    }
    b0_data = (
        json.loads(b0_summary.read_text(encoding="utf-8"))
        if b0_summary is not None and b0_summary.exists()
        else None
    )

    summary: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "benchmark": "B2_INDEPENDENT_OWNER_CLUSTER",
        "status": "PHASE1_B2_DEVELOPMENT_DESCRIPTIVE_COMPLETE",
        "period": "2016-2020 XNYS evaluation-session cohort",
        "outcomeMarketBoundary": "2016-2022 only",
        "p0DataQualityTier": tier,
        "definition": {
            "windowCalendarDays": WINDOW_DAYS,
            "primaryDistinctOwnerCikMinimum": IMPORTANT_OWNER_COUNT,
            "strongDistinctOwnerCikMinimum": STRONG_OWNER_COUNT,
            "pointInTimeRule": (
                "cluster is observable only when enough qualifying purchase filings are public; "
                "trigger date is the current XNYS evaluation session, never backdated"
            ),
        },
        "eventUnit": "issuer CIK + PIT cluster-trigger XNYS evaluation session",
        "dedupSessions": DEDUP_SESSIONS,
        "dedupKey": "issuer CIK",
        "executionClock": (
            "knowledgeAt -> first eligible XNYS close -> exact next XNYS session open"
        ),
        "horizonsSessions": list(v1.HORIZONS),
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "selection": {
            "source": source_diag,
            "clusterTriggerEvents": len(triggers),
            "identity": identity_diag,
            "dedupSuppressed": dedup_suppressed,
            "retainedAfterDedup": len(retained),
            "exactEntryMatched": len(event_rows),
            "entryAttrition": attrition,
            "distinctIssuersWithEntry": len({row["issuerCik"] for row in event_rows}),
            "strongClusterEntries": len(strong_rows),
        },
        "horizons": primary_horizons,
        "strongClusterHorizons": strong_horizons,
        "comparisonVsB0": _comparison(primary_horizons, b0_data),
        "interpretation": (
            "Development descriptive result only. Compare B2 with the already frozen B0 plumbing "
            "baseline, but do not claim formal alpha until calendar-time/HAC and clustered "
            "robustness are implemented."
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
    parser.add_argument("--b0-summary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(
        sec_path=args.sec,
        market_root=args.market_root,
        p0_summary=args.p0_summary,
        b0_summary=args.b0_summary,
        output=args.output,
    )


if __name__ == "__main__":
    main()
