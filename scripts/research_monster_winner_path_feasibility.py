"""Performance-blind holder-path feasibility audit for Monster Winner Enrichment v1."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_market_event_audit_v2 as p0
import research_phase1_feature_tournament_confirmation as confirmation
import research_phase1_feature_tournament_discovery as discovery

EXPECTED_EVENTS = 24190
EXPECTED_ISSUERS = 4729
PRIMARY_HORIZON = 252
EXPECTED_PATH_SESSIONS = 253
MIN_NEGATIVE_COVERAGE = 0.95
MAX_NEGATIVE_GAP = 5
SEALED_YEAR = 2023

ALLOWED_MARKET_FIELDS = {
    "ticker",
    "date",
    "volume",
    "trade_count",
    "terminal_candidate",
}
FORBIDDEN_OUTPUT_TOKENS = (
    "open",
    "high",
    "low",
    "close",
    "vwap",
    "return",
    "excess",
    "mfe",
    "threshold",
    "monster",
)


def _read_stage_a(stage_a_dir: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    summary, _cutpoints, rows = discovery._load_stage_a(stage_a_dir)
    if len(rows) != EXPECTED_EVENTS:
        raise ValueError("Stage-A event count changed")
    if len({str(row["issuerCik"]) for row in rows}) != EXPECTED_ISSUERS:
        raise ValueError("Stage-A distinct issuer count changed")
    return summary, rows


def _market_paths(root: Path) -> list[Path]:
    if (root / "2023").exists():
        raise ValueError("sealed OOS market directory mounted")
    paths: list[Path] = []
    for year in range(2016, 2023):
        matches = list(root.rglob(f"canonical-market-{year}.csv"))
        if len(matches) != 1:
            raise ValueError(
                f"expected one canonical-market-{year}.csv, got {len(matches)}"
            )
        paths.append(matches[0])
    return paths


def _regular_presence(
    root: Path,
    wanted_tickers: set[str],
) -> dict[str, set[str]]:
    result = {ticker: set() for ticker in wanted_tickers}
    for path in _market_paths(root):
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = set(reader.fieldnames or [])
            if not ALLOWED_MARKET_FIELDS.issubset(fields):
                raise ValueError(f"market presence fields missing: {path}")
            for row in reader:
                ticker = str(row.get("ticker") or "").strip().upper()
                if ticker not in result:
                    continue
                day = str(row.get("date") or "")[:10]
                if not day:
                    continue
                if int(day[:4]) >= SEALED_YEAR:
                    raise ValueError("sealed OOS market row encountered")
                terminal = (
                    str(row.get("terminal_candidate") or "").strip().lower()
                    == "true"
                )
                volume = int(float(row.get("volume") or 0))
                trade_count = int(float(row.get("trade_count") or 0))
                if not terminal and volume > 0 and trade_count > 0:
                    result[ticker].add(day)
    return result


def _provider_effective_date(
    ledger_row: dict[str, Any],
    actions: dict[str, dict[str, Any]],
) -> str:
    ids = discovery._action_ids(ledger_row)
    dates = {
        str(actions[action_id].get("actionDate") or "")[:10]
        for action_id in ids
        if action_id in actions
        and str(actions[action_id].get("actionDate") or "")[:10]
    }
    return next(iter(dates)) if len(dates) == 1 else ""


def _needs_effective_date(terms: dict[str, Any], ticker: str) -> bool:
    decision = str(terms["decision"])
    kind = str(terms["kind"])
    terminal = str(terms["terminalTicker"]).upper()
    basket = list(terms["basket"])

    if decision in {
        "NO_CONTINUITY_CORRECTION_REQUIRED",
        "SAME_SECURITY_CONTINUITY",
    }:
        return False
    if kind == "STOCK_DIVIDEND_QUANTITY":
        return False
    if (
        decision == "TRANSFORMED_HOLDER_CONSIDERATION"
        and terminal == ticker
        and not basket
        and float(terms["cash"]) == 0.0
        and float(terms["marketQuantity"]) == 1.0
    ):
        return False
    return True


def _effective_date(
    ledger_row: dict[str, Any],
    final_row: dict[str, Any] | None,
    amendment_row: dict[str, Any] | None,
    terms: dict[str, Any],
    actions: dict[str, dict[str, Any]],
) -> str:
    ticker = str(ledger_row["ticker"]).upper()
    if not _needs_effective_date(terms, ticker):
        return ""
    if amendment_row is not None:
        return str(amendment_row.get("effectiveDate") or "")[:10]
    if final_row is not None:
        return str(final_row.get("effectiveDate") or "")[:10]
    return _provider_effective_date(ledger_row, actions)


def _required_symbols(
    *,
    day: str,
    ticker: str,
    terms: dict[str, Any],
    effective_date: str,
) -> tuple[str, ...] | None:
    decision = str(terms["decision"])
    kind = str(terms["kind"])
    terminal = str(terms["terminalTicker"]).upper()
    basket = list(terms["basket"])

    if decision == "DISCONTINUOUS_NO_COMPLETE_VALUATION":
        if not effective_date:
            return None
        return (ticker,) if day < effective_date else None

    if kind == "STOCK_DIVIDEND_QUANTITY":
        return (ticker,)

    if decision in {
        "NO_CONTINUITY_CORRECTION_REQUIRED",
        "SAME_SECURITY_CONTINUITY",
    }:
        return (ticker,)

    if not effective_date:
        return None

    if day < effective_date:
        return (ticker,)

    if basket:
        return tuple(sorted(str(item["symbol"]).upper() for item in basket))

    quantity = float(terms["marketQuantity"])
    if quantity > 0:
        if not terminal:
            return None
        return (terminal,)

    if float(terms["cash"]) > 0:
        return ()

    return None


def _missing_stats(
    sessions: list[str],
    observable: list[bool],
) -> tuple[int, str, str]:
    max_run = 0
    run = 0
    missing_days: list[str] = []
    for day, ok in zip(sessions, observable, strict=True):
        if ok:
            run = 0
            continue
        missing_days.append(day)
        run += 1
        max_run = max(max_run, run)
    first = missing_days[0] if missing_days else ""
    last = missing_days[-1] if missing_days else ""
    return max_run, first, last


def _reason_codes(
    *,
    mandatory_unvalued: bool,
    deterministic_effective_date: bool,
    coverage_ratio: float,
    max_missing_run: int,
) -> list[str]:
    reasons: list[str] = []
    if mandatory_unvalued:
        reasons.append("MANDATORY_UNVALUED_CONSIDERATION")
    if not deterministic_effective_date:
        reasons.append("EFFECTIVE_DATE_UNDETERMINED")
    if coverage_ratio < MIN_NEGATIVE_COVERAGE:
        reasons.append("PATH_COVERAGE_BELOW_95_PCT")
    if max_missing_run > MAX_NEGATIVE_GAP:
        reasons.append("INTERNAL_GAP_GT_5")
    return reasons or ["NEGATIVE_LABEL_FEASIBLE"]


def _output_fields() -> list[str]:
    return [
        "eventNumber",
        "issuerCik",
        "ticker",
        "evaluationSession",
        "entrySession",
        "targetExitSession",
        "continuityDecision",
        "transformationKind",
        "effectiveDate",
        "successorSymbol",
        "basketSymbols",
        "requiredPathSessions",
        "observablePathSessions",
        "coverageRatio",
        "maxConsecutiveUnobservableSessions",
        "firstUnobservableSession",
        "lastUnobservableSession",
        "mandatoryUnvaluedConsideration",
        "deterministicEffectiveDate",
        "negativeLabelFeasible",
        "feasibilityReasons",
    ]


def run(
    *,
    stage_a_dir: Path,
    ledger_path: Path,
    corporate_actions_path: Path,
    final_contract_path: Path,
    provider_amendment_path: Path,
    market_root: Path,
    output: Path,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    stage_a_summary, events = _read_stage_a(stage_a_dir)
    ledger = discovery._load_ledger(ledger_path)
    final_rows = discovery._load_final_contract(final_contract_path)
    actions = discovery._load_actions(corporate_actions_path)
    provider_amendment = confirmation._load_provider_amendment(
        provider_amendment_path
    )

    ledger_252 = [
        row for row in ledger if int(row["horizon"]) == PRIMARY_HORIZON
    ]
    if len(ledger_252) != EXPECTED_EVENTS:
        raise ValueError("252-session ledger row count changed")

    ledger_by_base = {
        discovery._base_key(row): row
        for row in ledger_252
    }
    if len(ledger_by_base) != EXPECTED_EVENTS:
        raise ValueError("duplicate 252-session ledger base key")

    final_by_key = {
        discovery._horizon_key(row): row
        for row in final_rows
    }
    unresolved_keys = {
        discovery._horizon_key(row)
        for row in ledger
        if row["state"] == "UNRESOLVED_CONTINUITY"
    }
    if set(final_by_key) != unresolved_keys:
        raise ValueError("final continuity set no longer matches unresolved ledger")

    sessions = p0._expected_sessions()
    session_index = {day: index for index, day in enumerate(sessions)}

    prepared: list[dict[str, Any]] = []
    wanted_tickers: set[str] = set()

    for event in events:
        base = discovery._base_key(event)
        ledger_row = ledger_by_base.get(base)
        if ledger_row is None:
            raise ValueError("Stage-A event missing 252-session continuity row")

        key = discovery._horizon_key(ledger_row)
        final_row = final_by_key.get(key)
        amendment_row = provider_amendment.get(key)
        terms = confirmation._terms_for_confirmation(
            ledger_row,
            final_row,
            amendment_row,
            actions,
        )
        effective = _effective_date(
            ledger_row,
            final_row,
            amendment_row,
            terms,
            actions,
        )

        entry = str(event["entrySession"])
        target = str(ledger_row["targetExitSession"])
        entry_idx = session_index.get(entry)
        target_idx = session_index.get(target)
        if entry_idx is None or target_idx is None:
            raise ValueError("path boundary absent from XNYS calendar")
        if target_idx - entry_idx != PRIMARY_HORIZON:
            raise ValueError("252-session path clock changed")
        path_sessions = sessions[entry_idx : target_idx + 1]
        if len(path_sessions) != EXPECTED_PATH_SESSIONS:
            raise ValueError("expected 253 close-observation sessions")
        if any(int(day[:4]) >= SEALED_YEAR for day in path_sessions):
            raise ValueError("sealed OOS path session encountered")

        ticker = str(event["ticker"]).upper()
        wanted_tickers.add(ticker)
        terminal = str(terms["terminalTicker"]).upper()
        if terminal:
            wanted_tickers.add(terminal)
        for leg in terms["basket"]:
            wanted_tickers.add(str(leg["symbol"]).upper())

        prepared.append(
            {
                "event": event,
                "ledger": ledger_row,
                "terms": terms,
                "effectiveDate": effective,
                "pathSessions": path_sessions,
            }
        )

    presence = _regular_presence(market_root, wanted_tickers)

    rows: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    decision_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    year_counts: dict[str, Counter[str]] = {}

    for item in prepared:
        event = item["event"]
        terms = item["terms"]
        path_sessions = item["pathSessions"]
        effective = str(item["effectiveDate"])
        ticker = str(event["ticker"]).upper()

        needs_effective = _needs_effective_date(terms, ticker)
        deterministic_effective = not needs_effective or bool(effective)
        mandatory_unvalued = (
            str(terms["decision"]) == "DISCONTINUOUS_NO_COMPLETE_VALUATION"
        )

        observable: list[bool] = []
        for day in path_sessions:
            required = _required_symbols(
                day=day,
                ticker=ticker,
                terms=terms,
                effective_date=effective,
            )
            if required is None:
                observable.append(False)
            elif not required:
                observable.append(True)
            else:
                observable.append(
                    all(day in presence.get(symbol, set()) for symbol in required)
                )

        observable_n = sum(observable)
        coverage = observable_n / len(path_sessions)
        max_run, first_missing, last_missing = _missing_stats(
            path_sessions,
            observable,
        )
        reasons = _reason_codes(
            mandatory_unvalued=mandatory_unvalued,
            deterministic_effective_date=deterministic_effective,
            coverage_ratio=coverage,
            max_missing_run=max_run,
        )
        feasible = reasons == ["NEGATIVE_LABEL_FEASIBLE"]

        decision = str(terms["decision"])
        kind = str(terms["kind"])
        reason_counts.update(reasons)
        decision_counts[decision] += 1
        kind_counts[kind] += 1
        year = str(event["evaluationSession"])[:4]
        year_counts.setdefault(year, Counter())
        year_counts[year]["events"] += 1
        year_counts[year][
            "negativeLabelFeasible" if feasible else "mfeUnknownIfNoPositive"
        ] += 1

        row = {
            "eventNumber": int(event["eventNumber"]),
            "issuerCik": str(event["issuerCik"]),
            "ticker": ticker,
            "evaluationSession": str(event["evaluationSession"]),
            "entrySession": str(event["entrySession"]),
            "targetExitSession": str(item["ledger"]["targetExitSession"]),
            "continuityDecision": decision,
            "transformationKind": kind,
            "effectiveDate": effective,
            "successorSymbol": str(terms["terminalTicker"]).upper(),
            "basketSymbols": ";".join(
                sorted(str(leg["symbol"]).upper() for leg in terms["basket"])
            ),
            "requiredPathSessions": len(path_sessions),
            "observablePathSessions": observable_n,
            "coverageRatio": round(coverage, 12),
            "maxConsecutiveUnobservableSessions": max_run,
            "firstUnobservableSession": first_missing,
            "lastUnobservableSession": last_missing,
            "mandatoryUnvaluedConsideration": mandatory_unvalued,
            "deterministicEffectiveDate": deterministic_effective,
            "negativeLabelFeasible": feasible,
            "feasibilityReasons": ";".join(reasons),
        }
        rows.append(row)

    if len(rows) != EXPECTED_EVENTS:
        raise ValueError("feasibility row count changed")
    rows.sort(key=lambda row: int(row["eventNumber"]))

    fields = _output_fields()
    if any(
        token in field.lower()
        for field in fields
        for token in FORBIDDEN_OUTPUT_TOKENS
    ):
        raise ValueError("forbidden outcome token in feasibility output schema")

    csv_path = output / "monster-path-feasibility.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    feasible_n = sum(bool(row["negativeLabelFeasible"]) for row in rows)
    unknown_n = len(rows) - feasible_n
    coverages = sorted(float(row["coverageRatio"]) for row in rows)

    def percentile(fraction: float) -> float:
        if not coverages:
            return 0.0
        index = round((len(coverages) - 1) * fraction)
        return coverages[index]

    summary = {
        "schemaVersion": "1.0.0",
        "status": "MONSTER_WINNER_ENRICHMENT_V1_PATH_FEASIBILITY_AUDITED",
        "definitionId": "MONSTER_WINNER_ENRICHMENT_V1",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "marketFieldsRead": sorted(ALLOWED_MARKET_FIELDS),
        "outcomeFieldsRead": [],
        "monsterLabelsComputed": False,
        "thresholdCrossingsRead": False,
        "mfeValuesComputed": False,
        "validationOpened": False,
        "knownSampleDiagnosticOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceStageAEvents": EXPECTED_EVENTS,
        "distinctIssuers": EXPECTED_ISSUERS,
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "pathObservationSessions": EXPECTED_PATH_SESSIONS,
        "negativeCoverageThreshold": MIN_NEGATIVE_COVERAGE,
        "negativeMaxGapSessions": MAX_NEGATIVE_GAP,
        "negativeLabelFeasibleEvents": feasible_n,
        "negativeLabelFeasibleShare": feasible_n / len(rows),
        "mfeUnknownIfNoPositiveEvents": unknown_n,
        "mfeUnknownIfNoPositiveShare": unknown_n / len(rows),
        "coverageDistribution": {
            "min": coverages[0],
            "p01": percentile(0.01),
            "p05": percentile(0.05),
            "p10": percentile(0.10),
            "median": percentile(0.50),
            "p90": percentile(0.90),
            "p95": percentile(0.95),
            "p99": percentile(0.99),
            "max": coverages[-1],
        },
        "reasonCounts": dict(sorted(reason_counts.items())),
        "continuityDecisionCounts": dict(sorted(decision_counts.items())),
        "transformationKindCounts": dict(sorted(kind_counts.items())),
        "evaluationYearCounts": {
            year: dict(sorted(counts.items()))
            for year, counts in sorted(year_counts.items())
        },
        "providerCompletenessAmendmentRows": len(provider_amendment),
        "sourceStageAScopeKeySha256": stage_a_summary["scope"]["scopeKeySha256"],
        "nextGate": (
            "Inspect performance-blind feasibility failures, then freeze the "
            "exact Monster Winner outcome execution contract before MFE prices."
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-a-dir", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--corporate-actions", type=Path, required=True)
    parser.add_argument("--final-contract", type=Path, required=True)
    parser.add_argument("--provider-amendment", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        stage_a_dir=args.stage_a_dir,
        ledger_path=args.ledger,
        corporate_actions_path=args.corporate_actions,
        final_contract_path=args.final_contract,
        provider_amendment_path=args.provider_amendment,
        market_root=args.market_root,
        output=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
