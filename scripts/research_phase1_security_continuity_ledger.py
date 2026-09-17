"""Build a performance-blind security-continuity ledger for Phase-1 events.

The runner uses only event identity/date metadata, bounded corporate actions and
presence/absence of adjusted market bars. It deliberately ignores all realized
return and MAE fields. Corrected performance is a later, separately gated stage.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import research_market_event_audit as market_audit

HORIZONS = (21, 63, 126, 252)
SEALED_YEAR = 2023
LONG_GAP_SESSIONS = 10

AUTO_ADJUSTED_BUCKETS = frozenset(
    {"forward_splits", "reverse_splits", "cash_dividends", "spin_offs"}
)
CANDIDATE_BUCKETS = frozenset(
    {
        "unit_splits",
        "stock_dividends",
        "cash_mergers",
        "stock_mergers",
        "stock_and_cash_mergers",
        "redemptions",
        "name_changes",
        "worthless_removals",
        "rights_distributions",
    }
)


def _load_events(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = list(reader.fieldnames or [])
        required = {
            "issuerCik",
            "ticker",
            "evaluationSession",
            "entrySession",
            *(f"exit_{horizon}" for horizon in HORIZONS),
        }
        if not required.issubset(fieldnames):
            raise ValueError("event file missing required identity/date fields")
        rows: list[dict[str, str]] = []
        for raw in reader:
            row = {field: str(raw.get(field) or "").strip() for field in required}
            for field in ("evaluationSession", "entrySession", *(f"exit_{h}" for h in HORIZONS)):
                value = row[field]
                if value and int(value[:4]) >= SEALED_YEAR:
                    raise ValueError("sealed OOS boundary violated by event metadata")
            rows.append(row)
    if not rows:
        raise ValueError("event file is empty")
    performance_columns = sorted(
        field
        for field in fieldnames
        if field.startswith(("raw_", "excess_", "mae_"))
    )
    return rows, performance_columns


def _load_actions(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("performanceRead") is not False:
        raise ValueError("corporate-action inventory is not performance-blind")
    if payload.get("oosOpened") is not False:
        raise ValueError("corporate-action inventory opened OOS")
    actions = payload.get("actions")
    if not isinstance(actions, list):
        raise ValueError("corporate-action inventory missing actions")
    for action in actions:
        date_value = str(action.get("actionDate") or "")
        if date_value and int(date_value[:4]) >= SEALED_YEAR:
            raise ValueError("sealed OOS boundary violated by corporate action")
    return actions


def _load_fixtures(path: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("performanceRead") is not False:
        raise ValueError("fixture file is not performance-blind")
    fixtures: dict[tuple[str, str, str], dict[str, Any]] = {}
    for fixture in payload.get("fixtures", []):
        effective = str(fixture["effectiveDate"])
        if int(effective[:4]) >= SEALED_YEAR:
            raise ValueError("sealed OOS boundary violated by fixture")
        key = (
            str(fixture["issuerCik"]),
            str(fixture["ticker"]).upper(),
            str(fixture["entrySession"]),
        )
        fixtures[key] = fixture
    return fixtures


def _affected_symbol(action: dict[str, Any]) -> str:
    bucket = str(action.get("bucket") or "")
    if bucket == "name_changes":
        return str(action.get("old_symbol") or "").upper()
    if bucket in {"cash_mergers", "stock_mergers", "stock_and_cash_mergers"}:
        return str(action.get("acquiree_symbol") or "").upper()
    return str(action.get("symbol") or "").upper()


def _index_actions(actions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for action in actions:
        symbol = _affected_symbol(action)
        if symbol:
            indexed[symbol].append(action)
    for rows in indexed.values():
        rows.sort(key=lambda row: (str(row.get("actionDate") or ""), str(row.get("id") or "")))
    return indexed


def _candidate_actions(
    actions: list[dict[str, Any]], entry: str, exit_session: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    in_window = [
        action
        for action in actions
        if entry < str(action.get("actionDate") or "") <= exit_session
    ]
    candidates = [
        action for action in in_window if str(action.get("bucket") or "") in CANDIDATE_BUCKETS
    ]
    diagnostics = [
        action
        for action in in_window
        if str(action.get("bucket") or "") in AUTO_ADJUSTED_BUCKETS
    ]
    return candidates, diagnostics


def _provider_state(actions: list[dict[str, Any]]) -> tuple[str, str | None]:
    if not actions:
        return "PRICE_CONTINUOUS_ADJUSTED", None
    if len(actions) != 1:
        return "UNRESOLVED_CONTINUITY", None
    action = actions[0]
    bucket = str(action.get("bucket") or "")
    if bucket == "name_changes":
        old_cusip = str(action.get("old_cusip") or "")
        new_cusip = str(action.get("new_cusip") or "")
        successor = str(action.get("new_symbol") or "").upper() or None
        if old_cusip and old_cusip == new_cusip and successor:
            return "SYMBOL_CHANGED_SAME_SECURITY", successor
        return "UNRESOLVED_CONTINUITY", successor
    if bucket == "cash_mergers" and action.get("rate") is not None:
        return "TRANSFORMED_HOLDER_CONSIDERATION", None
    if bucket == "stock_mergers":
        if action.get("acquirer_rate") is not None and action.get("acquiree_rate") is not None:
            return "TRANSFORMED_HOLDER_CONSIDERATION", str(
                action.get("acquirer_symbol") or ""
            ).upper() or None
    if bucket == "stock_and_cash_mergers":
        if (
            action.get("acquirer_rate") is not None
            and action.get("acquiree_rate") is not None
            and action.get("cash_rate") is not None
        ):
            return "TRANSFORMED_HOLDER_CONSIDERATION", str(
                action.get("acquirer_symbol") or ""
            ).upper() or None
    if bucket == "redemptions" and action.get("rate") is not None:
        return "TRANSFORMED_HOLDER_CONSIDERATION", None
    if bucket == "worthless_removals":
        return "DISCONTINUOUS_NO_COMPLETE_VALUATION", None
    return "UNRESOLVED_CONTINUITY", None


def _max_internal_gap(
    observed_indices: list[int], start_index: int, end_index: int
) -> int:
    left = bisect.bisect_left(observed_indices, start_index)
    right = bisect.bisect_right(observed_indices, end_index)
    bounded = observed_indices[left:right]
    if len(bounded) < 2:
        return 0
    return max(
        next_index - index - 1
        for index, next_index in zip(bounded, bounded[1:], strict=False)
    )


def _fixture_state(
    fixture: dict[str, Any] | None, entry: str, exit_session: str
) -> tuple[str | None, str | None]:
    if fixture is None:
        return None, None
    effective = str(fixture["effectiveDate"])
    if not (entry < effective <= exit_session):
        return None, None
    return str(fixture["correctionState"]), str(fixture.get("successorSymbol") or "") or None


def run(
    *,
    events_path: Path,
    corporate_actions_path: Path,
    fixtures_path: Path,
    market_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    events, performance_columns = _load_events(events_path)
    actions = _load_actions(corporate_actions_path)
    fixtures = _load_fixtures(fixtures_path)
    actions_by_symbol = _index_actions(actions)

    calendar = xcals.get_calendar("XNYS")
    sessions = [
        str(value.date())
        for value in calendar.sessions_in_range("2016-01-01", "2022-12-31")
    ]
    session_index = {day: index for index, day in enumerate(sessions)}

    market_files = market_audit._market_files(market_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "continuity-market.sqlite"
    db_path.unlink(missing_ok=True)
    market_audit._build_market_db(market_files, db_path)

    conn = sqlite3.connect(db_path)
    observed_by_ticker: dict[str, list[int]] = {}
    ledger: list[dict[str, Any]] = []
    try:
        for ticker in sorted({row["ticker"].upper() for row in events}):
            rows = conn.execute(
                "SELECT date FROM market WHERE ticker=? AND terminal=0 "
                "AND volume>0 AND trade_count>0 ORDER BY date",
                (ticker,),
            ).fetchall()
            observed_by_ticker[ticker] = [
                session_index[str(row[0])]
                for row in rows
                if str(row[0]) in session_index
            ]

        for event_number, event in enumerate(events, start=1):
            ticker = event["ticker"].upper()
            entry = event["entrySession"]
            entry_index = session_index.get(entry)
            if entry_index is None:
                raise ValueError("entry session outside frozen XNYS calendar")
            fixture = fixtures.get((event["issuerCik"], ticker, entry))
            symbol_actions = actions_by_symbol.get(ticker, [])

            for horizon in HORIZONS:
                exit_session = event[f"exit_{horizon}"]
                if not exit_session:
                    continue
                exit_index = session_index.get(exit_session)
                if exit_index is None:
                    raise ValueError("exit session outside frozen XNYS calendar")

                candidates, adjusted_actions = _candidate_actions(
                    symbol_actions, entry, exit_session
                )
                state, successor = _provider_state(candidates)
                fixture_state, fixture_successor = _fixture_state(
                    fixture, entry, exit_session
                )
                resolution_source = "provider"
                if fixture_state is not None:
                    state = fixture_state
                    successor = fixture_successor
                    resolution_source = "verified_fixture"

                gap = _max_internal_gap(
                    observed_by_ticker.get(ticker, []), entry_index, exit_index
                )
                long_gap = gap >= LONG_GAP_SESSIONS
                if long_gap and state == "PRICE_CONTINUOUS_ADJUSTED":
                    state = "UNRESOLVED_CONTINUITY"
                    resolution_source = "long_internal_gap"

                ledger.append(
                    {
                        "eventNumber": event_number,
                        "issuerCik": event["issuerCik"],
                        "ticker": ticker,
                        "evaluationSession": event["evaluationSession"],
                        "entrySession": entry,
                        "horizon": horizon,
                        "targetExitSession": exit_session,
                        "state": state,
                        "successorSymbol": successor or "",
                        "resolutionSource": resolution_source,
                        "candidateActionTypes": ";".join(
                            sorted({str(action.get("bucket")) for action in candidates})
                        ),
                        "adjustedActionTypes": ";".join(
                            sorted({str(action.get("bucket")) for action in adjusted_actions})
                        ),
                        "candidateActionIds": ";".join(
                            str(action.get("id") or "") for action in candidates
                        ),
                        "maxInternalGapSessions": gap,
                        "longInternalGapCandidate": long_gap,
                    }
                )
    finally:
        conn.close()
        db_path.unlink(missing_ok=True)

    states = Counter(str(row["state"]) for row in ledger)
    by_horizon: dict[str, Counter[str]] = defaultdict(Counter)
    affected_years: Counter[str] = Counter()
    action_types: Counter[str] = Counter()
    affected_event_ids: set[int] = set()
    affected_issuers: set[str] = set()
    affected_tickers: set[str] = set()
    long_gap_rows = 0

    for row in ledger:
        by_horizon[str(row["horizon"])][str(row["state"])] += 1
        affected = (
            row["state"] != "PRICE_CONTINUOUS_ADJUSTED"
            or bool(row["longInternalGapCandidate"])
            or bool(row["candidateActionTypes"])
        )
        if not affected:
            continue
        affected_event_ids.add(int(row["eventNumber"]))
        affected_issuers.add(str(row["issuerCik"]))
        affected_tickers.add(str(row["ticker"]))
        affected_years[str(row["evaluationSession"])[:4]] += 1
        if row["longInternalGapCandidate"]:
            long_gap_rows += 1
        for action_type in str(row["candidateActionTypes"]).split(";"):
            if action_type:
                action_types[action_type] += 1

    ledger_path = output_dir / "continuity-ledger.csv"
    fieldnames = list(ledger[0]) if ledger else []
    with ledger_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(ledger)

    summary: dict[str, Any] = {
        "schemaVersion": 1,
        "status": "PHASE1_SECURITY_CONTINUITY_LEDGER_COMPLETE",
        "performanceRead": False,
        "performanceColumnsIgnored": performance_columns,
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "gapThresholdSessions": LONG_GAP_SESSIONS,
        "eventRowsScanned": len(events),
        "eventHorizonRows": len(ledger),
        "corporateActionsAvailable": len(actions),
        "continuityStates": dict(sorted(states.items())),
        "statesByHorizon": {
            horizon: dict(sorted(counts.items()))
            for horizon, counts in sorted(by_horizon.items())
        },
        "affectedUniqueEvents": len(affected_event_ids),
        "affectedUniqueIssuers": len(affected_issuers),
        "affectedUniqueTickers": len(affected_tickers),
        "affectedEventHorizonRowsByEvaluationYear": dict(sorted(affected_years.items())),
        "candidateActionRowsByType": dict(sorted(action_types.items())),
        "longInternalGapEventHorizonRows": long_gap_rows,
        "unresolvedEventHorizonRows": states.get("UNRESOLVED_CONTINUITY", 0),
        "performanceStageBlocked": states.get("UNRESOLVED_CONTINUITY", 0) > 0,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--corporate-actions", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        events_path=args.events,
        corporate_actions_path=args.corporate_actions,
        fixtures_path=args.fixtures,
        market_root=args.market_root,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
