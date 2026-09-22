"""Run the frozen 2021-2022 F2 validation after continuity reaches zero."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_b0 as b0
import research_phase1_feature_tournament_discovery as discovery
import research_phase1_feature_tournament_stage_a as stage_a

PRIMARY_HORIZON = 126
EXPECTED_SCOPE_ROWS = 7493
EXPECTED_CONTRACT_ROWS = 191
EXPECTED_SCOPE_KEY = (
    "sha256:8f2d7d09c43689007d22690d8c846cf253532d8cff15997c8def2ddde8df7bc3"
)
EXPECTED_CONTRACT_KEY = (
    "sha256:fe81e31a04a4e5f69eb07778685bc8799860eef37653af5479d79c5aefc1c18f"
)
KEY_FIELDS = (
    "eventNumber",
    "issuerCik",
    "ticker",
    "evaluationSession",
    "entrySession",
    "horizon",
    "targetExitSession",
)


def _key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row[field]) for field in KEY_FIELDS)


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
    material = [{field: row[field] for field in fields} for row in rows]
    raw = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _load_confirmation(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    required = {
        "status": "PHASE1_INSIDER_FEATURE_TOURNAMENT_CONFIRMATION_COMPLETE",
        "confirmedCandidateCount": 1,
        "confirmationComplete": True,
        "validationOpened": False,
        "validationEventOutcomesRead": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for field, expected in required.items():
        if payload.get(field) != expected:
            raise ValueError(f"confirmation contract mismatch: {field}")
    expected = [
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
    ]
    if payload.get("confirmedCandidates") != expected:
        raise ValueError("frozen F2 validation candidate changed")
    return payload


def _load_scope(
    csv_path: Path,
    summary_path: Path,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    summary = _read_json(summary_path)
    required = {
        "status": "PHASE1_FEATURE_TOURNAMENT_VALIDATION_SCOPE_FROZEN",
        "confirmedCandidate": "F2_DIRECT_VS_INDIRECT",
        "frozenPreferred": "INDIRECT_ONLY",
        "frozenComplement": "DIRECT_ONLY",
        "researchOnly": True,
        "outcomesRead": False,
        "priceOutcomeFieldsRead": [],
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "validationScopeRows": EXPECTED_SCOPE_ROWS,
        "scopeKeySha256": EXPECTED_SCOPE_KEY,
    }
    for field, expected in required.items():
        if summary.get(field) != expected:
            raise ValueError(f"validation scope mismatch: {field}")

    with csv_path.open(encoding="utf-8", newline="") as stream:
        rows = [dict(row) for row in csv.DictReader(stream)]
    if len(rows) != EXPECTED_SCOPE_ROWS:
        raise ValueError("validation scope row count changed")
    if len({_key(row) for row in rows}) != EXPECTED_SCOPE_ROWS:
        raise ValueError("duplicate validation scope key")
    if _scope_digest(rows) != EXPECTED_SCOPE_KEY:
        raise ValueError("validation scope semantic digest changed")
    for row in rows:
        if row["horizon"] != str(PRIMARY_HORIZON):
            raise ValueError("validation scope contains non-primary horizon")
        if not "2021-01-01" <= row["evaluationSession"] <= "2022-12-31":
            raise ValueError("validation evaluation period changed")
        if row["targetExitSession"] > "2022-12-31":
            raise ValueError("validation target crossed sealed boundary")
    return summary, rows


def _load_contract(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = _read_json(path)
    required = {
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "FINAL_CONTINUITY_COMPLETE"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceScopeRows": EXPECTED_SCOPE_ROWS,
        "classifiedRows": EXPECTED_CONTRACT_ROWS,
        "unresolvedRows": 0,
        "classifiedKeySha256": EXPECTED_CONTRACT_KEY,
        "sourceValidationScopeKeySha256": EXPECTED_SCOPE_KEY,
        "resolutionComplete": True,
        "finalResolutionContractCreated": True,
    }
    for field, expected in required.items():
        if payload.get(field) != expected:
            raise ValueError(f"final continuity contract mismatch: {field}")
    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_CONTRACT_ROWS:
        raise ValueError("final continuity resolution rows changed")
    if len({_key(row) for row in rows}) != EXPECTED_CONTRACT_ROWS:
        raise ValueError("duplicate final continuity key")
    return payload, [dict(row) for row in rows]


def _terms(
    source: dict[str, Any],
    contract: dict[str, Any] | None,
) -> dict[str, Any]:
    ticker = str(source["ticker"]).upper()
    if contract is None:
        return {
            "decision": "NO_CONTINUITY_CORRECTION_REQUIRED",
            "kind": "ORDINARY_ADJUSTED_PRICE",
            "terminalTicker": ticker,
            "marketQuantity": 1.0,
            "legalQuantity": 1.0,
            "cash": 0.0,
            "basket": [],
        }

    decision = str(contract["resolutionDecision"])
    kind = str(contract.get("transformationKind") or "")
    successor = str(contract.get("successorSymbol") or "").upper()
    quantity = float(contract.get("successorSharesPerEntryShare") or 0.0)
    cash = float(contract.get("cashPerEntryShare") or 0.0)
    basket = contract.get("basket") or []
    if quantity < 0 or cash < 0:
        raise ValueError("negative final continuity economics")

    if decision == "SAME_SECURITY_CONTINUITY":
        if successor != ticker or quantity != 1.0 or cash != 0.0:
            raise ValueError("invalid same-security validation terms")
        return {
            "decision": decision,
            "kind": "PRICE_CONTINUOUS_ADJUSTED",
            "terminalTicker": ticker,
            "marketQuantity": 1.0,
            "legalQuantity": 1.0,
            "cash": 0.0,
            "basket": [],
        }

    if decision == "SYMBOL_CHANGED_SAME_SECURITY":
        if not successor or quantity != 1.0 or cash != 0.0:
            raise ValueError("invalid symbol-change validation terms")
        return {
            "decision": decision,
            "kind": kind,
            "terminalTicker": successor,
            "marketQuantity": 1.0,
            "legalQuantity": 1.0,
            "cash": 0.0,
            "basket": [],
        }

    if decision == "TRANSFORMED_HOLDER_CONSIDERATION":
        if basket:
            raise ValueError("unexpected basket in transformed validation row")
        if kind == "STOCK_DIVIDEND_QUANTITY":
            if successor != ticker or quantity <= 0 or cash != 0.0:
                raise ValueError("invalid adjusted stock-dividend terms")
            return {
                "decision": decision,
                "kind": kind,
                "terminalTicker": ticker,
                "marketQuantity": 1.0,
                "legalQuantity": quantity,
                "cash": 0.0,
                "basket": [],
            }
        if quantity > 0 and not successor:
            raise ValueError("stock consideration lacks successor ticker")
        if quantity == 0 and cash == 0:
            raise ValueError("transformed validation row lacks consideration")
        return {
            "decision": decision,
            "kind": kind,
            "terminalTicker": successor,
            "marketQuantity": quantity,
            "legalQuantity": quantity,
            "cash": cash,
            "basket": [],
        }

    raise ValueError(f"unsupported validation continuity decision: {decision}")


def _market_maps(
    market_root: Path,
    output: Path,
    tickers: set[str],
) -> tuple[dict[str, dict[str, tuple[Any, ...]]], Path]:
    if (market_root / "2023").exists():
        raise ValueError("sealed 2023 market directory mounted")
    paths = stage_a._market_paths(
        market_root,
        "canonical-market",
        (2021, 2022),
    )
    db_path = output / "f2-validation.sqlite"
    stage_a._build_market_db(paths, db_path)
    conn = sqlite3.connect(db_path)
    maps: dict[str, dict[str, tuple[Any, ...]]] = {}
    try:
        for ticker in sorted(tickers | {"SPY"}):
            data = conn.execute(
                "SELECT date,open,high,low,close,volume,trade_count,terminal "
                "FROM market WHERE ticker=? ORDER BY date",
                (ticker,),
            ).fetchall()
            maps[ticker] = {str(row[0]): row for row in data}
    finally:
        conn.close()
    return maps, db_path


def _value(
    scope_rows: list[dict[str, str]],
    contract_rows: list[dict[str, Any]],
    market_root: Path,
    output: Path,
) -> list[dict[str, Any]]:
    contract_by_key = {_key(row): row for row in contract_rows}
    scope_by_key = {_key(row): row for row in scope_rows}
    if not set(contract_by_key).issubset(scope_by_key):
        raise ValueError("continuity contract contains row outside validation scope")

    terms_by_key: dict[tuple[str, ...], dict[str, Any]] = {}
    tickers = {str(row["ticker"]).upper() for row in scope_rows}
    for row in scope_rows:
        key = _key(row)
        terms = _terms(row, contract_by_key.get(key))
        terms_by_key[key] = terms
        terminal = str(terms["terminalTicker"])
        if terminal:
            tickers.add(terminal)

    maps, db_path = _market_maps(market_root, output, tickers)
    results: list[dict[str, Any]] = []
    try:
        for source in scope_rows:
            key = _key(source)
            terms = terms_by_key[key]
            ticker = str(source["ticker"]).upper()
            entry_session = str(source["entrySession"])
            target = str(source["targetExitSession"])
            entry = maps.get(ticker, {}).get(entry_session)
            spy_entry = maps["SPY"].get(entry_session)
            if not b0._regular(entry) or not b0._regular(spy_entry):
                raise ValueError("frozen validation entry bar disappeared")

            entry_open = float(entry[1])
            spy_entry_open = float(spy_entry[1])
            raw: float | None = None
            excess: float | None = None
            reason = ""
            terminal_value: float | None = None

            spy_exit = maps["SPY"].get(target)
            if not b0._regular(spy_exit):
                reason = "MISSING_EXACT_SPY_EXIT_BAR"
            else:
                terminal_value = float(terms["cash"])
                quantity = float(terms["marketQuantity"])
                terminal_ticker = str(terms["terminalTicker"])
                if quantity:
                    terminal = maps.get(terminal_ticker, {}).get(target)
                    if not b0._regular(terminal):
                        reason = "MISSING_EXACT_TERMINAL_HOLDER_BAR"
                    else:
                        terminal_value += quantity * float(terminal[4])
                if not reason:
                    spy_return = float(spy_exit[4]) / spy_entry_open - 1.0
                    raw = terminal_value / entry_open - 1.0
                    excess = raw - spy_return

            row = dict(source)
            row["entryOpen"] = entry_open
            row["raw_126"] = raw
            row["excess_126"] = excess
            row["reason_126"] = reason or None
            row["continuity_126"] = terms["decision"]
            row["valuationKind_126"] = terms["kind"]
            row["terminalTicker_126"] = terms["terminalTicker"]
            row["legalSuccessorQuantity_126"] = terms["legalQuantity"]
            row["marketValuationQuantity_126"] = terms["marketQuantity"]
            row["cashPerEntryShare_126"] = terms["cash"]
            row["terminalHolderValue_126"] = terminal_value
            category = str(row.get("F2_DIRECT_VS_INDIRECT") or "")
            row["_group"] = (
                "PREFERRED"
                if category == "INDIRECT_ONLY"
                else "COMPLEMENT"
                if category == "DIRECT_ONLY"
                else ""
            )
            results.append(row)
    finally:
        db_path.unlink(missing_ok=True)
    return results


def _evaluate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    contrast = [
        row
        for row in rows
        if row["_group"] in {"PREFERRED", "COMPLEMENT"}
    ]
    preferred = discovery._group_summary(
        contrast,
        PRIMARY_HORIZON,
        "PREFERRED",
    )
    complement = discovery._group_summary(
        contrast,
        PRIMARY_HORIZON,
        "COMPLEMENT",
    )
    event_increment = discovery._increment(contrast, PRIMARY_HORIZON)
    issuer_increment = discovery._equal_weight_increment(
        contrast,
        "issuerCik",
    )
    session_increment = discovery._equal_weight_increment(
        contrast,
        "entrySession",
    )
    top1_increment, top1_removed = discovery._top1_removed_increment(contrast)
    year_increments = {
        year: discovery._increment(
            [
                row
                for row in contrast
                if str(row["evaluationSession"]).startswith(year)
            ],
            PRIMARY_HORIZON,
        )
        for year in ("2021", "2022")
    }

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
        "2021EventWeightedIncrementalMeanPositive": (
            year_increments["2021"] is not None
            and year_increments["2021"] > 0
        ),
        "2022EventWeightedIncrementalMeanPositive": (
            year_increments["2022"] is not None
            and year_increments["2022"] > 0
        ),
    }
    passed = all(checks.values())
    return {
        "family": "F2",
        "variantId": "F2_DIRECT_VS_INDIRECT",
        "coverageClass": "GENERAL_ELIGIBLE",
        "frozenGroupDefinition": {
            "kind": "F2_DYNAMIC",
            "sourceFeature": "F2_DIRECT_VS_INDIRECT",
            "preferred": "INDIRECT_ONLY",
            "complement": "DIRECT_ONLY",
        },
        "status": (
            "VALIDATED_CANDIDATE"
            if passed
            else "VALIDATION_FAIL_FROZEN"
        ),
        "validated": passed,
        "preferred": preferred,
        "complement": complement,
        "primary126": {
            "pooledEventWeightedIncrementalMean": event_increment,
            "pooledIssuerEqualWeightIncrementalMean": issuer_increment,
            "pooledEntrySessionEqualWeightIncrementalMean": session_increment,
            "pooledTop1PctRemovedIncrementalMean": top1_increment,
            "top1PctRemovedRows": top1_removed,
            "yearIncrementalMeans": year_increments,
        },
        "validationChecks": checks,
        "replacementAllowed": False,
        "alternateOrientationAllowed": False,
        "alternateThresholdAllowed": False,
    }


def run(
    *,
    confirmation_path: Path,
    scope_csv: Path,
    scope_summary: Path,
    contract_path: Path,
    market_root: Path,
    output: Path,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    _load_confirmation(confirmation_path)
    scope_meta, scope_rows = _load_scope(scope_csv, scope_summary)
    contract_meta, contract_rows = _load_contract(contract_path)
    outcomes = _value(scope_rows, contract_rows, market_root, output)
    result = _evaluate(outcomes)

    fields = [
        "eventNumber",
        "issuerCik",
        "ticker",
        "evaluationSession",
        "entrySession",
        "horizon",
        "targetExitSession",
        "F2_DIRECT_VS_INDIRECT",
        "F2_OWNERSHIP_CATEGORY",
        "entryOpen",
        "raw_126",
        "excess_126",
        "reason_126",
        "continuity_126",
        "valuationKind_126",
        "terminalTicker_126",
        "legalSuccessorQuantity_126",
        "marketValuationQuantity_126",
        "cashPerEntryShare_126",
        "terminalHolderValue_126",
    ]
    with (output / "validation-event-outcomes.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in outcomes:
            writer.writerow({field: row.get(field) for field in fields})

    maturity = {
        "valued": sum(row["excess_126"] is not None for row in outcomes),
        "missing": sum(row["excess_126"] is None for row in outcomes),
        "reasonCounts": dict(
            sorted(
                Counter(
                    str(row.get("reason_126") or "VALUED")
                    for row in outcomes
                ).items()
            )
        ),
    }
    payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_INSIDER_FEATURE_TOURNAMENT_VALIDATION_COMPLETE",
        "definitionId": "PHASE1_INSIDER_FEATURE_TOURNAMENT_V1",
        "researchOnly": True,
        "validationPeriod": "2021-01-01 through 2022-12-31",
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "sourceValidationScopeRows": len(scope_rows),
        "sourceValidationScopeKeySha256": scope_meta["scopeKeySha256"],
        "continuityContractRows": contract_meta["classifiedRows"],
        "continuityUnresolvedRows": contract_meta["unresolvedRows"],
        "continuityKeySha256": contract_meta["classifiedKeySha256"],
        "maturity": maturity,
        "candidateResult": result,
        "validatedCandidateCount": int(bool(result["validated"])),
        "validatedCandidates": (
            [{
                "family": "F2",
                "variantId": "F2_DIRECT_VS_INDIRECT",
                "coverageClass": "GENERAL_ELIGIBLE",
                "frozenGroupDefinition": result["frozenGroupDefinition"],
            }]
            if result["validated"]
            else []
        ),
        "noReselection": True,
        "noAlternateOrientation": True,
        "noAlternateThreshold": True,
        "validationOpened": True,
        "validationEventOutcomesRead": True,
        "validationPerformanceOpened": True,
        "validationComplete": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "newVariantsAdded": False,
        "compositeWeightsFit": False,
        "nextGate": (
            "If validated, freeze the F2 validation result before any "
            "separately authorized 2023+ OOS work. If validation failed, "
            "the frozen tournament version stops without replacement."
        ),
    }
    (output / "validation-results.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", type=Path, required=True)
    parser.add_argument("--scope-csv", type=Path, required=True)
    parser.add_argument("--scope-summary", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        confirmation_path=args.confirmation,
        scope_csv=args.scope_csv,
        scope_summary=args.scope_summary,
        contract_path=args.contract,
        market_root=args.market_root,
        output=args.output,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "maturity": result["maturity"],
                "candidateResult": result["candidateResult"],
                "validatedCandidateCount": result["validatedCandidateCount"],
                "oosOpened": result["oosOpened"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
