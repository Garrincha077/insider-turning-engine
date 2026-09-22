"""Run Monster Winner Enrichment v1 discovery on frozen 2016-2018 events."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import research_market_event_audit_v2 as p0
import research_monster_winner_path_feasibility as feasibility
import research_phase1_feature_tournament_confirmation as confirmation
import research_phase1_feature_tournament_discovery as discovery

DISCOVERY_END = "2018-12-31"
EXPECTED_DISCOVERY_EVENTS = 14340
EXPECTED_STAGE_A_EVENTS = 24190
PRIMARY_HORIZON = 252
PRIMARY_LABEL = "M100_252_CLOSE"
MIN_NEGATIVE_COVERAGE = 0.95
MAX_NEGATIVE_GAP = 5
SEALED_YEAR = 2023

LABEL_SPECS = {
    "M50_252_CLOSE": (252, 1.5),
    "M100_252_CLOSE": (252, 2.0),
    "M200_252_CLOSE": (252, 3.0),
    "M500_252_CLOSE": (252, 6.0),
    "M100_126_CLOSE": (126, 2.0),
    "M200_126_CLOSE": (126, 3.0),
}

VARIANTS: dict[str, dict[str, Any]] = {
    key: dict(value)
    for key, value in discovery.VARIANTS.items()
    if key != "F2_DIRECT_VS_INDIRECT"
}
VARIANTS.update(
    {
        "F2_INDIRECT_VS_DIRECT": {
            "family": "F2",
            "source": "F2_DIRECT_VS_INDIRECT",
            "coverage": "F2_DIRECT_VS_INDIRECT",
            "kind": "F2_FIXED",
            "preferred": "INDIRECT_ONLY",
            "complement": "DIRECT_ONLY",
        },
        "F2_DIRECT_VS_INDIRECT": {
            "family": "F2",
            "source": "F2_DIRECT_VS_INDIRECT",
            "coverage": "F2_DIRECT_VS_INDIRECT",
            "kind": "F2_FIXED",
            "preferred": "DIRECT_ONLY",
            "complement": "INDIRECT_ONLY",
        },
    }
)

PRICE_FIELDS_READ = ["entry_open", "exact_path_close"]


def _regular(row: tuple[float, float, int, int, bool] | None) -> bool:
    return (
        row is not None
        and not bool(row[4])
        and int(row[2]) > 0
        and int(row[3]) > 0
    )


def _market_paths(root: Path) -> list[Path]:
    if (root / "2021").exists() or (root / "2022").exists():
        raise ValueError("confirmation/known-sample market years mounted in discovery")
    if (root / "2023").exists():
        raise ValueError("sealed OOS market year mounted")
    paths: list[Path] = []
    for year in range(2016, 2021):
        matches = list(root.rglob(f"canonical-market-{year}.csv"))
        if len(matches) != 1:
            raise ValueError(
                f"expected one canonical-market-{year}.csv, got {len(matches)}"
            )
        paths.append(matches[0])
    return paths


def _market_maps(
    root: Path,
    wanted: set[str],
) -> dict[str, dict[str, tuple[float, float, int, int, bool]]]:
    maps: dict[
        str,
        dict[str, tuple[float, float, int, int, bool]],
    ] = {ticker: {} for ticker in wanted}

    for path in _market_paths(root):
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader)
            index = {name: pos for pos, name in enumerate(header)}
            required = {
                "ticker",
                "date",
                "open",
                "close",
                "volume",
                "trade_count",
                "terminal_candidate",
            }
            if not required.issubset(index):
                raise ValueError(f"market outcome fields missing: {path}")
            for raw in reader:
                ticker = raw[index["ticker"]].strip().upper()
                if ticker not in maps:
                    continue
                day = raw[index["date"]][:10]
                if int(day[:4]) >= SEALED_YEAR:
                    raise ValueError("sealed OOS market row encountered")
                maps[ticker][day] = (
                    float(raw[index["open"]]),
                    float(raw[index["close"]]),
                    int(float(raw[index["volume"]] or 0)),
                    int(float(raw[index["trade_count"]] or 0)),
                    raw[index["terminal_candidate"]].strip().lower() == "true",
                )
    return maps


def _load_path_feasibility(
    csv_path: Path,
    summary_path: Path,
) -> dict[tuple[str, str, str, str], dict[str, str]]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    required = {
        "status": "MONSTER_WINNER_ENRICHMENT_V1_PATH_FEASIBILITY_AUDITED",
        "definitionId": "MONSTER_WINNER_ENRICHMENT_V1",
        "sourceStageAEvents": EXPECTED_STAGE_A_EVENTS,
        "performanceRead": False,
        "priceFieldsRead": [],
        "outcomeFieldsRead": [],
        "monsterLabelsComputed": False,
        "thresholdCrossingsRead": False,
        "mfeValuesComputed": False,
        "knownSampleDiagnosticOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for key, expected in required.items():
        if summary.get(key) != expected:
            raise ValueError(f"path feasibility contract changed: {key}")

    with csv_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != EXPECTED_STAGE_A_EVENTS:
        raise ValueError("path feasibility event count changed")

    result: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in rows:
        key = discovery._base_key(row)
        if key in result:
            raise ValueError("duplicate path feasibility base key")
        result[key] = row
    return result


def _terms_and_paths(
    *,
    events: list[dict[str, str]],
    ledger: list[dict[str, str]],
    final_rows: list[dict[str, Any]],
    provider_amendment: dict[
        tuple[str, str, str, str, int, str],
        dict[str, Any],
    ],
    actions: dict[str, dict[str, Any]],
) -> tuple[
    dict[tuple[str, str, str, str], dict[str, Any]],
    set[str],
]:
    ledger_252 = [row for row in ledger if int(row["horizon"]) == PRIMARY_HORIZON]
    ledger_by_base = {
        discovery._base_key(row): row
        for row in ledger_252
    }
    if len(ledger_by_base) != EXPECTED_STAGE_A_EVENTS:
        raise ValueError("252-session ledger base-key count changed")

    final_by_key = {
        discovery._horizon_key(row): row
        for row in final_rows
    }
    unresolved = {
        discovery._horizon_key(row)
        for row in ledger
        if row["state"] == "UNRESOLVED_CONTINUITY"
    }
    if set(final_by_key) != unresolved:
        raise ValueError("final continuity key set changed")

    prepared: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    wanted: set[str] = set()

    for event in events:
        base = discovery._base_key(event)
        ledger_row = ledger_by_base.get(base)
        if ledger_row is None:
            raise ValueError("discovery event missing 252-session ledger row")
        key = discovery._horizon_key(ledger_row)
        final_row = final_by_key.get(key)
        amendment_row = provider_amendment.get(key)
        terms = confirmation._terms_for_confirmation(
            ledger_row,
            final_row,
            amendment_row,
            actions,
        )
        effective = feasibility._effective_date(
            ledger_row,
            final_row,
            amendment_row,
            terms,
            actions,
        )
        prepared[base] = {
            "ledger": ledger_row,
            "terms": terms,
            "effectiveDate": effective,
        }
        wanted.add(str(event["ticker"]).upper())
        terminal = str(terms["terminalTicker"]).upper()
        if terminal:
            wanted.add(terminal)
        for leg in terms["basket"]:
            wanted.add(str(leg["symbol"]).upper())

    return prepared, wanted


def _holder_close(
    *,
    day: str,
    ticker: str,
    terms: dict[str, Any],
    effective_date: str,
    maps: dict[str, dict[str, tuple[float, float, int, int, bool]]],
) -> float | None:
    decision = str(terms["decision"])
    kind = str(terms["kind"])
    terminal = str(terms["terminalTicker"]).upper()
    basket = list(terms["basket"])
    cash = float(terms["cash"])

    if decision == "DISCONTINUOUS_NO_COMPLETE_VALUATION":
        if not effective_date or day >= effective_date:
            return None
        row = maps.get(ticker, {}).get(day)
        return float(row[1]) if _regular(row) else None

    if kind == "STOCK_DIVIDEND_QUANTITY":
        row = maps.get(ticker, {}).get(day)
        return float(row[1]) if _regular(row) else None

    if decision in {
        "NO_CONTINUITY_CORRECTION_REQUIRED",
        "SAME_SECURITY_CONTINUITY",
    }:
        row = maps.get(ticker, {}).get(day)
        return float(row[1]) if _regular(row) else None

    if not effective_date:
        return None

    if day < effective_date:
        row = maps.get(ticker, {}).get(day)
        return float(row[1]) if _regular(row) else None

    value = cash
    if basket:
        for leg in basket:
            symbol = str(leg["symbol"]).upper()
            row = maps.get(symbol, {}).get(day)
            if not _regular(row):
                return None
            value += float(leg["quantity"]) * float(row[1])
        return value

    quantity = float(terms["marketQuantity"])
    if quantity > 0:
        if not terminal:
            return None
        row = maps.get(terminal, {}).get(day)
        if not _regular(row):
            return None
        return value + quantity * float(row[1])

    if cash > 0:
        return cash
    return None


def _path_stats(values: list[float | None]) -> tuple[int, float, int]:
    observed = sum(value is not None for value in values)
    coverage = observed / len(values) if values else 0.0
    run = 0
    maximum = 0
    for value in values:
        if value is None:
            run += 1
            maximum = max(maximum, run)
        else:
            run = 0
    return observed, coverage, maximum


def _label(
    *,
    values: list[float | None],
    sessions: list[str],
    entry_open: float,
    multiple: float,
    mandatory_unvalued: bool,
    deterministic_effective: bool,
) -> dict[str, Any]:
    threshold = entry_open * multiple
    first_crossing = ""
    observed_max: float | None = None
    for day, value in zip(sessions, values, strict=True):
        if value is None:
            continue
        observed_max = value if observed_max is None else max(observed_max, value)
        if not first_crossing and value >= threshold:
            first_crossing = day

    observed, coverage, max_gap = _path_stats(values)
    if first_crossing:
        state = "POSITIVE"
    elif (
        not mandatory_unvalued
        and deterministic_effective
        and coverage >= MIN_NEGATIVE_COVERAGE
        and max_gap <= MAX_NEGATIVE_GAP
    ):
        state = "NEGATIVE"
    else:
        state = "UNKNOWN"

    return {
        "state": state,
        "firstCrossingSession": first_crossing,
        "observedSessions": observed,
        "coverageRatio": coverage,
        "maxMissingRun": max_gap,
        "maxObservedMultiple": (
            observed_max / entry_open if observed_max is not None else None
        ),
    }


def _event_outcomes(
    *,
    events: list[dict[str, str]],
    prepared: dict[tuple[str, str, str, str], dict[str, Any]],
    path_feasibility: dict[tuple[str, str, str, str], dict[str, str]],
    maps: dict[str, dict[str, tuple[float, float, int, int, bool]]],
) -> list[dict[str, Any]]:
    sessions = p0._expected_sessions()
    session_index = {day: index for index, day in enumerate(sessions)}
    result: list[dict[str, Any]] = []

    for source in events:
        base = discovery._base_key(source)
        prep = prepared[base]
        ledger_row = prep["ledger"]
        terms = prep["terms"]
        effective = str(prep["effectiveDate"])
        ticker = str(source["ticker"]).upper()
        entry = str(source["entrySession"])
        target = str(ledger_row["targetExitSession"])
        entry_idx = session_index[entry]
        target_idx = session_index[target]
        if target_idx - entry_idx != PRIMARY_HORIZON:
            raise ValueError("252-session target clock changed")
        path_sessions = sessions[entry_idx : target_idx + 1]
        if len(path_sessions) != 253:
            raise ValueError("252-session path must contain 253 close observations")
        if any(int(day[:4]) >= SEALED_YEAR for day in path_sessions):
            raise ValueError("sealed OOS path session")

        entry_row = maps.get(ticker, {}).get(entry)
        if not _regular(entry_row):
            raise ValueError("frozen discovery exact entry bar disappeared")
        entry_open = float(entry_row[0])
        if entry_open <= 0:
            raise ValueError("non-positive exact entry open")

        values = [
            _holder_close(
                day=day,
                ticker=ticker,
                terms=terms,
                effective_date=effective,
                maps=maps,
            )
            for day in path_sessions
        ]

        mandatory_unvalued = (
            str(terms["decision"]) == "DISCONTINUOUS_NO_COMPLETE_VALUATION"
        )
        deterministic_effective = (
            not feasibility._needs_effective_date(terms, ticker)
            or bool(effective)
        )

        row: dict[str, Any] = {
            **source,
            "targetExitSession252": target,
            "entryOpen": entry_open,
            "continuityDecision252": str(terms["decision"]),
            "transformationKind252": str(terms["kind"]),
            "effectiveDate252": effective,
        }

        for label_id, (horizon, multiple) in LABEL_SPECS.items():
            local_sessions = path_sessions[: horizon + 1]
            local_values = values[: horizon + 1]
            label = _label(
                values=local_values,
                sessions=local_sessions,
                entry_open=entry_open,
                multiple=multiple,
                mandatory_unvalued=mandatory_unvalued,
                deterministic_effective=deterministic_effective,
            )
            row[label_id] = label["state"]
            row[f"{label_id}_FIRST"] = label["firstCrossingSession"]
            row[f"{label_id}_COVERAGE"] = label["coverageRatio"]
            row[f"{label_id}_MAX_GAP"] = label["maxMissingRun"]

        observed_max = max((v for v in values if v is not None), default=None)
        row["MAX_OBSERVED_MULTIPLE_252"] = (
            observed_max / entry_open if observed_max is not None else None
        )

        frozen = path_feasibility.get(base)
        if frozen is None:
            raise ValueError("discovery event missing frozen path-feasibility row")
        observed, coverage, max_gap = _path_stats(values)
        if observed != int(frozen["observablePathSessions"]):
            raise ValueError("outcome path observability differs from blind audit")
        if abs(coverage - float(frozen["coverageRatio"])) > 1e-9:
            raise ValueError("outcome path coverage differs from blind audit")
        if max_gap != int(frozen["maxConsecutiveUnobservableSessions"]):
            raise ValueError("outcome path max gap differs from blind audit")
        frozen_feasible = str(frozen["negativeLabelFeasible"]).lower() == "true"
        local_feasible = (
            not mandatory_unvalued
            and deterministic_effective
            and coverage >= MIN_NEGATIVE_COVERAGE
            and max_gap <= MAX_NEGATIVE_GAP
        )
        if local_feasible != frozen_feasible:
            raise ValueError("negative-label feasibility differs from blind audit")
        row["NEGATIVE_LABEL_FEASIBLE_252"] = local_feasible
        result.append(row)

    if len(result) != EXPECTED_DISCOVERY_EVENTS:
        raise ValueError("discovery outcome count changed")
    return result


def _membership(
    row: dict[str, Any],
    variant_id: str,
    cutpoints: dict[str, Any],
) -> str | None:
    spec = VARIANTS[variant_id]
    if spec["kind"] == "F2_FIXED":
        category = str(row.get(spec["source"]) or "")
        if category == spec["preferred"]:
            return "PREFERRED"
        if category == spec["complement"]:
            return "COMPLEMENT"
        return None
    return discovery._membership(
        row,
        variant_id=variant_id,
        cutpoints=cutpoints,
    )


def _state_counts(rows: list[dict[str, Any]], label: str, group: str) -> dict[str, int]:
    subset = [row for row in rows if row["_group"] == group]
    counts = Counter(str(row[label]) for row in subset)
    return {
        "N": len(subset),
        "positive": counts["POSITIVE"],
        "negative": counts["NEGATIVE"],
        "unknown": counts["UNKNOWN"],
    }


def _density(counts: dict[str, int]) -> float | None:
    return counts["positive"] / counts["N"] if counts["N"] else None


def _evaluable_hit_rate(counts: dict[str, int]) -> float | None:
    n = counts["positive"] + counts["negative"]
    return counts["positive"] / n if n else None


def _lift(
    rows: list[dict[str, Any]],
    label: str,
) -> tuple[float | None, dict[str, int], dict[str, int]]:
    preferred = _state_counts(rows, label, "PREFERRED")
    complement = _state_counts(rows, label, "COMPLEMENT")
    pd = _density(preferred)
    cd = _density(complement)
    lift = pd / cd if pd is not None and cd not in (None, 0.0) else None
    return lift, preferred, complement


def _variant_result(
    *,
    variant_id: str,
    outcomes: list[dict[str, Any]],
    stage_a_summary: dict[str, Any],
    cutpoints: dict[str, Any],
) -> dict[str, Any]:
    spec = VARIANTS[variant_id]
    grouped: list[dict[str, Any]] = []
    for source in outcomes:
        membership = _membership(source, variant_id, cutpoints)
        if membership is None:
            continue
        item = dict(source)
        item["_group"] = membership
        grouped.append(item)

    preferred_rows = [row for row in grouped if row["_group"] == "PREFERRED"]
    complement_rows = [row for row in grouped if row["_group"] == "COMPLEMENT"]
    review_share = (
        len(preferred_rows) / len(grouped)
        if grouped
        else None
    )

    m100_lift, pref100, comp100 = _lift(grouped, PRIMARY_LABEL)
    total_positive = pref100["positive"] + comp100["positive"]
    capture = (
        pref100["positive"] / total_positive
        if total_positive
        else None
    )
    capture_efficiency = (
        capture / review_share
        if capture is not None and review_share not in (None, 0.0)
        else None
    )

    year_lifts: dict[str, float | None] = {}
    for year in ("2016", "2017", "2018"):
        subset = [
            row for row in grouped
            if str(row["evaluationSession"]).startswith(year)
        ]
        year_lifts[year] = _lift(subset, PRIMARY_LABEL)[0]
    positive_years = sum(
        value is not None and value > 1.0
        for value in year_lifts.values()
    )

    adv_q20 = float(cutpoints["DOLLAR_ADV_20"]["q20"])
    outside_adv = [
        row
        for row in grouped
        if (
            (value := discovery._optional_float(row.get("DOLLAR_ADV_20")))
            is not None
            and value > adv_q20
        )
    ]
    outside_adv_lift = _lift(outside_adv, PRIMARY_LABEL)[0]

    m200_lift, pref200, comp200 = _lift(grouped, "M200_252_CLOSE")
    m200_total = pref200["positive"] + comp200["positive"]

    preferred_m100 = [
        row
        for row in preferred_rows
        if row[PRIMARY_LABEL] == "POSITIVE"
    ]
    by_issuer = Counter(str(row["issuerCik"]) for row in preferred_m100)
    by_session = Counter(str(row["entrySession"]) for row in preferred_m100)
    largest_issuer_share = (
        max(by_issuer.values()) / len(preferred_m100)
        if preferred_m100 else None
    )
    largest_session_share = (
        max(by_session.values()) / len(preferred_m100)
        if preferred_m100 else None
    )

    secondary: dict[str, Any] = {}
    for label in LABEL_SPECS:
        lift, preferred, complement = _lift(grouped, label)
        secondary[label] = {
            "lift": lift,
            "preferred": {
                **preferred,
                "observedPositiveDensity": _density(preferred),
                "evaluableHitRate": _evaluable_hit_rate(preferred),
                "unknownShare": (
                    preferred["unknown"] / preferred["N"]
                    if preferred["N"] else None
                ),
            },
            "complement": {
                **complement,
                "observedPositiveDensity": _density(complement),
                "evaluableHitRate": _evaluable_hit_rate(complement),
                "unknownShare": (
                    complement["unknown"] / complement["N"]
                    if complement["N"] else None
                ),
            },
        }

    top_tail_rows = [
        row
        for row in grouped
        if bool(row["NEGATIVE_LABEL_FEASIBLE_252"])
        and row["MAX_OBSERVED_MULTIPLE_252"] is not None
    ]
    top_tail: dict[str, Any] = {}
    if top_tail_rows:
        ranked = sorted(
            top_tail_rows,
            key=lambda row: (
                -float(row["MAX_OBSERVED_MULTIPLE_252"]),
                int(row["eventNumber"]),
            ),
        )
        for name, fraction in (
            ("top10Pct", 0.10),
            ("top5Pct", 0.05),
            ("top1Pct", 0.01),
            ("top0_5Pct", 0.005),
        ):
            n = max(1, math.ceil(len(ranked) * fraction))
            top = ranked[:n]
            preferred_share = sum(
                row["_group"] == "PREFERRED" for row in top
            ) / n
            top_tail[name] = {
                "N": n,
                "preferredShare": preferred_share,
                "enrichmentVsReviewShare": (
                    preferred_share / review_share
                    if review_share not in (None, 0.0)
                    else None
                ),
            }

    preferred_distinct_issuers = len(
        {str(row["issuerCik"]) for row in preferred_rows}
    )
    checks = {
        "preferredNAtLeast200": len(preferred_rows) >= 200,
        "preferredDistinctIssuersAtLeast100": preferred_distinct_issuers >= 100,
        "preferredM100HitsAtLeast20": pref100["positive"] >= 20,
        "reviewShareAtMost50Pct": (
            review_share is not None and review_share <= 0.50
        ),
        "m100LiftAtLeast1_50": (
            m100_lift is not None and m100_lift >= 1.50
        ),
        "m100CaptureAtLeast20Pct": (
            capture is not None and capture >= 0.20
        ),
        "m100LiftAbove1InAtLeastTwoYears": positive_years >= 2,
        "outsideBottomAdvM100LiftAtLeast1_25": (
            outside_adv_lift is not None and outside_adv_lift >= 1.25
        ),
        "m200LiftAbove1WhenAtLeast10ObservedM200": (
            m200_total < 10
            or (m200_lift is not None and m200_lift > 1.0)
        ),
        "singleIssuerM100ShareAtMost15Pct": (
            largest_issuer_share is not None
            and largest_issuer_share <= 0.15
        ),
    }
    passed = all(checks.values())

    coverage = stage_a_summary["coverage"].get(spec["coverage"], {})
    return {
        "variantId": variant_id,
        "family": spec["family"],
        "coverageClass": coverage.get("coverageClass"),
        "status": "DISCOVERY_PASS" if passed else "DISCOVERY_FAIL",
        "observedCohortN": len(grouped),
        "preferredN": len(preferred_rows),
        "complementN": len(complement_rows),
        "preferredDistinctIssuers": preferred_distinct_issuers,
        "reviewShare": review_share,
        "reviewReduction": 1.0 - review_share if review_share is not None else None,
        "primaryM100": {
            "lift": m100_lift,
            "capture": capture,
            "captureEfficiency": capture_efficiency,
            "preferred": secondary[PRIMARY_LABEL]["preferred"],
            "complement": secondary[PRIMARY_LABEL]["complement"],
            "yearLifts": year_lifts,
            "yearsWithLiftAbove1": positive_years,
            "outsideBottomDollarAdvLift": outside_adv_lift,
            "largestIssuerShareOfPreferredM100": largest_issuer_share,
            "largestEntrySessionShareOfPreferredM100": largest_session_share,
        },
        "secondaryLabels": secondary,
        "topTailDiagnostics": top_tail,
        "advancementChecks": checks,
        "discoveryPass": passed,
    }


def _select_family_candidates(
    results: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for family in ("F1", "F2", "F3", "F4"):
        passing = [
            row
            for row in results
            if row["family"] == family and row["discoveryPass"] is True
        ]
        if not passing:
            output[family] = {
                "family": family,
                "status": "NO_MONSTER_DISCOVERY_CANDIDATE",
            }
            continue

        def rank(row: dict[str, Any]) -> tuple[float, float, float, float, float, str]:
            p = row["primaryM100"]
            m200 = row["secondaryLabels"]["M200_252_CLOSE"]["lift"]
            return (
                -float(p["captureEfficiency"]),
                -float(p["lift"]),
                -float(m200 if m200 is not None else 0.0),
                -float(p["capture"]),
                float(row["reviewShare"]),
                str(row["variantId"]),
            )

        winner = sorted(passing, key=rank)[0]
        output[family] = {
            "family": family,
            "status": "MONSTER_DISCOVERY_FAMILY_CANDIDATE_FROZEN",
            "variantId": winner["variantId"],
            "coverageClass": winner["coverageClass"],
            "selectionTuple": {
                "captureEfficiency": winner["primaryM100"]["captureEfficiency"],
                "m100Lift": winner["primaryM100"]["lift"],
                "m200Lift": winner["secondaryLabels"]["M200_252_CLOSE"]["lift"],
                "m100Capture": winner["primaryM100"]["capture"],
                "reviewShare": winner["reviewShare"],
            },
        }
    return output


def run(
    *,
    stage_a_dir: Path,
    path_feasibility_csv: Path,
    path_feasibility_summary: Path,
    ledger_path: Path,
    corporate_actions_path: Path,
    final_contract_path: Path,
    provider_amendment_path: Path,
    market_root: Path,
    output: Path,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)

    stage_a_summary, cutpoints, matrix = discovery._load_stage_a(stage_a_dir)
    events = [
        dict(row)
        for row in matrix
        if str(row["evaluationSession"]) <= DISCOVERY_END
    ]
    if len(events) != EXPECTED_DISCOVERY_EVENTS:
        raise ValueError("frozen discovery event count changed")
    if any(str(row["evaluationSession"]) > DISCOVERY_END for row in events):
        raise ValueError("confirmation event entered Monster discovery")

    path_feasibility = _load_path_feasibility(
        path_feasibility_csv,
        path_feasibility_summary,
    )
    ledger = discovery._load_ledger(ledger_path)
    final_rows = discovery._load_final_contract(final_contract_path)
    actions = discovery._load_actions(corporate_actions_path)
    provider_amendment = confirmation._load_provider_amendment(
        provider_amendment_path
    )

    prepared, wanted = _terms_and_paths(
        events=events,
        ledger=ledger,
        final_rows=final_rows,
        provider_amendment=provider_amendment,
        actions=actions,
    )
    maps = _market_maps(market_root, wanted)

    outcomes = _event_outcomes(
        events=events,
        prepared=prepared,
        path_feasibility=path_feasibility,
        maps=maps,
    )

    result_rows = [
        _variant_result(
            variant_id=variant_id,
            outcomes=outcomes,
            stage_a_summary=stage_a_summary,
            cutpoints=cutpoints,
        )
        for variant_id in sorted(VARIANTS)
    ]
    family_candidates = _select_family_candidates(result_rows)
    candidate_count = sum(
        value["status"] == "MONSTER_DISCOVERY_FAMILY_CANDIDATE_FROZEN"
        for value in family_candidates.values()
    )

    outcome_fields = [
        "eventNumber",
        "issuerCik",
        "ticker",
        "evaluationSession",
        "entrySession",
        "targetExitSession252",
        "continuityDecision252",
        "transformationKind252",
        "effectiveDate252",
        "NEGATIVE_LABEL_FEASIBLE_252",
        "MAX_OBSERVED_MULTIPLE_252",
    ]
    for label_id in LABEL_SPECS:
        outcome_fields.extend(
            [
                label_id,
                f"{label_id}_FIRST",
                f"{label_id}_COVERAGE",
                f"{label_id}_MAX_GAP",
            ]
        )

    event_path = output / "monster-discovery-event-outcomes.csv"
    with event_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=outcome_fields)
        writer.writeheader()
        for row in outcomes:
            writer.writerow({field: row.get(field, "") for field in outcome_fields})

    label_counts = {
        label: dict(
            sorted(Counter(str(row[label]) for row in outcomes).items())
        )
        for label in LABEL_SPECS
    }

    summary = {
        "schemaVersion": "1.0.0",
        "status": "MONSTER_WINNER_ENRICHMENT_V1_DISCOVERY_COMPLETE",
        "definitionId": "MONSTER_WINNER_ENRICHMENT_V1",
        "researchOnly": True,
        "sourcePathFeasibilityRelease": (
            "research-monster-winner-enrichment-path-feasibility-v1"
        ),
        "discoveryEvents": len(outcomes),
        "discoveryDistinctIssuers": len(
            {str(row["issuerCik"]) for row in outcomes}
        ),
        "evaluationStart": min(str(row["evaluationSession"]) for row in outcomes),
        "evaluationEnd": max(str(row["evaluationSession"]) for row in outcomes),
        "primaryLabel": PRIMARY_LABEL,
        "priceFieldsRead": PRICE_FIELDS_READ,
        "intradayHighRead": False,
        "mfeClosePathsOpened": True,
        "monsterLabelsComputed": True,
        "confirmationOutcomesOpened": False,
        "knownSampleDiagnosticOpened": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "compositeWeightsFit": False,
        "technicalOverlayIncluded": False,
        "labelCounts": label_counts,
        "variantCount": len(result_rows),
        "variantResults": result_rows,
        "familyCandidates": family_candidates,
        "familyCandidateCount": candidate_count,
        "nextGate": (
            "Freeze unchanged 2019-2020 Monster Winner confirmation for the "
            "discovery-selected family candidates only."
        ),
    }
    (output / "monster-discovery-results.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-a-dir", type=Path, required=True)
    parser.add_argument("--path-feasibility-csv", type=Path, required=True)
    parser.add_argument("--path-feasibility-summary", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--corporate-actions", type=Path, required=True)
    parser.add_argument("--final-contract", type=Path, required=True)
    parser.add_argument("--provider-amendment", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        stage_a_dir=args.stage_a_dir,
        path_feasibility_csv=args.path_feasibility_csv,
        path_feasibility_summary=args.path_feasibility_summary,
        ledger_path=args.ledger,
        corporate_actions_path=args.corporate_actions,
        final_contract_path=args.final_contract,
        provider_amendment_path=args.provider_amendment,
        market_root=args.market_root,
        output=args.output,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "discoveryEvents": result["discoveryEvents"],
                "labelCounts": result["labelCounts"],
                "familyCandidates": result["familyCandidates"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
