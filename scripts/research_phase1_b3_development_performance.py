"""Phase-1 B3 development performance under the frozen coverage-first gate.

The development event cohort is already frozen. This runner first computes
B3-specific identity/entry/SPY coverage and applies the existing P0 tier
thresholds. Forward returns are calculated only if Tier C or better passes.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

import research_market_event_audit as market_audit
import research_market_event_audit_v2 as p0
import research_phase1_b0 as b0

HORIZONS = (21, 63, 126, 252)
PRIMARY_HORIZON = 126
DEVELOPMENT_START = "2016-01-01"
DEVELOPMENT_END = "2020-12-31"
OUTCOME_END = "2022-12-31"
SEALED_YEAR = 2023
MINIMUM_TIER = "C_EXPLORATORY"
ALLOWED_TIERS = {"A_HIGH_CONFIDENCE", "B_RESEARCH_GRADE", "C_EXPLORATORY"}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _identity_metrics(
    identity_summary: dict[str, Any],
    *,
    entry_matched: int,
    annual_entry: dict[str, dict[str, int]],
    spy_coverage: float,
) -> dict[str, float]:
    total = int(identity_summary["sourceEventCount"])
    eligible = int(identity_summary["identityEligibleEvents"])
    counts = identity_summary["quarantineStatusCounts"]
    missing = int(counts.get("MISSING_REAL_TICKER", 0))
    ambiguous = int(counts.get("MULTIPLE_REAL_TICKERS", 0)) + int(
        counts.get("TICKER_SESSION_CIK_COLLISION", 0)
    )
    with_usable_ticker = total - missing
    total_identity_problem = int(identity_summary["identityQuarantineEvents"])

    yearly_coverages = []
    for values in annual_entry.values():
        denominator = int(values.get("identityEligible", 0))
        if denominator:
            yearly_coverages.append(
                int(values.get("exactEntryMatched", 0)) / denominator
            )

    return {
        "entryCoverage": entry_matched / eligible if eligible else 0.0,
        "identityMissing": missing / total if total else 0.0,
        "identityAmbiguity": (
            ambiguous / with_usable_ticker if with_usable_ticker else 0.0
        ),
        "totalIdentityProblem": (
            total_identity_problem / total if total else 0.0
        ),
        "worstYearEntryCoverage": min(yearly_coverages) if yearly_coverages else 0.0,
        "spyCoverage": spy_coverage,
    }


def _validate_event_clock(event: dict[str, Any], sessions: tuple[str, ...]) -> int:
    evaluation = str(event["evaluationSession"])
    entry = str(event["entrySession"])
    if not (DEVELOPMENT_START <= evaluation <= DEVELOPMENT_END):
        raise ValueError("B3 event outside frozen development evaluation cohort")
    session_index = {day: index for index, day in enumerate(sessions)}
    index = session_index.get(evaluation)
    if index is None:
        raise ValueError("B3 evaluation session absent from XNYS calendar")
    if index + 1 >= len(sessions) or sessions[index + 1] != entry:
        raise ValueError("B3 entry session differs from exact next XNYS session")
    if int(entry[:4]) >= SEALED_YEAR:
        raise ValueError("sealed OOS boundary violated by B3 entry")
    return index


def run(
    *,
    identity_events_path: Path,
    identity_summary_path: Path,
    definition_path: Path,
    market_root: Path,
    output: Path,
) -> dict[str, Any]:
    definition = _read_json(definition_path)
    identity_summary = _read_json(identity_summary_path)

    if definition.get("status") != "PREDECLARED_IDENTITY_PINNED_BEFORE_EXECUTION":
        raise ValueError("B3 development performance definition is not pinned")
    if not definition.get("sourceIdentityAssetSha256"):
        raise ValueError("B3 identity artifact digest is not pinned")
    if definition.get("primaryHorizonSessions") != PRIMARY_HORIZON:
        raise ValueError("B3 primary horizon changed")
    if definition.get("horizonsSessions") != list(HORIZONS):
        raise ValueError("B3 horizon family changed")
    if identity_summary.get("status") != "B3_PIT_IDENTITY_ATTACHMENT_PASS":
        raise ValueError("B3 PIT identity gate has not passed")
    if identity_summary.get("returnsRead") is not False:
        raise ValueError("B3 identity gate unexpectedly read returns")
    if identity_summary.get("oosOpened") is not False:
        raise ValueError("B3 identity gate opened OOS")
    if (market_root / "2023").exists():
        raise ValueError("sealed 2023 market directory must not be present")

    events = _read_jsonl(identity_events_path)
    if len(events) != int(identity_summary["identityEligibleEvents"]):
        raise ValueError("identity event count differs from frozen identity summary")

    sessions = p0._expected_sessions()
    session_index = {day: index for index, day in enumerate(sessions)}
    for event in events:
        _validate_event_clock(event, sessions)

    output.mkdir(parents=True, exist_ok=True)
    db_path = output / "phase1-b3-development.sqlite"
    db_path.unlink(missing_ok=True)
    market_files = market_audit._market_files(market_root)
    market_audit._build_market_db(market_files, db_path)

    conn = sqlite3.connect(db_path)
    try:
        spy_rows = conn.execute(
            "SELECT date,open,high,low,close,volume,trade_count,terminal "
            "FROM market WHERE ticker='SPY' ORDER BY date"
        ).fetchall()
        spy = {str(row[0]): row for row in spy_rows}
        regular_spy_dates = {
            day for day, row in spy.items() if b0._regular(row)
        }
        spy_coverage = len(set(sessions) & regular_spy_dates) / len(sessions)

        rows_by_ticker: dict[str, dict[str, tuple[Any, ...]]] = {}
        for ticker in sorted({str(event["ticker"]) for event in events}):
            rows = conn.execute(
                "SELECT date,open,high,low,close,volume,trade_count,terminal "
                "FROM market WHERE ticker=? ORDER BY date",
                (ticker,),
            ).fetchall()
            rows_by_ticker[ticker] = {str(row[0]): row for row in rows}

        annual: dict[str, dict[str, int]] = {
            str(year): defaultdict(int) for year in range(2016, 2021)
        }
        entry_ready: list[dict[str, Any]] = []
        entry_attrition: dict[str, int] = defaultdict(int)

        for event in events:
            year = str(event["evaluationSession"])[:4]
            annual[year]["identityEligible"] += 1
            ticker = str(event["ticker"])
            entry_session = str(event["entrySession"])
            stock_entry = rows_by_ticker[ticker].get(entry_session)
            spy_entry = spy.get(entry_session)

            if not b0._regular(stock_entry):
                annual[year]["missingExactEntry"] += 1
                entry_attrition["MISSING_EXACT_ENTRY_BAR"] += 1
                continue
            if not b0._regular(spy_entry):
                annual[year]["missingExactSpyEntry"] += 1
                entry_attrition["MISSING_EXACT_SPY_ENTRY_BAR"] += 1
                continue

            annual[year]["exactEntryMatched"] += 1
            entry_ready.append(event)

        metrics = _identity_metrics(
            identity_summary,
            entry_matched=len(entry_ready),
            annual_entry=annual,
            spy_coverage=spy_coverage,
        )
        tier, tier_checks = p0.select_data_quality_tier(metrics)

        annual_coverage = {}
        for year, values in annual.items():
            denominator = int(values.get("identityEligible", 0))
            matched = int(values.get("exactEntryMatched", 0))
            annual_coverage[year] = {
                **dict(values),
                "exactEntryCoverage": matched / denominator if denominator else None,
            }

        coverage_summary = {
            "schemaVersion": "1.0.0",
            "status": (
                "B3_MARKET_COVERAGE_PASS"
                if tier in ALLOWED_TIERS
                else "B3_MARKET_COVERAGE_FAIL_BEFORE_PERFORMANCE"
            ),
            "sourceIdentityEvents": len(events),
            "exactEntryMatched": len(entry_ready),
            "entryAttrition": len(events) - len(entry_ready),
            "entryAttritionReasonCounts": dict(sorted(entry_attrition.items())),
            "metrics": metrics,
            "tier": tier,
            "tierChecks": tier_checks,
            "annual": annual_coverage,
            "returnsRead": False,
            "oosOpened": False,
            "productionScoringChanged": False,
        }
        (output / "coverage-summary.json").write_text(
            json.dumps(coverage_summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        if tier not in ALLOWED_TIERS:
            raise ValueError(
                "B3-specific market/identity coverage is below frozen Tier C; "
                "development returns remain unopened"
            )

        result_rows: list[dict[str, Any]] = []
        for event in entry_ready:
            ticker = str(event["ticker"])
            stock = rows_by_ticker[ticker]
            evaluation_index = session_index[str(event["evaluationSession"])]
            entry_index = evaluation_index + 1
            entry_session = str(event["entrySession"])
            entry = stock[entry_session]
            spy_entry = spy[entry_session]
            entry_open = float(entry[1])
            spy_entry_open = float(spy_entry[1])

            result: dict[str, Any] = {
                "signalId": str(event["signalId"]),
                "issuerCik": str(event["issuerCik"]),
                "ticker": ticker,
                "knowledgeBoundaryAt": str(event["knowledgeBoundaryAt"]),
                "evaluationSession": str(event["evaluationSession"]),
                "entrySession": entry_session,
                "entryOpen": entry_open,
                "buyDollars": str(event["buyDollars"]),
                "saleDollars": str(event["saleDollars"]),
                "netDollars": str(event["netDollars"]),
                "grossDollars": str(event["grossDollars"]),
                "netBuyingIntensity": str(event["netBuyingIntensity"]),
            }

            for horizon in HORIZONS:
                target_index = entry_index + horizon
                raw_key = f"raw_{horizon}"
                excess_key = f"excess_{horizon}"
                mae_key = f"mae_{horizon}"
                exit_key = f"exit_{horizon}"
                reason_key = f"reason_{horizon}"

                if target_index >= len(sessions):
                    result.update(
                        {
                            exit_key: None,
                            raw_key: None,
                            excess_key: None,
                            mae_key: None,
                            reason_key: "STUDY_BOUNDARY_RIGHT_CENSORED",
                        }
                    )
                    continue

                exit_session = sessions[target_index]
                if exit_session > OUTCOME_END:
                    result.update(
                        {
                            exit_key: exit_session,
                            raw_key: None,
                            excess_key: None,
                            mae_key: None,
                            reason_key: "STUDY_BOUNDARY_RIGHT_CENSORED",
                        }
                    )
                    continue

                exit_row = stock.get(exit_session)
                spy_exit = spy.get(exit_session)
                if not b0._regular(exit_row):
                    result.update(
                        {
                            exit_key: exit_session,
                            raw_key: None,
                            excess_key: None,
                            mae_key: None,
                            reason_key: "MISSING_EXACT_EXIT_BAR",
                        }
                    )
                    continue
                if not b0._regular(spy_exit):
                    result.update(
                        {
                            exit_key: exit_session,
                            raw_key: None,
                            excess_key: None,
                            mae_key: None,
                            reason_key: "MISSING_EXACT_SPY_EXIT_BAR",
                        }
                    )
                    continue

                raw_return = float(exit_row[4]) / entry_open - 1.0
                spy_return = float(spy_exit[4]) / spy_entry_open - 1.0
                path_rows = [
                    stock.get(day)
                    for day in sessions[entry_index : target_index + 1]
                ]
                if all(b0._regular(row) for row in path_rows):
                    path_low = min(
                        float(row[3]) for row in path_rows if row is not None
                    )
                    mae = path_low / entry_open - 1.0
                else:
                    mae = None

                result.update(
                    {
                        exit_key: exit_session,
                        raw_key: raw_return,
                        excess_key: raw_return - spy_return,
                        mae_key: mae,
                        reason_key: None,
                    }
                )

            result_rows.append(result)
    finally:
        conn.close()
        db_path.unlink(missing_ok=True)

    fieldnames = [
        "signalId",
        "issuerCik",
        "ticker",
        "knowledgeBoundaryAt",
        "evaluationSession",
        "entrySession",
        "entryOpen",
        "buyDollars",
        "saleDollars",
        "netDollars",
        "grossDollars",
        "netBuyingIntensity",
    ]
    for horizon in HORIZONS:
        fieldnames.extend(
            [
                f"exit_{horizon}",
                f"raw_{horizon}",
                f"excess_{horizon}",
                f"mae_{horizon}",
                f"reason_{horizon}",
            ]
        )

    with (output / "b3-development-events.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(result_rows)

    horizons = {
        str(horizon): b0._aggregate(result_rows, horizon)
        for horizon in HORIZONS
    }
    reason_counts: dict[str, dict[str, int]] = {}
    for horizon in HORIZONS:
        counts: dict[str, int] = defaultdict(int)
        for row in result_rows:
            reason = row[f"reason_{horizon}"]
            if reason:
                counts[str(reason)] += 1
        reason_counts[str(horizon)] = dict(sorted(counts.items()))

    summary: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_B3_DEVELOPMENT_DESCRIPTIVE_COMPLETE",
        "benchmark": "B3_COMPANY_NET_BUYING_V1",
        "resultClass": "research/descriptive",
        "formalAlphaClaimed": False,
        "period": "2016-2020 XNYS evaluation-session cohort",
        "outcomeMarketBoundary": "2016-2022 only",
        "coverageTier": coverage_summary["tier"],
        "coverage": coverage_summary,
        "selection": {
            "preoutcomeEvents": int(identity_summary["sourceEventCount"]),
            "identityEligibleEvents": len(events),
            "exactEntryMatched": len(result_rows),
            "entryAttritionAfterIdentity": len(events) - len(result_rows),
            "distinctIssuersWithEntry": len(
                {str(row["issuerCik"]) for row in result_rows}
            ),
        },
        "horizonsSessions": list(HORIZONS),
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "horizons": horizons,
        "horizonAttritionReasons": reason_counts,
        "continuityCorrectionComplete": False,
        "dependenceAwareRobustnessComplete": False,
        "calendarTimeRobustnessComplete": False,
        "hacRobustnessComplete": False,
        "marketDataJoined": True,
        "returnsRead": True,
        "developmentPerformanceComputed": True,
        "validationPerformanceComputed": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "b3DefinitionChanged": False,
        "eventConstructionChanged": False,
        "identityDefinitionChanged": False,
        "interpretationGuardrail": (
            "First B3 development result is descriptive only. Missing/delisted "
            "outcomes remain explicit. No formal alpha claim is permitted before "
            "security-continuity and dependence-aware robustness work."
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity-events", type=Path, required=True)
    parser.add_argument("--identity-summary", type=Path, required=True)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    print(
        json.dumps(
            run(
                identity_events_path=args.identity_events,
                identity_summary_path=args.identity_summary,
                definition_path=args.definition,
                market_root=args.market_root,
                output=args.output,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
