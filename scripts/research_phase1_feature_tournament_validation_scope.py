"""Freeze the outcome-blind 2021-2022 validation scope for confirmed F2."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from datetime import UTC
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import pandas as pd
import research_market_event_audit as market_audit
import research_market_event_audit_v2 as p0
import research_phase1_feature_tournament_stage_a as stage_a

VALIDATION_START = "2021-01-01"
VALIDATION_END = "2022-12-31"
OUTCOME_BOUNDARY = "2022-12-31"
PRIMARY_HORIZON = 126
DEDUP_SESSIONS = 20
SEALED_YEAR = 2023


def _scope_digest(rows: list[dict[str, Any]]) -> str:
    fields = (
        "eventNumber",
        "issuerCik",
        "ticker",
        "evaluationSession",
        "entrySession",
        "targetExitSession",
        "F2_DIRECT_VS_INDIRECT",
    )
    material = [
        {field: row[field] for field in fields}
        for row in rows
    ]
    raw = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _candidate_stream(
    sec_effective: Path,
) -> list[dict[str, Any]]:
    events_by_ticker, _ = market_audit._load_events(sec_effective)
    sessions = p0._expected_sessions()

    candidates: list[dict[str, Any]] = []
    for ticker, events in events_by_ticker.items():
        for event in events:
            if event["identityAmbiguous"]:
                continue
            evaluation = str(event["evaluationSession"])
            if evaluation >= f"{SEALED_YEAR}-01-01":
                continue
            index = session_index.get(evaluation)
            if index is None:
                continue
            candidates.append(
                {
                    **event,
                    "ticker": ticker,
                    "evaluationIndex": index,
                }
            )

    candidates.sort(
        key=lambda row: (
            int(row["evaluationIndex"]),
            str(row["knowledgeAtFirst"]),
            str(row["issuerCik"]),
            str(row["ticker"]),
        )
    )

    retained: list[dict[str, Any]] = []
    last_by_issuer: dict[str, int] = {}
    for event in candidates:
        cik = str(event["issuerCik"])
        index = int(event["evaluationIndex"])
        previous = last_by_issuer.get(cik)
        if previous is not None and index - previous <= DEDUP_SESSIONS:
            continue
        last_by_issuer[cik] = index
        retained.append(event)
    return retained


def _f2_category(
    event: dict[str, Any],
    issuer_rows: list[dict[str, Any]],
    calendar: Any,
) -> str:
    evaluation = str(event["evaluationSession"])
    cutoff = calendar.session_close(
        pd.Timestamp(evaluation)
    ).to_pydatetime()
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)
    cutoff = cutoff.astimezone(UTC)

    active = stage_a._active_purchases(issuer_rows, cutoff)
    ownerships: set[str] = set()
    for row in active:
        row_session = market_audit._evaluation_session(
            row["_knowledge"].isoformat(),
            calendar,
        )
        if row_session != evaluation:
            continue
        ownership = str(
            (row.get("transaction") or {}).get("ownershipNature") or ""
        ).upper()
        if ownership in {"D", "I"}:
            ownerships.add(ownership)

    if ownerships == {"D"}:
        return "DIRECT_ONLY"
    if ownerships == {"I"}:
        return "INDIRECT_ONLY"
    if ownerships == {"D", "I"}:
        return "MIXED"
    return "UNKNOWN"


def _assert_confirmation(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "status": "PHASE1_INSIDER_FEATURE_TOURNAMENT_CONFIRMATION_COMPLETE",
        "definitionId": "PHASE1_INSIDER_FEATURE_TOURNAMENT_V1",
        "confirmedCandidateCount": 1,
        "confirmationComplete": True,
        "validationOpened": False,
        "validationEventOutcomesRead": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"confirmation contract mismatch: {key}")
    confirmed = payload.get("confirmedCandidates")
    if confirmed != [
        {
            "family": "F2",
            "variantId": "F2_DIRECT_VS_INDIRECT",
            "coverageClass": "GENERAL_ELIGIBLE",
            "frozenGroupDefinition": {
                "kind": "F2_DYNAMIC",
                "sourceFeature": "F2_DIRECT_VS_INDIRECT",
                "preferred": "INDIRECT_ONLY",
                "complement": "DIRECT_ONLY",
            },
        }
    ]:
        raise ValueError("confirmed candidate changed")


def run(
    *,
    confirmation_results: Path,
    sec_effective: Path,
    sec_revisions: Path,
    market_root: Path,
    output: Path,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    _assert_confirmation(confirmation_results)
    if (market_root / "2023").exists():
        raise ValueError("sealed 2023 market directory mounted")

    paths = stage_a._market_paths(
        market_root,
        "canonical-market",
        range(2016, 2023),
    )
    db_path = output / "validation-scope.sqlite"
    stage_a._build_market_db(paths, db_path)

    retained = _candidate_stream(sec_effective)
    validation_candidates = [
        row
        for row in retained
        if VALIDATION_START
        <= str(row["evaluationSession"])
        <= VALIDATION_END
    ]
    issuers = {
        str(row["issuerCik"])
        for row in validation_candidates
    }
    revisions = stage_a._load_revisions(sec_revisions, issuers)
    calendar = xcals.get_calendar("XNYS")
    sessions = p0._expected_sessions()
    session_index = {day: idx for idx, day in enumerate(sessions)}

    conn = sqlite3.connect(db_path)
    rows: list[dict[str, Any]] = []
    right_censored = 0
    missing_entry = 0
    try:
        spy = {
            str(row[0]): row
            for row in conn.execute(
                "SELECT date,open,high,low,close,volume,trade_count,terminal "
                "FROM market WHERE ticker='SPY' ORDER BY date"
            ).fetchall()
        }
        for event in validation_candidates:
            evaluation = str(event["evaluationSession"])
            evaluation_index = int(event["evaluationIndex"])
            entry_index = evaluation_index + 1
            target_index = entry_index + PRIMARY_HORIZON
            if entry_index >= len(sessions):
                right_censored += 1
                continue
            entry = sessions[entry_index]
            if target_index >= len(sessions):
                right_censored += 1
                continue
            target = sessions[target_index]
            if target > OUTCOME_BOUNDARY:
                right_censored += 1
                continue

            stock_entry = conn.execute(
                "SELECT date,open,high,low,close,volume,trade_count,terminal "
                "FROM market WHERE ticker=? AND date=?",
                (str(event["ticker"]).upper(), entry),
            ).fetchone()
            if not stage_a._regular(stock_entry) or not stage_a._regular(
                spy.get(entry)
            ):
                missing_entry += 1
                continue

            f2 = _f2_category(
                event,
                revisions.get(str(event["issuerCik"]), []),
                calendar,
            )
            rows.append(
                {
                    "eventNumber": len(rows) + 1,
                    "issuerCik": str(event["issuerCik"]),
                    "ticker": str(event["ticker"]).upper(),
                    "evaluationSession": evaluation,
                    "entrySession": entry,
                    "horizon": PRIMARY_HORIZON,
                    "targetExitSession": target,
                    "F2_DIRECT_VS_INDIRECT": (
                        f2 if f2 in {"DIRECT_ONLY", "INDIRECT_ONLY"} else ""
                    ),
                    "F2_OWNERSHIP_CATEGORY": f2,
                }
            )
    finally:
        conn.close()
        db_path.unlink(missing_ok=True)

    if not rows:
        raise ValueError("validation scope is empty")
    if any(
        not VALIDATION_START
        <= row["evaluationSession"]
        <= VALIDATION_END
        for row in rows
    ):
        raise ValueError("non-validation event entered scope")
    if any(row["targetExitSession"] > OUTCOME_BOUNDARY for row in rows):
        raise ValueError("validation target crossed sealed outcome boundary")

    scope_path = output / "validation-scope.csv"
    with scope_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(rows[0]),
        )
        writer.writeheader()
        writer.writerows(rows)

    f2_observed = [
        row
        for row in rows
        if row["F2_DIRECT_VS_INDIRECT"]
    ]
    summary = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_VALIDATION_SCOPE_FROZEN",
        "definitionId": "PHASE1_INSIDER_FEATURE_TOURNAMENT_V1",
        "confirmedCandidate": "F2_DIRECT_VS_INDIRECT",
        "frozenPreferred": "INDIRECT_ONLY",
        "frozenComplement": "DIRECT_ONLY",
        "researchOnly": True,
        "outcomesRead": False,
        "priceOutcomeFieldsRead": [],
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "validationEvaluationPeriod": [
            VALIDATION_START,
            VALIDATION_END,
        ],
        "outcomeBoundary": OUTCOME_BOUNDARY,
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "dedupSessions": DEDUP_SESSIONS,
        "validationCandidatesAfterCrossPeriodDedup": len(
            validation_candidates
        ),
        "rightCensoredBeforeOutcomeRead": right_censored,
        "missingExactEntryBeforeOutcomeRead": missing_entry,
        "validationScopeRows": len(rows),
        "validationDistinctIssuers": len(
            {row["issuerCik"] for row in rows}
        ),
        "f2ObservedRows": len(f2_observed),
        "f2ObservedDistinctIssuers": len(
            {row["issuerCik"] for row in f2_observed}
        ),
        "f2CategoryCounts": dict(
            sorted(
                {
                    category: sum(
                        row["F2_OWNERSHIP_CATEGORY"] == category
                        for row in rows
                    )
                    for category in (
                        "DIRECT_ONLY",
                        "INDIRECT_ONLY",
                        "MIXED",
                        "UNKNOWN",
                    )
                }.items()
            )
        ),
        "scopeKeySha256": _scope_digest(rows),
        "nextGate": (
            "Run performance-blind security continuity on this exact "
            "validation event/126-session scope to zero unresolved."
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation-results", type=Path, required=True)
    parser.add_argument("--sec-effective", type=Path, required=True)
    parser.add_argument("--sec-revisions", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                confirmation_results=args.confirmation_results,
                sec_effective=args.sec_effective,
                sec_revisions=args.sec_revisions,
                market_root=args.market_root,
                output=args.output,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
