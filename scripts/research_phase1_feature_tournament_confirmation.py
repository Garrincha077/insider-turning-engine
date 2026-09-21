"""Run frozen 2019-2020 confirmation for discovery-selected features."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import research_phase1_b0 as b0
import research_phase1_feature_tournament_discovery as discovery
import research_phase1_feature_tournament_stage_a as stage_a

HORIZONS = discovery.HORIZONS
PRIMARY_HORIZON = discovery.PRIMARY_HORIZON
CONFIRMATION_START = "2019-01-01"
CONFIRMATION_END = "2020-12-31"
EXPECTED_CONFIRMATION_EVENTS = 9850

EXPECTED_CANDIDATES = {
    "F1": {
        "variantId": "F1_ABS_PLUS_FRACTION_POST",
        "coverageClass": "GENERAL_ELIGIBLE",
        "frozenGroupDefinition": {
            "kind": "TRUE",
            "sourceFeature": "F1_ABS_PLUS_FRACTION_POST",
            "preferred": True,
            "complement": False,
        },
    },
    "F2": {
        "variantId": "F2_DIRECT_VS_INDIRECT",
        "coverageClass": "GENERAL_ELIGIBLE",
        "frozenGroupDefinition": {
            "kind": "F2_DYNAMIC",
            "sourceFeature": "F2_DIRECT_VS_INDIRECT",
            "preferred": "INDIRECT_ONLY",
            "complement": "DIRECT_ONLY",
        },
    },
    "F4": {
        "variantId": "F4_RECLAIM_PERSIST_5",
        "coverageClass": "GENERAL_ELIGIBLE",
        "frozenGroupDefinition": {
            "kind": "TRUE",
            "sourceFeature": "F4_RECLAIM_PERSIST_5",
            "preferred": True,
            "complement": False,
        },
    },
}


def _read_discovery(path: Path) -> dict[str, Any]:
    payload = discovery._read_json(path)
    required = {
        "status": "PHASE1_INSIDER_FEATURE_TOURNAMENT_DISCOVERY_COMPLETE",
        "definitionId": "PHASE1_INSIDER_FEATURE_TOURNAMENT_V1",
        "discoveryEvents": 14340,
        "discoveryDistinctIssuers": 3836,
        "familyCandidateCount": 3,
        "confirmationOpened": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"discovery contract mismatch: {key}")

    families = payload.get("familyCandidates")
    if not isinstance(families, dict):
        raise ValueError("discovery family candidates missing")
    if families.get("F3") != {
        "family": "F3",
        "status": "NO_FAMILY_CANDIDATE",
    }:
        raise ValueError("F3 discovery result changed")
    for family, expected in EXPECTED_CANDIDATES.items():
        actual = families.get(family)
        if not isinstance(actual, dict):
            raise ValueError(f"discovery candidate missing: {family}")
        for key, value in expected.items():
            if actual.get(key) != value:
                raise ValueError(
                    f"discovery candidate changed: {family}.{key}"
                )
        if actual.get("status") != "DISCOVERY_FAMILY_CANDIDATE_FROZEN":
            raise ValueError(f"discovery candidate not frozen: {family}")
    return payload


def _confirmation_market_maps(
    market_root: Path,
    output: Path,
    tickers: set[str],
) -> tuple[dict[str, dict[str, tuple[Any, ...]]], Path]:
    if (market_root / "2023").exists():
        raise ValueError("sealed OOS market directory mounted")
    paths = stage_a._market_paths(
        market_root,
        "canonical-market",
        range(2016, 2023),
    )
    db_path = output / "feature-confirmation.sqlite"
    stage_a._build_market_db(paths, db_path)
    conn = sqlite3.connect(db_path)
    maps: dict[str, dict[str, tuple[Any, ...]]] = {}
    try:
        for ticker in sorted(tickers | {"SPY"}):
            rows = conn.execute(
                "SELECT date,open,high,low,close,volume,trade_count,terminal "
                "FROM market WHERE ticker=? ORDER BY date",
                (ticker,),
            ).fetchall()
            maps[ticker] = {str(row[0]): row for row in rows}
    finally:
        conn.close()
    return maps, db_path


def _terms_for_confirmation(
    ledger_row: dict[str, Any],
    final_row: dict[str, Any] | None,
    actions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    try:
        return discovery._terms_for(ledger_row, final_row, actions)
    except ValueError as exc:
        action_ids = discovery._action_ids(ledger_row)
        action_rows = [
            actions[action_id]
            for action_id in action_ids
            if action_id in actions
        ]
        detail = {
            "eventNumber": ledger_row.get("eventNumber"),
            "issuerCik": ledger_row.get("issuerCik"),
            "ticker": ledger_row.get("ticker"),
            "entrySession": ledger_row.get("entrySession"),
            "horizon": ledger_row.get("horizon"),
            "targetExitSession": ledger_row.get("targetExitSession"),
            "state": ledger_row.get("state"),
            "successorSymbol": ledger_row.get("successorSymbol"),
            "candidateActionIds": action_ids,
            "actions": action_rows,
        }
        raise ValueError(
            f"confirmation continuity adapter failed: {exc}; "
            f"context={json.dumps(detail, sort_keys=True)}"
        ) from exc


def _audit_incomplete_provider_stock_mergers(
    confirmation: list[dict[str, str]],
    ledger_by_base: dict[
        tuple[str, str, str, str],
        list[dict[str, str]],
    ],
    actions: dict[str, dict[str, Any]],
) -> None:
    findings: dict[str, dict[str, Any]] = {}
    for event in confirmation:
        for ledger_row in ledger_by_base.get(discovery._base_key(event), []):
            action_types = {
                item
                for item in str(
                    ledger_row.get("candidateActionTypes") or ""
                ).split(";")
                if item
            }
            if (
                ledger_row.get("state")
                != "TRANSFORMED_HOLDER_CONSIDERATION"
                or ledger_row.get("successorSymbol")
                or not action_types.intersection(
                    {"stock_mergers", "stock_and_cash_mergers"}
                )
            ):
                continue
            for action_id in discovery._action_ids(ledger_row):
                finding = findings.setdefault(
                    action_id,
                    {
                        "action": actions.get(action_id),
                        "tickers": set(),
                        "eventNumbers": set(),
                        "horizons": set(),
                    },
                )
                finding["tickers"].add(str(ledger_row["ticker"]))
                finding["eventNumbers"].add(
                    int(ledger_row["eventNumber"])
                )
                finding["horizons"].add(int(ledger_row["horizon"]))

    if findings:
        serializable = {}
        for action_id, finding in sorted(findings.items()):
            serializable[action_id] = {
                "action": finding["action"],
                "tickers": sorted(finding["tickers"]),
                "eventNumbers": sorted(finding["eventNumbers"]),
                "horizons": sorted(finding["horizons"]),
            }
        raise ValueError(
            "incomplete frozen provider stock-merger semantics: "
            + json.dumps(serializable, sort_keys=True)
        )


def _value_confirmation_outcomes(
    matrix: list[dict[str, str]],
    ledger: list[dict[str, str]],
    final_rows: list[dict[str, Any]],
    actions: dict[str, dict[str, Any]],
    market_root: Path,
    output: Path,
) -> list[dict[str, Any]]:
    confirmation = [
        dict(row)
        for row in matrix
        if CONFIRMATION_START
        <= str(row["evaluationSession"])
        <= CONFIRMATION_END
    ]
    if len(confirmation) != EXPECTED_CONFIRMATION_EVENTS:
        raise ValueError("confirmation event count changed")

    ledger_by_base: dict[
        tuple[str, str, str, str],
        list[dict[str, str]],
    ] = defaultdict(list)
    for ledger_row in ledger:
        ledger_by_base[discovery._base_key(ledger_row)].append(ledger_row)

    final_by_key = {
        discovery._horizon_key(row): row
        for row in final_rows
    }

    _audit_incomplete_provider_stock_mergers(
        confirmation,
        ledger_by_base,
        actions,
    )
    unresolved_keys = {
        discovery._horizon_key(row)
        for row in ledger
        if row["state"] == "UNRESOLVED_CONTINUITY"
    }
    if set(final_by_key) != unresolved_keys:
        raise ValueError("final continuity key-set changed")

    terms_by_key: dict[
        tuple[str, str, str, str, int, str],
        dict[str, Any],
    ] = {}
    needed_tickers = {
        str(row["ticker"]).upper()
        for row in confirmation
    }
    for row in confirmation:
        matches = ledger_by_base.get(discovery._base_key(row), [])
        if len(matches) != len(HORIZONS):
            raise ValueError("confirmation event lacks four Stage-B rows")
        for ledger_row in matches:
            key = discovery._horizon_key(ledger_row)
            terms = _terms_for_confirmation(
                ledger_row,
                final_by_key.get(key),
                actions,
            )
            terms_by_key[key] = terms
            terminal = str(terms["terminalTicker"])
            if terminal:
                needed_tickers.add(terminal)
            for leg in terms["basket"]:
                needed_tickers.add(str(leg["symbol"]))

    maps, db_path = _confirmation_market_maps(
        market_root,
        output,
        needed_tickers,
    )
    result: list[dict[str, Any]] = []
    try:
        for row in confirmation:
            original = str(row["ticker"]).upper()
            entry_session = str(row["entrySession"])
            entry = maps.get(original, {}).get(entry_session)
            spy_entry = maps["SPY"].get(entry_session)
            if not b0._regular(entry) or not b0._regular(spy_entry):
                raise ValueError("frozen confirmation entry bar disappeared")
            entry_open = float(entry[1])
            spy_entry_open = float(spy_entry[1])

            event = dict(row)
            event["entryOpen"] = entry_open
            event_number: int | None = None
            by_horizon = {
                int(item["horizon"]): item
                for item in ledger_by_base[discovery._base_key(row)]
            }
            if set(by_horizon) != set(HORIZONS):
                raise ValueError("confirmation horizon set changed")

            for horizon in HORIZONS:
                ledger_row = by_horizon[horizon]
                event_number = int(ledger_row["eventNumber"])
                key = discovery._horizon_key(ledger_row)
                terms = terms_by_key[key]
                target = str(ledger_row["targetExitSession"])
                raw: float | None = None
                excess: float | None = None
                reason = ""

                if terms["decision"] == "DISCONTINUOUS_NO_COMPLETE_VALUATION":
                    reason = "DISCONTINUOUS_NO_COMPLETE_VALUATION"
                else:
                    spy_exit = maps["SPY"].get(target)
                    if not b0._regular(spy_exit):
                        reason = "MISSING_EXACT_SPY_EXIT_BAR"
                    else:
                        terminal_value = float(terms["cash"])
                        if terms["basket"]:
                            for leg in terms["basket"]:
                                terminal = maps.get(
                                    str(leg["symbol"]),
                                    {},
                                ).get(target)
                                if not b0._regular(terminal):
                                    reason = (
                                        "MISSING_EXACT_BASKET_COMPONENT_BAR"
                                    )
                                    break
                                terminal_value += (
                                    float(leg["quantity"])
                                    * float(terminal[4])
                                )
                        else:
                            quantity = float(terms["marketQuantity"])
                            terminal_ticker = str(terms["terminalTicker"])
                            if quantity:
                                terminal = maps.get(
                                    terminal_ticker,
                                    {},
                                ).get(target)
                                if not b0._regular(terminal):
                                    reason = (
                                        "MISSING_EXACT_TERMINAL_HOLDER_BAR"
                                    )
                                else:
                                    terminal_value += (
                                        quantity * float(terminal[4])
                                    )
                        if not reason:
                            spy_return = (
                                float(spy_exit[4]) / spy_entry_open - 1.0
                            )
                            raw = terminal_value / entry_open - 1.0
                            excess = raw - spy_return

                event[f"exit_{horizon}"] = target
                event[f"raw_{horizon}"] = raw
                event[f"excess_{horizon}"] = excess
                event[f"reason_{horizon}"] = reason or None
                event[f"continuity_{horizon}"] = terms["decision"]
                event[f"valuationKind_{horizon}"] = terms["kind"]

            if event_number is None:
                raise ValueError("confirmation event missing Stage-B event number")
            event["eventNumber"] = event_number
            result.append(event)
    finally:
        db_path.unlink(missing_ok=True)

    if any(
        not CONFIRMATION_START
        <= str(row["evaluationSession"])
        <= CONFIRMATION_END
        for row in result
    ):
        raise ValueError("non-confirmation event outcome was opened")
    return result


def _benchmark_keys(
    path: Path,
) -> set[tuple[str, str, str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {
            "issuerCik",
            "ticker",
            "evaluationSession",
            "entrySession",
        }
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("benchmark event file missing identity fields")
        return {
            (
                str(row["issuerCik"]),
                str(row["ticker"]).upper(),
                str(row["evaluationSession"]),
                str(row["entrySession"]),
            )
            for row in reader
            if CONFIRMATION_START
            <= str(row["evaluationSession"])
            <= CONFIRMATION_END
        }


def _candidate_rows(
    outcomes: list[dict[str, Any]],
    cutpoints: dict[str, Any],
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    variant_id = str(candidate["variantId"])
    group = candidate["frozenGroupDefinition"]
    f2_preferred = None
    if group["kind"] == "F2_DYNAMIC":
        f2_preferred = str(group["preferred"])

    rows = []
    for source in outcomes:
        membership = discovery._membership(
            source,
            variant_id=variant_id,
            cutpoints=cutpoints,
            f2_preferred=f2_preferred,
        )
        if membership is None:
            continue
        item = dict(source)
        item["_group"] = membership
        rows.append(item)
    return rows


def _evaluate_candidate(
    *,
    family: str,
    candidate: dict[str, Any],
    outcomes: list[dict[str, Any]],
    cutpoints: dict[str, Any],
    benchmark_sets: dict[
        str,
        set[tuple[str, str, str, str]],
    ],
) -> dict[str, Any]:
    rows = _candidate_rows(outcomes, cutpoints, candidate)

    horizons = {}
    for horizon in HORIZONS:
        horizons[str(horizon)] = {
            "preferred": discovery._group_summary(
                rows,
                horizon,
                "PREFERRED",
            ),
            "complement": discovery._group_summary(
                rows,
                horizon,
                "COMPLEMENT",
            ),
            "incrementalEventWeightedMean": discovery._increment(
                rows,
                horizon,
            ),
        }

    primary = horizons[str(PRIMARY_HORIZON)]
    preferred = primary["preferred"]
    event_increment = primary["incrementalEventWeightedMean"]
    issuer_increment = discovery._equal_weight_increment(
        rows,
        "issuerCik",
    )
    session_increment = discovery._equal_weight_increment(
        rows,
        "entrySession",
    )
    top1_increment, top1_removed = discovery._top1_removed_increment(rows)

    year_increments = {
        year: discovery._increment(
            [
                row
                for row in rows
                if str(row["evaluationSession"]).startswith(year)
            ]
        )
        for year in ("2019", "2020")
    }

    adv_q20 = float(cutpoints["DOLLAR_ADV_20"]["q20"])
    outside_adv = [
        row
        for row in rows
        if (
            (value := discovery._optional_float(
                row.get("DOLLAR_ADV_20")
            ))
            is not None
            and value > adv_q20
        )
    ]
    outside_adv_increment = discovery._increment(outside_adv)

    checks = {
        "preferredMatureNAtLeast150": int(preferred["matureN"]) >= 150,
        "preferredDistinctIssuersAtLeast75": (
            int(preferred["distinctIssuers"]) >= 75
        ),
        "pooledEventWeightedIncrementalMeanPositive": (
            event_increment is not None and event_increment > 0
        ),
        "pooledIssuerEqualWeightIncrementalMeanPositive": (
            issuer_increment is not None and issuer_increment > 0
        ),
        "pooledEntrySessionEqualWeightIncrementalMeanPositive": (
            session_increment is not None and session_increment > 0
        ),
        "pooledTop1PctRemovedIncrementalMeanPositive": (
            top1_increment is not None and top1_increment > 0
        ),
        "2019IncrementalMeanPositive": (
            year_increments["2019"] is not None
            and year_increments["2019"] > 0
        ),
        "2020IncrementalMeanPositive": (
            year_increments["2020"] is not None
            and year_increments["2020"] > 0
        ),
        "outsideBottomDollarAdvQuintileIncrementalMeanPositive": (
            outside_adv_increment is not None
            and outside_adv_increment > 0
        ),
    }
    passed = all(checks.values())

    return {
        "family": family,
        "variantId": candidate["variantId"],
        "coverageClass": candidate["coverageClass"],
        "frozenGroupDefinition": candidate["frozenGroupDefinition"],
        "observedCohortN": len(rows),
        "status": (
            "CONFIRMED_DEVELOPMENT_CANDIDATE"
            if passed
            else "CONFIRMATION_FAIL_FROZEN"
        ),
        "horizonSummaries": horizons,
        "primary126": {
            "pooledEventWeightedIncrementalMean": event_increment,
            "pooledIssuerEqualWeightIncrementalMean": issuer_increment,
            "pooledEntrySessionEqualWeightIncrementalMean": (
                session_increment
            ),
            "pooledTop1PctRemovedIncrementalMean": top1_increment,
            "top1PctRemovedRows": top1_removed,
            "yearIncrementalMeans": year_increments,
            "incrementalMeanOutsideBottomDollarAdvQuintile": (
                outside_adv_increment
            ),
        },
        "contextStrata": discovery._context_strata(rows, cutpoints),
        "benchmarkOverlap": discovery._overlap_metrics(
            rows,
            benchmark_sets,
        ),
        "confirmationChecks": checks,
        "confirmed": passed,
        "replacementAllowed": False,
    }


def run(
    *,
    stage_a_dir: Path,
    discovery_results_path: Path,
    ledger_path: Path,
    corporate_actions_path: Path,
    final_contract_path: Path,
    market_root: Path,
    b1_events_path: Path,
    b2_events_path: Path,
    b3_events_path: Path,
    b4_events_path: Path,
    output: Path,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)

    discovery_result = _read_discovery(discovery_results_path)
    stage_a_summary, cutpoints, matrix = discovery._load_stage_a(
        stage_a_dir
    )
    ledger = discovery._load_ledger(ledger_path)
    final_rows = discovery._load_final_contract(final_contract_path)
    actions = discovery._load_actions(corporate_actions_path)

    outcomes = _value_confirmation_outcomes(
        matrix,
        ledger,
        final_rows,
        actions,
        market_root,
        output,
    )

    benchmark_sets = {
        "B1": _benchmark_keys(b1_events_path),
        "B2": _benchmark_keys(b2_events_path),
        "B3": _benchmark_keys(b3_events_path),
        "B4": _benchmark_keys(b4_events_path),
    }

    results = []
    for family in ("F1", "F2", "F4"):
        candidate = discovery_result["familyCandidates"][family]
        results.append(
            _evaluate_candidate(
                family=family,
                candidate=candidate,
                outcomes=outcomes,
                cutpoints=cutpoints,
                benchmark_sets=benchmark_sets,
            )
        )

    confirmed = [
        {
            "family": row["family"],
            "variantId": row["variantId"],
            "coverageClass": row["coverageClass"],
            "frozenGroupDefinition": row["frozenGroupDefinition"],
        }
        for row in results
        if row["confirmed"]
    ]

    feature_fields = list(matrix[0].keys())
    output_rows = [
        {
            key: row.get(key)
            for key in (
                "eventNumber",
                *feature_fields,
                "entryOpen",
                *(f"exit_{h}" for h in HORIZONS),
                *(f"raw_{h}" for h in HORIZONS),
                *(f"excess_{h}" for h in HORIZONS),
                *(f"reason_{h}" for h in HORIZONS),
                *(f"continuity_{h}" for h in HORIZONS),
                *(f"valuationKind_{h}" for h in HORIZONS),
            )
        }
        for row in outcomes
    ]
    with (output / "confirmation-event-outcomes.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(output_rows[0]),
        )
        writer.writeheader()
        writer.writerows(output_rows)

    maturity = {
        str(horizon): {
            "valued": sum(
                row.get(f"excess_{horizon}") is not None
                for row in outcomes
            ),
            "missing": sum(
                row.get(f"excess_{horizon}") is None
                for row in outcomes
            ),
            "reasonCounts": dict(
                sorted(
                    Counter(
                        str(
                            row.get(f"reason_{horizon}")
                            or "VALUED"
                        )
                        for row in outcomes
                    ).items()
                )
            ),
        }
        for horizon in HORIZONS
    }

    payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_INSIDER_FEATURE_TOURNAMENT_CONFIRMATION_COMPLETE",
        "definitionId": "PHASE1_INSIDER_FEATURE_TOURNAMENT_V1",
        "researchOnly": True,
        "confirmationPeriod": "2019-01-01 through 2020-12-31",
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "sourceStageAEvents": stage_a_summary["scope"]["events"],
        "sourceDiscoveryEvents": discovery_result["discoveryEvents"],
        "sourceDiscoveryFamilyCandidates": 3,
        "confirmationEvents": len(outcomes),
        "confirmationDistinctIssuers": len(
            {str(row["issuerCik"]) for row in outcomes}
        ),
        "maturity": maturity,
        "candidateResults": results,
        "confirmedCandidates": confirmed,
        "confirmedCandidateCount": len(confirmed),
        "noReselection": True,
        "noAlternateThreshold": True,
        "confirmationOpened": True,
        "confirmationComplete": True,
        "validationOpened": False,
        "validationEventOutcomesRead": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "compositeWeightsFit": False,
        "newVariantsAdded": False,
        "nextGate": (
            "Freeze confirmed candidates, then predeclare and run "
            "2021-2022 validation with no selection or tuning."
        ),
    }
    (output / "confirmation-results.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-a-dir", type=Path, required=True)
    parser.add_argument(
        "--discovery-results",
        type=Path,
        required=True,
    )
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--corporate-actions", type=Path, required=True)
    parser.add_argument("--final-contract", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--b1-events", type=Path, required=True)
    parser.add_argument("--b2-events", type=Path, required=True)
    parser.add_argument("--b3-events", type=Path, required=True)
    parser.add_argument("--b4-events", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = run(
        stage_a_dir=args.stage_a_dir,
        discovery_results_path=args.discovery_results,
        ledger_path=args.ledger,
        corporate_actions_path=args.corporate_actions,
        final_contract_path=args.final_contract,
        market_root=args.market_root,
        b1_events_path=args.b1_events,
        b2_events_path=args.b2_events,
        b3_events_path=args.b3_events,
        b4_events_path=args.b4_events,
        output=args.output,
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key != "candidateResults"
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
