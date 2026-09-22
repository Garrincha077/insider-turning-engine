"""Run frozen 2019-2020 Monster Winner confirmation for selected family candidates."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_market_event_audit_v2 as p0
import research_monster_winner_discovery as monster
import research_monster_winner_path_feasibility as feasibility
import research_phase1_feature_tournament_confirmation as confirmation
import research_phase1_feature_tournament_discovery as discovery

CONFIRMATION_START = "2019-01-01"
CONFIRMATION_END = "2020-12-31"
EXPECTED_EVENTS = 9850
EXPECTED_BY_YEAR = {"2019": 4529, "2020": 5321}
CANDIDATES = ("F3_DRAWDOWN_252", "F4_DISTANCE_BELOW")
PRIMARY_LABEL = "M100_252_CLOSE"
MIN_NEGATIVE_COVERAGE = 0.95
MAX_NEGATIVE_GAP = 5

def _market_paths(root: Path) -> list[Path]:
    if (root / "2023").exists():
        raise ValueError("sealed OOS market year mounted")
    paths: list[Path] = []
    for year in range(2019, 2023):
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
    maps: dict[str, dict[str, tuple[float, float, int, int, bool]]] = {
        ticker: {} for ticker in wanted
    }
    for path in _market_paths(root):
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader)
            index = {name: pos for pos, name in enumerate(header)}
            required = {
                "ticker", "date", "open", "close",
                "volume", "trade_count", "terminal_candidate",
            }
            if not required.issubset(index):
                raise ValueError(f"market outcome fields missing: {path}")
            for raw in reader:
                ticker = raw[index["ticker"]].strip().upper()
                if ticker not in maps:
                    continue
                day = raw[index["date"]][:10]
                if int(day[:4]) >= 2023:
                    raise ValueError("sealed OOS market row encountered")
                maps[ticker][day] = (
                    float(raw[index["open"]]),
                    float(raw[index["close"]]),
                    int(float(raw[index["volume"]] or 0)),
                    int(float(raw[index["trade_count"]] or 0)),
                    raw[index["terminal_candidate"]].strip().lower() == "true",
                )
    return maps

def _load_discovery_result(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "MONSTER_WINNER_ENRICHMENT_V1_DISCOVERY_COMPLETE":
        raise ValueError("unexpected discovery result")
    expected = {
        "F3": "F3_DRAWDOWN_252",
        "F4": "F4_DISTANCE_BELOW",
    }
    for family, variant in expected.items():
        item = payload.get("familyCandidates", {}).get(family, {})
        if item.get("status") != "MONSTER_DISCOVERY_FAMILY_CANDIDATE_FROZEN":
            raise ValueError(f"{family} discovery candidate missing")
        if item.get("variantId") != variant:
            raise ValueError(f"{family} discovery candidate changed")
    for family in ("F1", "F2"):
        item = payload.get("familyCandidates", {}).get(family, {})
        if item.get("status") != "NO_MONSTER_DISCOVERY_CANDIDATE":
            raise ValueError(f"{family} unexpectedly advanced")

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
        if target_idx - entry_idx != 252:
            raise ValueError("252-session target clock changed")
        path_sessions = sessions[entry_idx : target_idx + 1]
        if len(path_sessions) != 253:
            raise ValueError("confirmation path length changed")
        if any(int(day[:4]) >= 2023 for day in path_sessions):
            raise ValueError("sealed OOS path session")

        entry_row = maps.get(ticker, {}).get(entry)
        if not monster._regular(entry_row):
            raise ValueError("frozen confirmation exact entry bar disappeared")
        entry_open = float(entry_row[0])
        if entry_open <= 0:
            raise ValueError("non-positive exact entry open")

        values = [
            monster._holder_close(
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

        row: dict[str, Any] = dict(source)
        row.update(
            {
                "targetExitSession252": target,
                "continuityDecision252": str(terms["decision"]),
                "transformationKind252": str(terms["kind"]),
                "effectiveDate252": effective,
            }
        )

        for label_id, (horizon, multiple) in monster.LABEL_SPECS.items():
            label = monster._label(
                values=values[: horizon + 1],
                sessions=path_sessions[: horizon + 1],
                entry_open=entry_open,
                multiple=multiple,
                mandatory_unvalued=mandatory_unvalued,
                deterministic_effective=deterministic_effective,
            )
            row[label_id] = label["state"]
            row[f"{label_id}_FIRST"] = label["firstCrossingSession"]
            row[f"{label_id}_COVERAGE"] = label["coverageRatio"]
            row[f"{label_id}_MAX_GAP"] = label["maxMissingRun"]

        observed, coverage, max_gap = monster._path_stats(values)
        frozen = path_feasibility.get(base)
        if frozen is None:
            raise ValueError("confirmation event missing path-feasibility row")
        if observed != int(frozen["observablePathSessions"]):
            raise ValueError("confirmation observability differs from blind audit")
        if abs(coverage - float(frozen["coverageRatio"])) > 1e-9:
            raise ValueError("confirmation coverage differs from blind audit")
        if max_gap != int(frozen["maxConsecutiveUnobservableSessions"]):
            raise ValueError("confirmation max gap differs from blind audit")
        local_feasible = (
            not mandatory_unvalued
            and deterministic_effective
            and coverage >= MIN_NEGATIVE_COVERAGE
            and max_gap <= MAX_NEGATIVE_GAP
        )
        frozen_feasible = str(frozen["negativeLabelFeasible"]).lower() == "true"
        if local_feasible != frozen_feasible:
            raise ValueError("confirmation feasibility differs from blind audit")
        row["NEGATIVE_LABEL_FEASIBLE_252"] = local_feasible
        observed_max = max((v for v in values if v is not None), default=None)
        row["MAX_OBSERVED_MULTIPLE_252"] = (
            observed_max / entry_open if observed_max is not None else None
        )
        result.append(row)

    if len(result) != EXPECTED_EVENTS:
        raise ValueError("confirmation event count changed")
    return result

def _evaluate(
    *,
    variant_id: str,
    outcomes: list[dict[str, Any]],
    cutpoints: dict[str, Any],
) -> dict[str, Any]:
    grouped: list[dict[str, Any]] = []
    for source in outcomes:
        membership = monster._membership(source, variant_id, cutpoints)
        if membership is None:
            continue
        row = dict(source)
        row["_group"] = membership
        grouped.append(row)

    lift, preferred, complement = monster._lift(grouped, PRIMARY_LABEL)
    preferred_rows = [r for r in grouped if r["_group"] == "PREFERRED"]
    complement_rows = [r for r in grouped if r["_group"] == "COMPLEMENT"]
    total_positive = preferred["positive"] + complement["positive"]
    capture = preferred["positive"] / total_positive if total_positive else None
    review_share = len(preferred_rows) / len(grouped) if grouped else None
    preferred_resolvable = preferred["positive"] + preferred["negative"]
    distinct_issuers = len({str(r["issuerCik"]) for r in preferred_rows})

    year_lifts: dict[str, float | None] = {}
    for year in ("2019", "2020"):
        subset = [
            r for r in grouped
            if str(r["evaluationSession"]).startswith(year)
        ]
        year_lifts[year] = monster._lift(subset, PRIMARY_LABEL)[0]

    adv_q20 = float(cutpoints["DOLLAR_ADV_20"]["q20"])
    outside_adv = [
        r
        for r in grouped
        if (
            (v := discovery._optional_float(r.get("DOLLAR_ADV_20"))) is not None
            and v > adv_q20
        )
    ]
    outside_adv_lift = monster._lift(outside_adv, PRIMARY_LABEL)[0]

    preferred_positive = [
        r for r in preferred_rows if r[PRIMARY_LABEL] == "POSITIVE"
    ]
    by_issuer = Counter(str(r["issuerCik"]) for r in preferred_positive)
    largest_issuer_share = (
        max(by_issuer.values()) / len(preferred_positive)
        if preferred_positive else None
    )

    secondary: dict[str, Any] = {}
    for label in monster.LABEL_SPECS:
        label_lift, pref, comp = monster._lift(grouped, label)
        secondary[label] = {
            "lift": label_lift,
            "preferred": {
                **pref,
                "observedPositiveDensity": monster._density(pref),
                "evaluableHitRate": monster._evaluable_hit_rate(pref),
                "unknownShare": pref["unknown"] / pref["N"] if pref["N"] else None,
            },
            "complement": {
                **comp,
                "observedPositiveDensity": monster._density(comp),
                "evaluableHitRate": monster._evaluable_hit_rate(comp),
                "unknownShare": comp["unknown"] / comp["N"] if comp["N"] else None,
            },
        }

    checks = {
        "preferredResolvableNAtLeast150": preferred_resolvable >= 150,
        "preferredDistinctIssuersAtLeast75": distinct_issuers >= 75,
        "preferredM100HitsAtLeast10": preferred["positive"] >= 10,
        "pooledM100LiftAtLeast1_25": lift is not None and lift >= 1.25,
        "pooledM100CaptureAtLeast15Pct": capture is not None and capture >= 0.15,
        "2019M100LiftAbove1": (
            year_lifts["2019"] is not None and year_lifts["2019"] > 1.0
        ),
        "2020M100LiftAbove1": (
            year_lifts["2020"] is not None and year_lifts["2020"] > 1.0
        ),
        "outsideBottomAdvM100LiftAbove1": (
            outside_adv_lift is not None and outside_adv_lift > 1.0
        ),
        "singleIssuerM100ShareAtMost20Pct": (
            largest_issuer_share is not None
            and largest_issuer_share <= 0.20
        ),
    }

    return {
        "variantId": variant_id,
        "family": monster.VARIANTS[variant_id]["family"],
        "status": (
            "MONSTER_CONFIRMED_DEVELOPMENT_CANDIDATE"
            if all(checks.values())
            else "MONSTER_CONFIRMATION_FAIL"
        ),
        "observedCohortN": len(grouped),
        "preferredN": len(preferred_rows),
        "complementN": len(complement_rows),
        "preferredResolvableN": preferred_resolvable,
        "preferredDistinctIssuers": distinct_issuers,
        "reviewShare": review_share,
        "primaryM100": {
            "lift": lift,
            "capture": capture,
            "preferred": secondary[PRIMARY_LABEL]["preferred"],
            "complement": secondary[PRIMARY_LABEL]["complement"],
            "yearLifts": year_lifts,
            "outsideBottomDollarAdvLift": outside_adv_lift,
            "largestIssuerShareOfPreferredM100": largest_issuer_share,
        },
        "secondaryLabels": secondary,
        "confirmationChecks": checks,
        "confirmationPass": all(checks.values()),
    }

def run(
    *,
    stage_a_dir: Path,
    path_feasibility_csv: Path,
    path_feasibility_summary: Path,
    ledger_path: Path,
    corporate_actions_path: Path,
    final_contract_path: Path,
    provider_amendment_path: Path,
    discovery_result_path: Path,
    market_root: Path,
    output: Path,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    _load_discovery_result(discovery_result_path)

    _stage_summary, cutpoints, matrix = discovery._load_stage_a(stage_a_dir)
    events = [
        dict(row)
        for row in matrix
        if CONFIRMATION_START <= str(row["evaluationSession"]) <= CONFIRMATION_END
    ]
    if len(events) != EXPECTED_EVENTS:
        raise ValueError("confirmation event count changed")
    counts = Counter(str(row["evaluationSession"])[:4] for row in events)
    if dict(sorted(counts.items())) != EXPECTED_BY_YEAR:
        raise ValueError("confirmation annual event counts changed")

    path_feasibility = monster._load_path_feasibility(
        path_feasibility_csv,
        path_feasibility_summary,
    )
    ledger = discovery._load_ledger(ledger_path)
    final_rows = discovery._load_final_contract(final_contract_path)
    actions = discovery._load_actions(corporate_actions_path)
    provider_amendment = confirmation._load_provider_amendment(
        provider_amendment_path
    )
    prepared, wanted = monster._terms_and_paths(
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

    results = [
        _evaluate(variant_id=variant, outcomes=outcomes, cutpoints=cutpoints)
        for variant in CANDIDATES
    ]
    confirmed = [r["variantId"] for r in results if r["confirmationPass"]]

    fields = [
        "eventNumber","issuerCik","ticker","evaluationSession","entrySession",
        "targetExitSession252","continuityDecision252","transformationKind252",
        "effectiveDate252","NEGATIVE_LABEL_FEASIBLE_252","MAX_OBSERVED_MULTIPLE_252",
    ]
    for label in monster.LABEL_SPECS:
        fields += [
            label,f"{label}_FIRST",f"{label}_COVERAGE",f"{label}_MAX_GAP"
        ]
    with (output / "monster-confirmation-event-outcomes.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in outcomes:
            writer.writerow({field: row.get(field, "") for field in fields})

    summary = {
        "schemaVersion":"1.0.0",
        "status":"MONSTER_WINNER_ENRICHMENT_V1_CONFIRMATION_COMPLETE",
        "definitionId":"MONSTER_WINNER_ENRICHMENT_V1",
        "researchOnly":True,
        "confirmationEvents":len(outcomes),
        "evaluationStart":min(str(r["evaluationSession"]) for r in outcomes),
        "evaluationEnd":max(str(r["evaluationSession"]) for r in outcomes),
        "candidateCount":len(CANDIDATES),
        "candidateResults":results,
        "confirmedCandidates":confirmed,
        "confirmedCandidateCount":len(confirmed),
        "priceFieldsRead":["entry_open","exact_path_close"],
        "intradayHighRead":False,
        "knownSampleDiagnosticOpened":False,
        "validationOpened":False,
        "oosOpened":False,
        "productionScoringChanged":False,
        "technicalOverlayIncluded":False,
        "nextGate":(
            "If desired, freeze a separately labelled 2021-2022 known-sample "
            "retrospective diagnostic for confirmed candidates only; 2023+ stays sealed."
        ),
    }
    (output / "monster-confirmation-results.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True)+"\n", encoding="utf-8"
    )
    return summary

def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--stage-a-dir",type=Path,required=True)
    parser.add_argument("--path-feasibility-csv",type=Path,required=True)
    parser.add_argument("--path-feasibility-summary",type=Path,required=True)
    parser.add_argument("--ledger",type=Path,required=True)
    parser.add_argument("--corporate-actions",type=Path,required=True)
    parser.add_argument("--final-contract",type=Path,required=True)
    parser.add_argument("--provider-amendment",type=Path,required=True)
    parser.add_argument("--discovery-result",type=Path,required=True)
    parser.add_argument("--market-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=run(
        stage_a_dir=args.stage_a_dir,
        path_feasibility_csv=args.path_feasibility_csv,
        path_feasibility_summary=args.path_feasibility_summary,
        ledger_path=args.ledger,
        corporate_actions_path=args.corporate_actions,
        final_contract_path=args.final_contract,
        provider_amendment_path=args.provider_amendment,
        discovery_result_path=args.discovery_result,
        market_root=args.market_root,
        output=args.output,
    )
    print(json.dumps({
        "status":result["status"],
        "confirmedCandidates":result["confirmedCandidates"],
        "candidateResults":result["candidateResults"],
    },indent=2,sort_keys=True))

if __name__=="__main__":
    main()
