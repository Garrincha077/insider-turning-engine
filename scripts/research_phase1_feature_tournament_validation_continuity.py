"""Audit frozen F2 validation scope continuity without reading outcomes."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import research_phase1_security_continuity_ledger as continuity
import research_phase1_security_gap_diagnostics as gaps

PRIMARY_HORIZON = 126
SEALED_YEAR = 2023
GAP_THRESHOLD = 10


def _load_scope(
    csv_path: Path,
    summary_path: Path,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    required = {
        "status": "PHASE1_FEATURE_TOURNAMENT_VALIDATION_SCOPE_FROZEN",
        "confirmedCandidate": "F2_DIRECT_VS_INDIRECT",
        "frozenPreferred": "INDIRECT_ONLY",
        "frozenComplement": "DIRECT_ONLY",
        "outcomesRead": False,
        "priceOutcomeFieldsRead": [],
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "primaryHorizonSessions": PRIMARY_HORIZON,
    }
    for key, expected in required.items():
        if summary.get(key) != expected:
            raise ValueError(f"validation scope mismatch: {key}")

    with csv_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required_fields = {
            "eventNumber",
            "issuerCik",
            "ticker",
            "evaluationSession",
            "entrySession",
            "horizon",
            "targetExitSession",
        }
        if not required_fields.issubset(reader.fieldnames or []):
            raise ValueError("validation scope CSV missing fields")
        rows = [dict(row) for row in reader]

    if len(rows) != int(summary["validationScopeRows"]):
        raise ValueError("validation scope row count changed")
    if any(int(row["horizon"]) != PRIMARY_HORIZON for row in rows):
        raise ValueError("validation scope horizon changed")
    if any(
        int(str(row["targetExitSession"])[:4]) >= SEALED_YEAR
        for row in rows
    ):
        raise ValueError("sealed OOS target entered validation scope")
    return summary, rows


def _load_actions(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("performanceRead") is not False:
        raise ValueError("corporate actions are not performance-blind")
    if payload.get("oosOpened") is not False:
        raise ValueError("corporate actions opened OOS")
    rows = payload.get("actions")
    if not isinstance(rows, list):
        raise ValueError("corporate action inventory missing actions")
    return rows



def _provider_terms_complete(
    candidate_rows: list[dict[str, Any]],
) -> bool:
    if len(candidate_rows) != 1:
        return False
    action = candidate_rows[0]
    bucket = str(action.get("bucket") or "")
    try:
        if bucket == "cash_mergers":
            return float(action["rate"]) >= 0
        if bucket == "stock_mergers":
            return (
                float(action["acquiree_rate"]) > 0
                and float(action["acquirer_rate"]) > 0
                and bool(str(action.get("acquirer_symbol") or "").strip())
            )
        if bucket == "stock_and_cash_mergers":
            return (
                float(action["acquiree_rate"]) > 0
                and float(action["acquirer_rate"]) > 0
                and float(action["cash_rate"]) >= 0
                and bool(str(action.get("acquirer_symbol") or "").strip())
            )
        if bucket == "redemptions":
            return float(action["rate"]) >= 0
    except (KeyError, TypeError, ValueError):
        return False
    return False


def run(
    *,
    scope_csv: Path,
    scope_summary: Path,
    corporate_actions: Path,
    market_root: Path,
    output: Path,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    summary, scope = _load_scope(scope_csv, scope_summary)
    actions = _load_actions(corporate_actions)
    indexed_actions = continuity._index_actions(actions)

    calendar = xcals.get_calendar("XNYS")
    sessions = [
        str(value.date())
        for value in calendar.sessions_in_range("2016-01-01", "2022-12-31")
    ]
    session_index = {day: index for index, day in enumerate(sessions)}
    wanted_tickers = {
        str(row["ticker"]).upper()
        for row in scope
    }
    observed = gaps._regular_observed_indices(
        market_root,
        wanted_tickers,
        session_index,
    )

    audit_rows: list[dict[str, Any]] = []
    for raw in scope:
        ticker = str(raw["ticker"]).upper()
        entry = str(raw["entrySession"])
        target = str(raw["targetExitSession"])
        entry_index = session_index.get(entry)
        target_index = session_index.get(target)
        if entry_index is None or target_index is None:
            raise ValueError("validation row outside frozen XNYS calendar")

        candidates, adjusted = continuity._candidate_actions(
            indexed_actions.get(ticker, []),
            entry,
            target,
        )
        state, successor = continuity._provider_state(candidates)
        source = "provider"
        if (
            state == "TRANSFORMED_HOLDER_CONSIDERATION"
            and not _provider_terms_complete(candidates)
        ):
            state = "UNRESOLVED_CONTINUITY"
            successor = None
            source = "provider_incomplete_terms"

        gap = continuity._max_internal_gap(
            observed.get(ticker, []),
            entry_index,
            target_index,
        )
        long_gap = gap >= GAP_THRESHOLD
        if long_gap and state == "PRICE_CONTINUOUS_ADJUSTED":
            state = "UNRESOLVED_CONTINUITY"
            source = "long_internal_gap"

        audit_rows.append(
            {
                "eventNumber": int(raw["eventNumber"]),
                "issuerCik": str(raw["issuerCik"]),
                "ticker": ticker,
                "evaluationSession": str(raw["evaluationSession"]),
                "entrySession": entry,
                "horizon": PRIMARY_HORIZON,
                "targetExitSession": target,
                "state": state,
                "successorSymbol": successor or "",
                "resolutionSource": source,
                "candidateActionTypes": ";".join(
                    sorted(
                        {
                            str(action.get("bucket") or "")
                            for action in candidates
                            if action.get("bucket")
                        }
                    )
                ),
                "candidateActionIds": ";".join(
                    str(action.get("id") or "")
                    for action in candidates
                ),
                "adjustedActionTypes": ";".join(
                    sorted(
                        {
                            str(action.get("bucket") or "")
                            for action in adjusted
                            if action.get("bucket")
                        }
                    )
                ),
                "maxInternalGapSessions": gap,
                "longInternalGapCandidate": long_gap,
            }
        )

    state_counts = Counter(row["state"] for row in audit_rows)
    source_counts = Counter(row["resolutionSource"] for row in audit_rows)
    unresolved = [
        row
        for row in audit_rows
        if row["state"] == "UNRESOLVED_CONTINUITY"
    ]

    path = output / "validation-continuity-audit.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(audit_rows[0]),
        )
        writer.writeheader()
        writer.writerows(audit_rows)

    result = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_VALIDATION_CONTINUITY_AUDITED",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceScopeKeySha256": summary["scopeKeySha256"],
        "scopeRows": len(audit_rows),
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "continuityStateCounts": dict(sorted(state_counts.items())),
        "resolutionSourceCounts": dict(sorted(source_counts.items())),
        "longGapRows": sum(
            bool(row["longInternalGapCandidate"])
            for row in audit_rows
        ),
        "unresolvedRows": len(unresolved),
        "unresolvedEventNumbers": [
            row["eventNumber"]
            for row in unresolved
        ],
        "providerSemanticsCompletenessChecked": True,
        "performanceStageBlocked": len(unresolved) > 0,
        "nextGate": (
            "Resolve all unresolved rows and separately verify complete "
            "provider holder-consideration semantics before validation."
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope-csv", type=Path, required=True)
    parser.add_argument("--scope-summary", type=Path, required=True)
    parser.add_argument("--corporate-actions", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                scope_csv=args.scope_csv,
                scope_summary=args.scope_summary,
                corporate_actions=args.corporate_actions,
                market_root=args.market_root,
                output=args.output,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
