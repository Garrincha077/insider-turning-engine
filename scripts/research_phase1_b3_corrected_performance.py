"""B3 continuity-corrected development performance under the frozen v1 gate."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import research_market_event_audit as market_audit
import research_market_event_audit_v2 as p0
import research_phase1_b0 as b0
import research_phase1_security_continuity_resolution as continuity

HORIZONS = (21, 63, 126, 252)
PRIMARY_HORIZON = 126
SEALED_YEAR = 2023
DEVELOPMENT_START = "2016-01-01"
DEVELOPMENT_END = "2020-12-31"
OUTCOME_END = "2022-12-31"
EXPECTED_EVENTS = 29930
EXPECTED_EVENT_HORIZON_ROWS = 119720
EXPECTED_CONTRACT_ROWS = 264
EXPECTED_CONTRACT_KEY_SHA256 = (
    "sha256:6125fe42a9559ce937d385b4f49d1a74d33ce1caad7f5ec8487ce72bf854082b"
)
SOURCE_STATUS = "PHASE1_B3_DEVELOPMENT_DESCRIPTIVE_COMPLETE"
OUTPUT_STATUS = "PHASE1_B3_CONTINUITY_CORRECTED_DEVELOPMENT_COMPLETE"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return payload


def _optional_float(value: object) -> float | None:
    text = str(value or "").strip()
    return float(text) if text else None


def _assert_pre2023(value: object, field: str) -> str:
    text = str(value or "").strip()
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        raise ValueError(f"invalid ISO date for {field}: {text!r}")
    if int(text[:4]) >= SEALED_YEAR:
        raise ValueError(f"sealed OOS boundary violated by {field}")
    return text


def _load_definition(path: Path) -> dict[str, Any]:
    p = _read_json(path)
    required = {
        "definitionId": "B3_CONTINUITY_CORRECTED_DEVELOPMENT_V1",
        "status": "PREDECLARED_BEFORE_CORRECTED_OUTCOMES",
        "researchOnly": True,
        "sourceDevelopmentEvents": EXPECTED_EVENTS,
        "sourceDevelopmentEventHorizonRows": EXPECTED_EVENT_HORIZON_ROWS,
        "continuityClassifiedRows": EXPECTED_CONTRACT_ROWS,
        "continuityUnresolvedRows": 0,
        "continuityKeySha256": EXPECTED_CONTRACT_KEY_SHA256,
        "marketAdjustment": "all",
        "marketSymbolMapping": "asof-dash-disabled",
        "developmentCohort": "2016-2020 XNYS evaluation-session cohort",
        "outcomeMarketBoundary": "2016-2022 only",
        "horizonsSessions": list(HORIZONS),
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "maeRecomputed": False,
        "correctedPerformanceOpened": False,
        "validationPerformanceComputed": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "b3DefinitionChanged": False,
        "eventConstructionChanged": False,
        "identityDefinitionChanged": False,
    }
    for key, expected in required.items():
        if p.get(key) != expected:
            raise ValueError(f"corrected-performance definition mismatch: {key}")
    exception = p.get("adjustedStockDividendException")
    if not isinstance(exception, dict):
        raise ValueError("missing adjusted stock-dividend exception")
    if exception.get("transformationKind") != "STOCK_DIVIDEND_QUANTITY":
        raise ValueError("stock-dividend exception kind changed")
    if exception.get("requiredSameTicker") is not True:
        raise ValueError("stock-dividend same-ticker guard changed")
    if float(exception.get("marketValuationQuantity", 0)) != 1.0:
        raise ValueError("stock-dividend market quantity changed")
    return p


def _load_source_summary(path: Path) -> dict[str, Any]:
    p = _read_json(path)
    required = {
        "status": SOURCE_STATUS,
        "benchmark": "B3_COMPANY_NET_BUYING_V1",
        "resultClass": "research/descriptive",
        "formalAlphaClaimed": False,
        "period": "2016-2020 XNYS evaluation-session cohort",
        "outcomeMarketBoundary": "2016-2022 only",
        "horizonsSessions": list(HORIZONS),
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "continuityCorrectionComplete": False,
        "validationPerformanceComputed": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "b3DefinitionChanged": False,
        "eventConstructionChanged": False,
        "identityDefinitionChanged": False,
    }
    for key, expected in required.items():
        if p.get(key) != expected:
            raise ValueError(f"canonical B3 summary mismatch: {key}")
    selection = p.get("selection")
    if not isinstance(selection, dict) or selection.get("exactEntryMatched") != EXPECTED_EVENTS:
        raise ValueError("canonical B3 exact-entry scope changed")
    return p


def _load_events(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        required = {
            "signalId",
            "issuerCik",
            "ticker",
            "evaluationSession",
            "entrySession",
            "entryOpen",
            *(f"exit_{h}" for h in HORIZONS),
            *(f"raw_{h}" for h in HORIZONS),
            *(f"excess_{h}" for h in HORIZONS),
            *(f"reason_{h}" for h in HORIZONS),
        }
        if not required.issubset(fields):
            raise ValueError("canonical B3 event file missing required fields")
        rows = []
        for raw in reader:
            row = {
                field: str(raw.get(field) or "").strip()
                for field in reader.fieldnames or []
            }
            evaluation = _assert_pre2023(row["evaluationSession"], "evaluationSession")
            if not DEVELOPMENT_START <= evaluation <= DEVELOPMENT_END:
                raise ValueError("canonical B3 event outside development cohort")
            _assert_pre2023(row["entrySession"], "entrySession")
            if float(row["entryOpen"]) <= 0:
                raise ValueError("canonical B3 entry open is non-positive")
            for horizon in HORIZONS:
                target = _assert_pre2023(
                    row[f"exit_{horizon}"],
                    f"exit_{horizon}",
                )
                if target > OUTCOME_END:
                    raise ValueError("canonical target exceeds outcome boundary")
            rows.append(row)
    if len(rows) != EXPECTED_EVENTS:
        raise ValueError("canonical B3 event count changed")
    return rows


def _load_contract(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    p = _read_json(path)
    required = {
        "status": "B3_FINAL_CONTINUITY_CONTRACT_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": EXPECTED_CONTRACT_ROWS,
        "classifiedRows": EXPECTED_CONTRACT_ROWS,
        "unresolvedRows": 0,
        "classifiedKeySha256": EXPECTED_CONTRACT_KEY_SHA256,
        "frozenScopeKeySha256": EXPECTED_CONTRACT_KEY_SHA256,
        "finalResolutionContractCreated": True,
        "correctedPerformanceOpened": False,
    }
    for key, expected in required.items():
        if p.get(key) != expected:
            raise ValueError(f"final continuity contract mismatch: {key}")
    rows = p.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_CONTRACT_ROWS:
        raise ValueError("final continuity resolution rows changed")
    if continuity._key_digest(rows) != EXPECTED_CONTRACT_KEY_SHA256:
        raise ValueError("final continuity resolution key digest changed")
    return p, rows


def _validate_contract_mapping(
    events: list[dict[str, str]],
    contract_rows: list[dict[str, Any]],
    sessions: list[str],
) -> dict[tuple[int, int], dict[str, Any]]:
    session_index = {day: idx for idx, day in enumerate(sessions)}
    by_key: dict[tuple[int, int], dict[str, Any]] = {}

    for event in events:
        entry = event["entrySession"]
        if entry not in session_index:
            raise ValueError("canonical B3 entry is absent from XNYS calendar")
        entry_idx = session_index[entry]
        for horizon in HORIZONS:
            target_idx = entry_idx + horizon
            if target_idx >= len(sessions):
                raise ValueError("canonical target lies outside frozen XNYS calendar")
            if sessions[target_idx] != event[f"exit_{horizon}"]:
                raise ValueError("canonical B3 target differs from XNYS calendar")

    for row in contract_rows:
        event_number = int(row["eventNumber"])
        horizon = int(row["horizon"])
        if not 1 <= event_number <= len(events) or horizon not in HORIZONS:
            raise ValueError("continuity contract event/horizon outside source scope")
        key = (event_number, horizon)
        if key in by_key:
            raise ValueError("duplicate continuity contract event/horizon")
        event = events[event_number - 1]
        expected_identity = (
            event["issuerCik"],
            event["ticker"].upper(),
            event["evaluationSession"],
            event["entrySession"],
            event[f"exit_{horizon}"],
        )
        actual_identity = (
            str(row["issuerCik"]),
            str(row["ticker"]).upper(),
            str(row["evaluationSession"]),
            str(row["entrySession"]),
            str(row["targetExitSession"]),
        )
        if actual_identity != expected_identity:
            raise ValueError("continuity contract no longer maps to canonical event order")
        by_key[key] = row

    if len(by_key) != EXPECTED_CONTRACT_ROWS:
        raise ValueError("continuity contract mapping count changed")
    return by_key


def _terms(
    event: dict[str, str],
    contract_row: dict[str, Any] | None,
) -> dict[str, Any]:
    ticker = event["ticker"].upper()
    if contract_row is None:
        return {
            "decision": "NO_CONTINUITY_CORRECTION_REQUIRED",
            "kind": "ORDINARY_ADJUSTED_PRICE",
            "terminalTicker": ticker,
            "marketQuantity": 1.0,
            "legalQuantity": 1.0,
            "cash": 0.0,
            "basket": [],
        }

    decision = str(contract_row["resolutionDecision"])
    kind = str(contract_row.get("transformationKind") or "")
    successor = str(contract_row.get("successorSymbol") or "").upper()
    legal_quantity = float(contract_row.get("successorSharesPerEntryShare") or 0.0)
    cash = float(contract_row.get("cashPerEntryShare") or 0.0)

    if decision == "SAME_SECURITY_CONTINUITY":
        return {
            "decision": decision,
            "kind": str(contract_row["resultState"]),
            "terminalTicker": ticker,
            "marketQuantity": 1.0,
            "legalQuantity": legal_quantity,
            "cash": 0.0,
            "basket": [],
        }

    if decision == "SYMBOL_CHANGED_SAME_SECURITY":
        if not successor or legal_quantity != 1.0 or cash != 0.0:
            raise ValueError("invalid same-security symbol-change terms")
        return {
            "decision": decision,
            "kind": kind,
            "terminalTicker": successor,
            "marketQuantity": 1.0,
            "legalQuantity": legal_quantity,
            "cash": 0.0,
            "basket": [],
        }

    if decision == "TRANSFORMED_HOLDER_CONSIDERATION":
        if kind == "STOCK_DIVIDEND_QUANTITY":
            if successor != ticker or cash != 0.0 or legal_quantity <= 0:
                raise ValueError("adjusted stock-dividend exception scope changed")
            return {
                "decision": decision,
                "kind": kind,
                "terminalTicker": ticker,
                "marketQuantity": 1.0,
                "legalQuantity": legal_quantity,
                "cash": 0.0,
                "basket": [],
            }
        if legal_quantity < 0 or cash < 0:
            raise ValueError("negative transformed-holder terms")
        if legal_quantity > 0 and not successor:
            raise ValueError("stock consideration lacks successor ticker")
        if legal_quantity == 0 and cash == 0:
            raise ValueError("holder transformation has no deterministic value")
        return {
            "decision": decision,
            "kind": kind,
            "terminalTicker": successor,
            "marketQuantity": legal_quantity,
            "legalQuantity": legal_quantity,
            "cash": cash,
            "basket": [],
        }

    if decision == "TRANSFORMED_MULTI_COMPONENT_CONSIDERATION":
        basket = contract_row.get("basket")
        if not isinstance(basket, list) or not basket:
            raise ValueError("multi-component consideration lacks basket")
        normalized = []
        for item in basket:
            symbol = str(item.get("symbol") or "").upper()
            quantity = float(item.get("quantityPerEntryUnit") or 0.0)
            if not symbol or quantity <= 0:
                raise ValueError("invalid multi-component basket leg")
            normalized.append(
                {
                    "symbol": symbol,
                    "quantity": quantity,
                    "securityClass": str(item.get("securityClass") or ""),
                }
            )
        return {
            "decision": decision,
            "kind": kind,
            "terminalTicker": "",
            "marketQuantity": 0.0,
            "legalQuantity": 0.0,
            "cash": cash,
            "basket": normalized,
        }

    if decision == "DISCONTINUOUS_NO_COMPLETE_VALUATION":
        return {
            "decision": decision,
            "kind": kind,
            "terminalTicker": "",
            "marketQuantity": 0.0,
            "legalQuantity": 0.0,
            "cash": 0.0,
            "basket": [],
        }

    raise ValueError(f"unsupported continuity decision: {decision}")


def _load_market_maps(
    market_root: Path,
    output: Path,
    tickers: set[str],
) -> tuple[dict[str, dict[str, tuple[Any, ...]]], Path]:
    if (market_root / "2023").exists():
        raise ValueError("sealed 2023 market directory must not be present")
    market_files = market_audit._market_files(market_root)
    if not market_files:
        raise ValueError("no frozen market files found")
    for path in market_files:
        relative = path.relative_to(market_root)
        if relative.parts and relative.parts[0].isdigit():
            if int(relative.parts[0]) >= SEALED_YEAR:
                raise ValueError("sealed OOS market file discovered")

    db_path = output / "phase1-b3-corrected.sqlite"
    db_path.unlink(missing_ok=True)
    market_audit._build_market_db(market_files, db_path)
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


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _aggregate(rows: list[dict[str, Any]], horizon: int) -> dict[str, Any]:
    matured = [
        row
        for row in rows
        if row[f"excess_{horizon}"] is not None
    ]
    raw = [float(row[f"raw_{horizon}"]) for row in matured]
    excess = [float(row[f"excess_{horizon}"]) for row in matured]
    return {
        "horizonSessions": horizon,
        "maturedOutcomeCount": len(matured),
        "distinctIssuers": len({str(row["issuerCik"]) for row in matured}),
        "rawReturnMean": statistics.fmean(raw) if raw else None,
        "rawReturnMedian": statistics.median(raw) if raw else None,
        "spyExcessMean": statistics.fmean(excess) if excess else None,
        "spyExcessMedian": statistics.median(excess) if excess else None,
        "spyExcessWinRate": (
            sum(value > 0 for value in excess) / len(excess)
            if excess
            else None
        ),
        "spyExcessP05": _percentile(excess, 0.05),
        "spyExcessP10": _percentile(excess, 0.10),
        "maeRecomputed": False,
    }


def _delta(left: object, right: object) -> float | None:
    if left is None or right is None:
        return None
    return float(left) - float(right)


def run(
    *,
    events_path: Path,
    source_summary_path: Path,
    contract_path: Path,
    definition_path: Path,
    market_root: Path,
    output: Path,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    definition = _load_definition(definition_path)
    source_summary = _load_source_summary(source_summary_path)
    events = _load_events(events_path)
    contract_summary, contract_rows = _load_contract(contract_path)

    sessions = p0._expected_sessions()
    contract_by_key = _validate_contract_mapping(events, contract_rows, sessions)

    needed_tickers = {event["ticker"].upper() for event in events}
    terms_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for key, row in contract_by_key.items():
        event = events[key[0] - 1]
        terms = _terms(event, row)
        terms_by_key[key] = terms
        if terms["terminalTicker"]:
            needed_tickers.add(str(terms["terminalTicker"]))
        for leg in terms["basket"]:
            needed_tickers.add(str(leg["symbol"]))

    maps, db_path = _load_market_maps(market_root, output, needed_tickers)
    detailed_rows: list[dict[str, Any]] = []
    corrected_events: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    decision_counts: Counter[str] = Counter()
    changed_rows = 0
    canonical_reproduction_rows = 0
    canonical_missing_reproduced = 0
    adjusted_stock_dividend_rows = 0

    try:
        for event_number, event in enumerate(events, start=1):
            entry_open = float(event["entryOpen"])
            entry_session = event["entrySession"]
            original_ticker = event["ticker"].upper()
            original_entry = maps.get(original_ticker, {}).get(entry_session)
            if not b0._regular(original_entry):
                raise ValueError("canonical exact entry bar disappeared from frozen market")
            market_entry_open = float(original_entry[1])
            if not math.isclose(
                market_entry_open,
                entry_open,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("canonical entry open differs from frozen market")

            spy_entry = maps["SPY"].get(entry_session)
            if not b0._regular(spy_entry):
                raise ValueError("canonical exact SPY entry bar disappeared")
            spy_entry_open = float(spy_entry[1])

            corrected: dict[str, Any] = {
                key: event[key]
                for key in (
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
                )
            }

            for horizon in HORIZONS:
                contract_row = contract_by_key.get((event_number, horizon))
                terms = (
                    terms_by_key[(event_number, horizon)]
                    if contract_row is not None
                    else _terms(event, None)
                )
                decision_counts[terms["decision"]] += 1
                if terms["kind"] == "STOCK_DIVIDEND_QUANTITY":
                    adjusted_stock_dividend_rows += 1

                target = event[f"exit_{horizon}"]
                original_raw = _optional_float(event[f"raw_{horizon}"])
                original_excess = _optional_float(event[f"excess_{horizon}"])
                terminal_value: float | None = None
                corrected_raw: float | None = None
                corrected_excess: float | None = None
                spy_return: float | None = None
                reason = ""
                status = ""

                if terms["decision"] == "DISCONTINUOUS_NO_COMPLETE_VALUATION":
                    status = "DISCONTINUOUS_NO_COMPLETE_VALUATION"
                    reason = "complete holder consideration is not deterministically valued"
                else:
                    spy_exit = maps["SPY"].get(target)
                    if not b0._regular(spy_exit):
                        status = "MISSING_EXACT_SPY_EXIT_BAR"
                        reason = "exact frozen SPY target bar missing"
                    else:
                        spy_return = float(spy_exit[4]) / spy_entry_open - 1.0
                        basket = terms["basket"]
                        if basket:
                            basket_value = 0.0
                            for leg in basket:
                                component = maps.get(leg["symbol"], {}).get(target)
                                if not b0._regular(component):
                                    status = "MISSING_EXACT_BASKET_COMPONENT_BAR"
                                    reason = (
                                        "missing exact target bar for basket component "
                                        f"{leg['symbol']}"
                                    )
                                    break
                                basket_value += float(leg["quantity"]) * float(
                                    component[4]
                                )
                            if not status:
                                terminal_value = float(terms["cash"]) + basket_value
                        else:
                            stock_value = 0.0
                            quantity = float(terms["marketQuantity"])
                            terminal_ticker = str(terms["terminalTicker"])
                            if quantity:
                                terminal = maps.get(terminal_ticker, {}).get(target)
                                if not b0._regular(terminal):
                                    status = "MISSING_EXACT_TERMINAL_HOLDER_BAR"
                                    reason = (
                                        "missing exact target bar for "
                                        f"{terminal_ticker}"
                                    )
                                else:
                                    stock_value = quantity * float(terminal[4])
                            if not status:
                                terminal_value = float(terms["cash"]) + stock_value

                        if not status:
                            if terminal_value is None or terminal_value < 0:
                                raise ValueError("invalid terminal holder value")
                            corrected_raw = terminal_value / entry_open - 1.0
                            corrected_excess = corrected_raw - spy_return
                            status = "VALUED"

                must_reproduce = (
                    contract_row is None
                    or terms["decision"] == "SAME_SECURITY_CONTINUITY"
                    or terms["kind"] == "STOCK_DIVIDEND_QUANTITY"
                )
                if must_reproduce:
                    if original_raw is None or original_excess is None:
                        if corrected_raw is not None or corrected_excess is not None:
                            raise ValueError(
                                "canonical missing ordinary outcome unexpectedly became valued"
                            )
                        canonical_missing_reproduced += 1
                    else:
                        if corrected_raw is None or corrected_excess is None:
                            raise ValueError(
                                "canonical valued ordinary outcome became missing"
                            )
                        if not math.isclose(
                            corrected_raw,
                            original_raw,
                            rel_tol=0.0,
                            abs_tol=1e-12,
                        ):
                            raise ValueError("ordinary raw return reproduction failed")
                        if not math.isclose(
                            corrected_excess,
                            original_excess,
                            rel_tol=0.0,
                            abs_tol=1e-12,
                        ):
                            raise ValueError("ordinary excess return reproduction failed")
                        canonical_reproduction_rows += 1
                else:
                    if (
                        corrected_raw is not None
                        and (
                            original_raw is None
                            or not math.isclose(
                                corrected_raw,
                                original_raw,
                                rel_tol=0.0,
                                abs_tol=1e-12,
                            )
                        )
                    ):
                        changed_rows += 1

                status_counts[status] += 1
                corrected[f"exit_{horizon}"] = target
                corrected[f"raw_{horizon}"] = corrected_raw
                corrected[f"excess_{horizon}"] = corrected_excess
                corrected[f"mae_{horizon}"] = None
                corrected[f"reason_{horizon}"] = reason or None
                corrected[f"continuity_{horizon}"] = terms["decision"]
                corrected[f"valuationKind_{horizon}"] = terms["kind"]

                detailed_rows.append(
                    {
                        "eventNumber": event_number,
                        "signalId": event["signalId"],
                        "issuerCik": event["issuerCik"],
                        "ticker": original_ticker,
                        "evaluationSession": event["evaluationSession"],
                        "entrySession": entry_session,
                        "entryOpen": entry_open,
                        "horizon": horizon,
                        "targetExitSession": target,
                        "contractApplied": contract_row is not None,
                        "resolutionDecision": terms["decision"],
                        "transformationKind": terms["kind"],
                        "terminalTicker": terms["terminalTicker"],
                        "legalSuccessorQuantity": terms["legalQuantity"],
                        "marketValuationQuantity": terms["marketQuantity"],
                        "cashPerEntryShare": terms["cash"],
                        "basket": json.dumps(
                            terms["basket"],
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        "terminalHolderValue": terminal_value,
                        "originalRaw": original_raw,
                        "correctedRaw": corrected_raw,
                        "originalExcess": original_excess,
                        "correctedExcess": corrected_excess,
                        "spyReturn": spy_return,
                        "valuationStatus": status,
                        "missingReason": reason,
                    }
                )
            corrected_events.append(corrected)
    finally:
        db_path.unlink(missing_ok=True)

    if len(detailed_rows) != EXPECTED_EVENT_HORIZON_ROWS:
        raise ValueError("corrected event-horizon row count changed")
    if adjusted_stock_dividend_rows != 50:
        raise ValueError("adjusted stock-dividend exception count changed")

    detailed_path = output / "b3-corrected-event-horizons.csv"
    with detailed_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(detailed_rows[0]))
        writer.writeheader()
        writer.writerows(detailed_rows)

    event_path = output / "b3-continuity-corrected-events.csv"
    event_fields = [
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
        event_fields.extend(
            [
                f"exit_{horizon}",
                f"raw_{horizon}",
                f"excess_{horizon}",
                f"mae_{horizon}",
                f"reason_{horizon}",
                f"continuity_{horizon}",
                f"valuationKind_{horizon}",
            ]
        )
    with event_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=event_fields)
        writer.writeheader()
        writer.writerows(corrected_events)

    corrected_horizons = {
        str(horizon): _aggregate(corrected_events, horizon)
        for horizon in HORIZONS
    }
    side_by_side: dict[str, Any] = {}
    for horizon in HORIZONS:
        key = str(horizon)
        original = source_summary["horizons"][key]
        corrected = corrected_horizons[key]
        side_by_side[key] = {
            "canonical": original,
            "continuityCorrected": corrected,
            "correctedMinusCanonical": {
                "maturedOutcomeCountDelta": (
                    corrected["maturedOutcomeCount"]
                    - original["maturedOutcomeCount"]
                ),
                "rawReturnMeanDelta": _delta(
                    corrected["rawReturnMean"],
                    original["rawReturnMean"],
                ),
                "rawReturnMedianDelta": _delta(
                    corrected["rawReturnMedian"],
                    original["rawReturnMedian"],
                ),
                "spyExcessMeanDelta": _delta(
                    corrected["spyExcessMean"],
                    original["spyExcessMean"],
                ),
                "spyExcessMedianDelta": _delta(
                    corrected["spyExcessMedian"],
                    original["spyExcessMedian"],
                ),
                "spyExcessWinRateDelta": _delta(
                    corrected["spyExcessWinRate"],
                    original["spyExcessWinRate"],
                ),
            },
        }

    reason_counts: dict[str, dict[str, int]] = {}
    for horizon in HORIZONS:
        counts: dict[str, int] = defaultdict(int)
        for row in corrected_events:
            reason = row[f"reason_{horizon}"]
            if reason:
                counts[str(reason)] += 1
        reason_counts[str(horizon)] = dict(sorted(counts.items()))

    summary: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": OUTPUT_STATUS,
        "benchmark": "B3_COMPANY_NET_BUYING_V1",
        "resultClass": "research/descriptive",
        "formalAlphaClaimed": False,
        "period": "2016-2020 XNYS evaluation-session cohort",
        "outcomeMarketBoundary": "2016-2022 only",
        "coverageTier": source_summary["coverageTier"],
        "horizonsSessions": list(HORIZONS),
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "selection": source_summary["selection"],
        "continuityContract": {
            "classifiedRows": contract_summary["classifiedRows"],
            "unresolvedRows": contract_summary["unresolvedRows"],
            "classifiedKeySha256": contract_summary["classifiedKeySha256"],
        },
        "scope": {
            "events": len(corrected_events),
            "eventHorizonRows": len(detailed_rows),
            "contractAppliedRows": EXPECTED_CONTRACT_ROWS,
            "resolutionDecisionCounts": dict(sorted(decision_counts.items())),
            "valuationStatusCounts": dict(sorted(status_counts.items())),
            "rowsWhereCorrectedRawDiffersOrCanonicalWasMissing": changed_rows,
            "canonicalReproductionRows": canonical_reproduction_rows,
            "canonicalMissingReproduced": canonical_missing_reproduced,
            "adjustedStockDividendRowsNormalizedToMarketQuantityOne": (
                adjusted_stock_dividend_rows
            ),
        },
        "horizons": corrected_horizons,
        "sideBySide": side_by_side,
        "primary126": side_by_side[str(PRIMARY_HORIZON)],
        "horizonAttritionReasons": reason_counts,
        "maeRecomputed": False,
        "continuityCorrectionComplete": True,
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
        "definitionId": definition["definitionId"],
        "interpretationGuardrail": (
            "Continuity-corrected B3 development outcomes are descriptive "
            "research evidence only. The frozen robustness semantics must be "
            "reapplied unchanged before any progression decision. Validation "
            "and 2023+ OOS remain sealed."
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--source-summary", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        events_path=args.events,
        source_summary_path=args.source_summary,
        contract_path=args.contract,
        definition_path=args.definition,
        market_root=args.market_root,
        output=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
