"""Run the frozen 2016-2018 insider-feature discovery tournament."""

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

import research_phase1_b0 as b0
import research_phase1_feature_tournament_stage_a as stage_a

HORIZONS = (21, 63, 126, 252)
PRIMARY_HORIZON = 126
DISCOVERY_END = "2018-12-31"
EXPECTED_STAGE_A_EVENTS = 24190
EXPECTED_LEDGER_ROWS = EXPECTED_STAGE_A_EVENTS * len(HORIZONS)
EXPECTED_FINAL_ROWS = 210

VARIANTS: dict[str, dict[str, str]] = {
    "F1_ABS_DOLLARS": {
        "family": "F1",
        "source": "F1_ABS_DOLLARS",
        "coverage": "F1_ABS_DOLLARS",
        "kind": "Q5",
    },
    "F1_FRACTION_POST": {
        "family": "F1",
        "source": "F1_FRACTION_POST",
        "coverage": "F1_FRACTION_POST",
        "kind": "Q5",
    },
    "F1_FRACTION_PRE": {
        "family": "F1",
        "source": "F1_FRACTION_PRE",
        "coverage": "F1_FRACTION_PRE",
        "kind": "Q5",
    },
    "F1_OWNER_HISTORY_PERCENTILE": {
        "family": "F1",
        "source": "F1_OWNER_HISTORY_PERCENTILE",
        "coverage": "F1_OWNER_HISTORY_PERCENTILE",
        "kind": "Q5",
    },
    "F1_ABS_PLUS_FRACTION_POST": {
        "family": "F1",
        "source": "F1_ABS_PLUS_FRACTION_POST",
        "coverage": "F1_ABS_PLUS_FRACTION_POST",
        "kind": "TRUE",
    },
    "F2_DIRECT_VS_INDIRECT": {
        "family": "F2",
        "source": "F2_DIRECT_VS_INDIRECT",
        "coverage": "F2_DIRECT_VS_INDIRECT",
        "kind": "F2_DYNAMIC",
    },
    "F3_RETURN_21": {
        "family": "F3",
        "source": "F3_RETURN_21",
        "coverage": "F3_RETURN_21",
        "kind": "Q1",
    },
    "F3_RETURN_63": {
        "family": "F3",
        "source": "F3_RETURN_63",
        "coverage": "F3_RETURN_63",
        "kind": "Q1",
    },
    "F3_RETURN_126": {
        "family": "F3",
        "source": "F3_RETURN_126",
        "coverage": "F3_RETURN_126",
        "kind": "Q1",
    },
    "F3_RETURN_252": {
        "family": "F3",
        "source": "F3_RETURN_252",
        "coverage": "F3_RETURN_252",
        "kind": "Q1",
    },
    "F3_DRAWDOWN_252": {
        "family": "F3",
        "source": "F3_DRAWDOWN_252",
        "coverage": "F3_DRAWDOWN_252",
        "kind": "Q5",
    },
    "F3_NEW_52W_LOW": {
        "family": "F3",
        "source": "F3_NEW_52W_LOW",
        "coverage": "F3_NEW_52W_LOW",
        "kind": "TRUE",
    },
    "F4_ABOVE_BASIS": {
        "family": "F4",
        "source": "F4_ABOVE_BASIS",
        "coverage": "F4_ABOVE_BASIS",
        "kind": "TRUE",
    },
    "F4_DISTANCE_ABOVE": {
        "family": "F4",
        "source": "F4_DISTANCE_TO_BASIS",
        "coverage": "F4_DISTANCE_TO_BASIS",
        "kind": "Q5",
    },
    "F4_DISTANCE_BELOW": {
        "family": "F4",
        "source": "F4_DISTANCE_TO_BASIS",
        "coverage": "F4_DISTANCE_TO_BASIS",
        "kind": "Q1",
    },
    "F4_TRUE_RECLAIM": {
        "family": "F4",
        "source": "F4_TRUE_RECLAIM",
        "coverage": "F4_TRUE_RECLAIM",
        "kind": "TRUE",
    },
    "F4_RECLAIM_PERSIST_2": {
        "family": "F4",
        "source": "F4_RECLAIM_PERSIST_2",
        "coverage": "F4_RECLAIM_PERSIST_2",
        "kind": "TRUE",
    },
    "F4_RECLAIM_PERSIST_5": {
        "family": "F4",
        "source": "F4_RECLAIM_PERSIST_5",
        "coverage": "F4_RECLAIM_PERSIST_5",
        "kind": "TRUE",
    },
}

CONTEXT_FEATURES = ("DOLLAR_ADV_20", "DOLLAR_ADV_60", "STOCK_PRICE")
ELIGIBLE_COVERAGE = {"GENERAL_ELIGIBLE", "SPECIALTY_ELIGIBLE"}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return value


def _optional_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    return None


def _base_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row["issuerCik"]),
        str(row["ticker"]).upper(),
        str(row["evaluationSession"]),
        str(row["entrySession"]),
    )


def _horizon_key(row: dict[str, Any]) -> tuple[str, str, str, str, int, str]:
    return (
        *_base_key(row),
        int(row["horizon"]),
        str(row["targetExitSession"]),
    )


def _load_stage_a(
    stage_a_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    summary = _read_json(stage_a_dir / "summary.json")
    cutpoints = _read_json(stage_a_dir / "stage-a-cutpoints.json")
    required = {
        "status": "PHASE1_INSIDER_FEATURE_TOURNAMENT_STAGE_A_FROZEN",
        "definitionId": "PHASE1_INSIDER_FEATURE_TOURNAMENT_V1",
        "forwardReturnsRead": False,
        "outcomeFieldsRead": [],
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for key, expected in required.items():
        if summary.get(key) != expected:
            raise ValueError(f"Stage A summary mismatch: {key}")
    if summary.get("scope", {}).get("events") != EXPECTED_STAGE_A_EVENTS:
        raise ValueError("Stage A event count changed")

    path = stage_a_dir / "stage-a-feature-matrix.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        lowered = " ".join(fields).lower()
        forbidden = ("raw_21", "raw_63", "raw_126", "raw_252", "excess_", "mae_")
        if any(token in lowered for token in forbidden):
            raise ValueError("Stage A matrix contains outcome fields")
        rows = [dict(row) for row in reader]
    if len(rows) != EXPECTED_STAGE_A_EVENTS:
        raise ValueError("Stage A matrix row count changed")
    return summary, cutpoints, rows


def _load_ledger(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {
            "eventNumber",
            "issuerCik",
            "ticker",
            "evaluationSession",
            "entrySession",
            "horizon",
            "targetExitSession",
            "state",
            "successorSymbol",
            "resolutionSource",
            "candidateActionIds",
        }
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Stage-B ledger missing required columns")
        rows = [dict(row) for row in reader]
    if len(rows) != EXPECTED_LEDGER_ROWS:
        raise ValueError("Stage-B ledger row count changed")
    counts = Counter(row["state"] for row in rows)
    expected = {
        "PRICE_CONTINUOUS_ADJUSTED": 96147,
        "SYMBOL_CHANGED_SAME_SECURITY": 251,
        "TRANSFORMED_HOLDER_CONSIDERATION": 152,
        "UNRESOLVED_CONTINUITY": 210,
    }
    if dict(counts) != expected:
        raise ValueError("Stage-B initial continuity partition changed")
    return rows


def _load_final_contract(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    required = {
        "status": "PHASE1_FEATURE_TOURNAMENT_STAGE_B_FINAL_CONTINUITY_COMPLETE",
        "sourceUnresolvedRows": EXPECTED_FINAL_ROWS,
        "classifiedRows": EXPECTED_FINAL_ROWS,
        "unresolvedRows": 0,
        "resolutionComplete": True,
        "finalResolutionContractCreated": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"final continuity contract mismatch: {key}")
    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_FINAL_ROWS:
        raise ValueError("final continuity row count changed")
    return rows


def _load_actions(path: Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(path)
    if payload.get("performanceRead") is not False:
        raise ValueError("corporate-action source is not performance-blind")
    if payload.get("oosOpened") is not False:
        raise ValueError("corporate-action source opened OOS")
    rows = payload.get("actions")
    if not isinstance(rows, list):
        raise ValueError("corporate-action source missing actions")
    return {str(row["id"]): row for row in rows}


def _action_ids(row: dict[str, Any]) -> list[str]:
    return [
        item
        for item in str(row.get("candidateActionIds") or "").split(";")
        if item
    ]


def _provider_terms(
    row: dict[str, Any],
    actions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    ids = _action_ids(row)
    if len(ids) != 1 or ids[0] not in actions:
        raise ValueError("provider transformation lacks one frozen action")
    action = actions[ids[0]]
    bucket = str(action.get("bucket") or "")
    effective = str(action.get("actionDate") or "")
    if not str(row["entrySession"]) < effective <= str(row["targetExitSession"]):
        raise ValueError("provider action effective date outside horizon")

    if bucket == "cash_mergers":
        return {
            "decision": "TRANSFORMED_HOLDER_CONSIDERATION",
            "kind": "CASH_MERGER",
            "terminalTicker": "",
            "marketQuantity": 0.0,
            "legalQuantity": 0.0,
            "cash": float(action["rate"]),
            "basket": [],
        }
    if bucket in {"stock_mergers", "stock_and_cash_mergers"}:
        acquiree_rate = float(action["acquiree_rate"])
        acquirer_rate = float(action["acquirer_rate"])
        if acquiree_rate <= 0 or acquirer_rate <= 0:
            raise ValueError("invalid provider stock-merger rates")
        quantity = acquirer_rate / acquiree_rate
        cash = 0.0
        if bucket == "stock_and_cash_mergers":
            cash = float(action["cash_rate"]) / acquiree_rate
        successor = str(action.get("acquirer_symbol") or "").upper()
        if not successor:
            raise ValueError("provider stock merger lacks successor")
        return {
            "decision": "TRANSFORMED_HOLDER_CONSIDERATION",
            "kind": bucket.upper(),
            "terminalTicker": successor,
            "marketQuantity": quantity,
            "legalQuantity": quantity,
            "cash": cash,
            "basket": [],
        }
    if bucket == "redemptions":
        return {
            "decision": "TRANSFORMED_HOLDER_CONSIDERATION",
            "kind": "REDEMPTION",
            "terminalTicker": "",
            "marketQuantity": 0.0,
            "legalQuantity": 0.0,
            "cash": float(action["rate"]),
            "basket": [],
        }
    raise ValueError(f"unsupported provider transformation: {bucket}")


def _final_terms(row: dict[str, Any]) -> dict[str, Any]:
    ticker = str(row["ticker"]).upper()
    decision = str(row["resolutionDecision"])
    kind = str(row.get("transformationKind") or "")
    successor = str(row.get("successorSymbol") or "").upper()
    legal_quantity = float(row.get("successorSharesPerEntryShare") or 0.0)
    cash = float(row.get("cashPerEntryShare") or 0.0)

    if decision == "SAME_SECURITY_CONTINUITY":
        return {
            "decision": decision,
            "kind": str(row["resultState"]),
            "terminalTicker": ticker,
            "marketQuantity": 1.0,
            "legalQuantity": legal_quantity,
            "cash": 0.0,
            "basket": [],
        }
    if decision == "SYMBOL_CHANGED_SAME_SECURITY":
        if not successor or legal_quantity != 1.0 or cash != 0.0:
            raise ValueError("invalid final symbol-change terms")
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
        if kind == "STOCK_DIVIDEND_QUANTITY":
            if successor != ticker or legal_quantity <= 0 or cash != 0.0:
                raise ValueError("invalid adjusted stock-dividend terms")
            market_quantity = 1.0
        else:
            market_quantity = legal_quantity
            if legal_quantity > 0 and not successor:
                raise ValueError("stock consideration lacks successor")
            if legal_quantity == 0 and cash == 0:
                raise ValueError("holder transformation lacks value")
        return {
            "decision": decision,
            "kind": kind,
            "terminalTicker": successor,
            "marketQuantity": market_quantity,
            "legalQuantity": legal_quantity,
            "cash": cash,
            "basket": [],
        }
    if decision == "TRANSFORMED_MULTI_COMPONENT_CONSIDERATION":
        basket = row.get("basket")
        if not isinstance(basket, list) or not basket:
            raise ValueError("multi-component resolution lacks basket")
        normalized = []
        for item in basket:
            symbol = str(item.get("symbol") or "").upper()
            quantity = float(item.get("quantityPerEntryUnit") or 0.0)
            if not symbol or quantity <= 0:
                raise ValueError("invalid basket component")
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
    raise ValueError(f"unsupported final continuity decision: {decision}")


def _terms_for(
    ledger_row: dict[str, Any],
    final_row: dict[str, Any] | None,
    actions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    state = str(ledger_row["state"])
    ticker = str(ledger_row["ticker"]).upper()
    if state == "UNRESOLVED_CONTINUITY":
        if final_row is None:
            raise ValueError("unresolved ledger row lacks final resolution")
        return _final_terms(final_row)
    if final_row is not None:
        raise ValueError("final resolution overlaps already classified ledger row")
    if state == "PRICE_CONTINUOUS_ADJUSTED":
        return {
            "decision": "NO_CONTINUITY_CORRECTION_REQUIRED",
            "kind": state,
            "terminalTicker": ticker,
            "marketQuantity": 1.0,
            "legalQuantity": 1.0,
            "cash": 0.0,
            "basket": [],
        }
    if state == "SYMBOL_CHANGED_SAME_SECURITY":
        successor = str(ledger_row.get("successorSymbol") or "").upper()
        if not successor:
            raise ValueError("symbol-change ledger row lacks successor")
        return {
            "decision": "SYMBOL_CHANGED_SAME_SECURITY",
            "kind": "SAME_SECURITY_SYMBOL_CHANGE",
            "terminalTicker": successor,
            "marketQuantity": 1.0,
            "legalQuantity": 1.0,
            "cash": 0.0,
            "basket": [],
        }
    if state == "TRANSFORMED_HOLDER_CONSIDERATION":
        return _provider_terms(ledger_row, actions)
    raise ValueError(f"unsupported initial continuity state: {state}")


def _market_maps(
    market_root: Path,
    output: Path,
    tickers: set[str],
) -> tuple[dict[str, dict[str, tuple[Any, ...]]], Path]:
    if (market_root / "2021").exists() or (market_root / "2022").exists():
        raise ValueError("confirmation/validation market years must not be mounted")
    if (market_root / "2023").exists():
        raise ValueError("sealed OOS market directory mounted")
    paths = stage_a._market_paths(
        market_root,
        "canonical-market",
        range(2016, 2021),
    )
    db_path = output / "feature-discovery.sqlite"
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


def _value_outcomes(
    matrix: list[dict[str, str]],
    ledger: list[dict[str, str]],
    final_rows: list[dict[str, Any]],
    actions: dict[str, dict[str, Any]],
    market_root: Path,
    output: Path,
) -> list[dict[str, Any]]:
    discovery = [
        dict(row)
        for row in matrix
        if str(row["evaluationSession"]) <= DISCOVERY_END
    ]
    if not discovery:
        raise ValueError("discovery scope is empty")
    if any(str(row["evaluationSession"]) > DISCOVERY_END for row in discovery):
        raise ValueError("confirmation event entered discovery")

    ledger_by_key = {_horizon_key(row): row for row in ledger}
    if len(ledger_by_key) != len(ledger):
        raise ValueError("duplicate Stage-B ledger key")
    ledger_by_base: dict[
        tuple[str, str, str, str],
        list[dict[str, str]],
    ] = defaultdict(list)
    for ledger_row in ledger:
        ledger_by_base[_base_key(ledger_row)].append(ledger_row)
    final_by_key = {_horizon_key(row): row for row in final_rows}
    if len(final_by_key) != len(final_rows):
        raise ValueError("duplicate final continuity key")

    unresolved_keys = {
        _horizon_key(row)
        for row in ledger
        if row["state"] == "UNRESOLVED_CONTINUITY"
    }
    if set(final_by_key) != unresolved_keys:
        raise ValueError("final continuity key-set differs from initial unresolved set")

    terms_by_key: dict[
        tuple[str, str, str, str, int, str],
        dict[str, Any],
    ] = {}
    needed_tickers = {str(row["ticker"]).upper() for row in discovery}
    for row in discovery:
        base = _base_key(row)
        matches = ledger_by_base.get(base, [])
        if len(matches) != len(HORIZONS):
            raise ValueError("Stage A discovery event does not map to four ledger rows")
        for ledger_row in matches:
            key = _horizon_key(ledger_row)
            terms = _terms_for(
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

    maps, db_path = _market_maps(market_root, output, needed_tickers)
    result: list[dict[str, Any]] = []
    try:
        for row in discovery:
            original = str(row["ticker"]).upper()
            entry_session = str(row["entrySession"])
            entry = maps.get(original, {}).get(entry_session)
            spy_entry = maps["SPY"].get(entry_session)
            if not b0._regular(entry) or not b0._regular(spy_entry):
                raise ValueError("frozen Stage A discovery entry bar disappeared")
            entry_open = float(entry[1])
            spy_entry_open = float(spy_entry[1])

            event = dict(row)
            event["entryOpen"] = entry_open
            event_number: int | None = None
            for horizon in HORIZONS:
                candidates = [
                    item
                    for item in ledger_by_base.get(_base_key(row), [])
                    if int(item["horizon"]) == horizon
                ]
                if len(candidates) != 1:
                    raise ValueError("discovery event/horizon ledger mapping changed")
                ledger_row = candidates[0]
                event_number = int(ledger_row["eventNumber"])
                key = _horizon_key(ledger_row)
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
                                terminal = maps.get(str(leg["symbol"]), {}).get(target)
                                if not b0._regular(terminal):
                                    reason = "MISSING_EXACT_BASKET_COMPONENT_BAR"
                                    break
                                terminal_value += float(leg["quantity"]) * float(
                                    terminal[4]
                                )
                        else:
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

                event[f"exit_{horizon}"] = target
                event[f"raw_{horizon}"] = raw
                event[f"excess_{horizon}"] = excess
                event[f"reason_{horizon}"] = reason or None
                event[f"continuity_{horizon}"] = terms["decision"]
                event[f"valuationKind_{horizon}"] = terms["kind"]
            if event_number is None:
                raise ValueError("discovery event missing Stage-B event number")
            event["eventNumber"] = event_number
            result.append(event)
    finally:
        db_path.unlink(missing_ok=True)

    if any(str(row["evaluationSession"]) > DISCOVERY_END for row in result):
        raise ValueError("confirmation outcome was opened")
    return result


def _quintile(value: float, cuts: dict[str, Any]) -> str:
    q20 = float(cuts["q20"])
    q40 = float(cuts["q40"])
    q60 = float(cuts["q60"])
    q80 = float(cuts["q80"])
    if value <= q20:
        return "Q1"
    if value <= q40:
        return "Q2"
    if value <= q60:
        return "Q3"
    if value <= q80:
        return "Q4"
    return "Q5"


def _membership(
    row: dict[str, Any],
    *,
    variant_id: str,
    cutpoints: dict[str, Any],
    f2_preferred: str | None = None,
) -> str | None:
    spec = VARIANTS[variant_id]
    source = spec["source"]
    kind = spec["kind"]
    value = row.get(source)
    if kind == "F2_DYNAMIC":
        category = str(value or "")
        if category not in {"DIRECT_ONLY", "INDIRECT_ONLY"}:
            return None
        if f2_preferred is None:
            return category
        return "PREFERRED" if category == f2_preferred else "COMPLEMENT"
    if kind == "TRUE":
        flag = _bool_value(value)
        if flag is None:
            return None
        return "PREFERRED" if flag else "COMPLEMENT"

    number = _optional_float(value)
    if number is None:
        return None
    cuts = cutpoints[source]
    q = _quintile(number, cuts)
    if kind == "Q5":
        return "PREFERRED" if q == "Q5" else "COMPLEMENT"
    if kind == "Q1":
        return "PREFERRED" if q == "Q1" else "COMPLEMENT"
    raise ValueError(f"unsupported variant grouping kind: {kind}")


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _group_summary(
    rows: list[dict[str, Any]],
    horizon: int,
    group: str,
) -> dict[str, Any]:
    matured = [
        row
        for row in rows
        if row["_group"] == group
        and row.get(f"excess_{horizon}") is not None
        and row.get(f"raw_{horizon}") is not None
    ]
    raw = [float(row[f"raw_{horizon}"]) for row in matured]
    excess = [float(row[f"excess_{horizon}"]) for row in matured]
    return {
        "matureN": len(matured),
        "distinctIssuers": len({str(row["issuerCik"]) for row in matured}),
        "rawMean": _mean(raw),
        "rawMedian": _median(raw),
        "spyExcessMean": _mean(excess),
        "spyExcessMedian": _median(excess),
        "spyExcessWinRate": (
            sum(value > 0 for value in excess) / len(excess)
            if excess
            else None
        ),
    }


def _increment(
    rows: list[dict[str, Any]],
    horizon: int = PRIMARY_HORIZON,
) -> float | None:
    preferred = [
        float(row[f"excess_{horizon}"])
        for row in rows
        if row["_group"] == "PREFERRED"
        and row.get(f"excess_{horizon}") is not None
    ]
    complement = [
        float(row[f"excess_{horizon}"])
        for row in rows
        if row["_group"] == "COMPLEMENT"
        and row.get(f"excess_{horizon}") is not None
    ]
    if not preferred or not complement:
        return None
    return statistics.fmean(preferred) - statistics.fmean(complement)


def _equal_weight_increment(
    rows: list[dict[str, Any]],
    field: str,
) -> float | None:
    means: dict[str, list[float]] = {}
    for group in ("PREFERRED", "COMPLEMENT"):
        by_unit: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            if row["_group"] != group or row.get("excess_126") is None:
                continue
            by_unit[str(row[field])].append(float(row["excess_126"]))
        unit_means = [
            statistics.fmean(values)
            for values in by_unit.values()
            if values
        ]
        if not unit_means:
            return None
        means[group] = unit_means
    return statistics.fmean(means["PREFERRED"]) - statistics.fmean(
        means["COMPLEMENT"]
    )


def _top1_removed_increment(rows: list[dict[str, Any]]) -> tuple[float | None, int]:
    matured = [
        row
        for row in rows
        if row["_group"] in {"PREFERRED", "COMPLEMENT"}
        and row.get("excess_126") is not None
    ]
    if not matured:
        return None, 0
    drop_n = math.ceil(0.01 * len(matured))
    ranked = sorted(
        matured,
        key=lambda row: (
            -float(row["excess_126"]),
            int(row["eventNumber"]),
            str(row["issuerCik"]),
        ),
    )
    kept = ranked[drop_n:]
    return _increment(kept), drop_n


def _context_strata(
    rows: list[dict[str, Any]],
    cutpoints: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for feature in CONTEXT_FEATURES:
        cuts = cutpoints.get(feature)
        if not isinstance(cuts, dict) or "q20" not in cuts:
            result[feature] = {"status": "CUTPOINT_UNAVAILABLE"}
            continue
        strata = {}
        for q in ("Q1", "Q2", "Q3", "Q4", "Q5"):
            subset = []
            for row in rows:
                value = _optional_float(row.get(feature))
                if value is None or _quintile(value, cuts) != q:
                    continue
                subset.append(row)
            strata[q] = {
                "matureN": sum(
                    row.get("excess_126") is not None for row in subset
                ),
                "incrementalMean": _increment(subset),
            }
        result[feature] = strata
    result["PIT_MARKET_CAP"] = {
        "status": "PIT_BLOCKED_PENDING_RAW_PRICE_AND_PIT_SHARES",
        "substitutionAllowed": False,
    }
    return result


def _benchmark_keys(path: Path) -> set[tuple[str, str, str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"issuerCik", "ticker", "evaluationSession", "entrySession"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"benchmark event file missing identity fields: {path}")
        keys = {
            (
                str(row["issuerCik"]),
                str(row["ticker"]).upper(),
                str(row["evaluationSession"]),
                str(row["entrySession"]),
            )
            for row in reader
            if str(row["evaluationSession"]) <= DISCOVERY_END
        }
    return keys


def _overlap_metrics(
    rows: list[dict[str, Any]],
    benchmark_sets: dict[str, set[tuple[str, str, str, str]]],
) -> dict[str, Any]:
    result = {}
    for label, keys in benchmark_sets.items():
        subset = [row for row in rows if _base_key(row) in keys]
        result[label] = {
            "observedCohortN": len(subset),
            "preferredMatureN": sum(
                row["_group"] == "PREFERRED"
                and row.get("excess_126") is not None
                for row in subset
            ),
            "complementMatureN": sum(
                row["_group"] == "COMPLEMENT"
                and row.get("excess_126") is not None
                for row in subset
            ),
            "incrementalMean": _increment(subset),
        }
    return result


def _f2_orientation(rows: list[dict[str, Any]]) -> str | None:
    grouped: dict[str, list[float]] = {
        "DIRECT_ONLY": [],
        "INDIRECT_ONLY": [],
    }
    for row in rows:
        category = str(row.get("F2_DIRECT_VS_INDIRECT") or "")
        value = row.get("excess_126")
        if category in grouped and value is not None:
            grouped[category].append(float(value))
    if not grouped["DIRECT_ONLY"] or not grouped["INDIRECT_ONLY"]:
        return None
    direct = statistics.fmean(grouped["DIRECT_ONLY"])
    indirect = statistics.fmean(grouped["INDIRECT_ONLY"])
    return "DIRECT_ONLY" if direct >= indirect else "INDIRECT_ONLY"


def _evaluate_variant(
    *,
    variant_id: str,
    outcomes: list[dict[str, Any]],
    stage_a_summary: dict[str, Any],
    cutpoints: dict[str, Any],
    benchmark_sets: dict[str, set[tuple[str, str, str, str]]],
) -> dict[str, Any]:
    spec = VARIANTS[variant_id]
    coverage = stage_a_summary["coverage"].get(spec["coverage"])
    if not isinstance(coverage, dict):
        raise ValueError(f"Stage A coverage missing: {spec['coverage']}")
    coverage_class = str(coverage["coverageClass"])

    if coverage_class not in ELIGIBLE_COVERAGE:
        return {
            "variantId": variant_id,
            "family": spec["family"],
            "coverageClass": coverage_class,
            "status": "OUTCOME_SKIPPED_BELOW_SPECIALTY_COVERAGE",
            "discoveryPass": False,
        }

    f2_preferred = None
    if spec["kind"] == "F2_DYNAMIC":
        f2_preferred = _f2_orientation(outcomes)
        if f2_preferred is None:
            return {
                "variantId": variant_id,
                "family": spec["family"],
                "coverageClass": coverage_class,
                "status": "INSUFFICIENT_F2_ORIENTATION_DATA",
                "discoveryPass": False,
            }

    rows = []
    for source in outcomes:
        group = _membership(
            source,
            variant_id=variant_id,
            cutpoints=cutpoints,
            f2_preferred=f2_preferred,
        )
        if group is None:
            continue
        item = dict(source)
        item["_group"] = group
        rows.append(item)

    horizon_summaries = {}
    for horizon in HORIZONS:
        horizon_summaries[str(horizon)] = {
            "preferred": _group_summary(rows, horizon, "PREFERRED"),
            "complement": _group_summary(rows, horizon, "COMPLEMENT"),
            "incrementalEventWeightedMean": _increment(rows, horizon),
        }

    primary = horizon_summaries[str(PRIMARY_HORIZON)]
    preferred = primary["preferred"]
    event_increment = primary["incrementalEventWeightedMean"]
    issuer_increment = _equal_weight_increment(rows, "issuerCik")
    session_increment = _equal_weight_increment(rows, "entrySession")
    top1_increment, top1_removed_n = _top1_removed_increment(rows)

    year_increments = {}
    for year in ("2016", "2017", "2018"):
        yearly = [
            row
            for row in rows
            if str(row["evaluationSession"]).startswith(year)
        ]
        year_increments[year] = _increment(yearly)
    positive_years = sum(
        value is not None and value > 0
        for value in year_increments.values()
    )

    adv_q20 = float(cutpoints["DOLLAR_ADV_20"]["q20"])
    outside_adv = [
        row
        for row in rows
        if (
            (value := _optional_float(row.get("DOLLAR_ADV_20"))) is not None
            and value > adv_q20
        )
    ]
    outside_adv_increment = _increment(outside_adv)

    checks = {
        "preferredMatureNAtLeast200": int(preferred["matureN"]) >= 200,
        "preferredDistinctIssuersAtLeast100": (
            int(preferred["distinctIssuers"]) >= 100
        ),
        "eventWeightedIncrementalMeanPositive": (
            event_increment is not None and event_increment > 0
        ),
        "issuerEqualWeightIncrementalMeanPositive": (
            issuer_increment is not None and issuer_increment > 0
        ),
        "entrySessionEqualWeightIncrementalMeanPositive": (
            session_increment is not None and session_increment > 0
        ),
        "top1PctRemovedIncrementalMeanPositive": (
            top1_increment is not None and top1_increment > 0
        ),
        "minimumTwoPositiveDiscoveryYears": positive_years >= 2,
        "outsideBottomDollarAdvQuintileIncrementalMeanPositive": (
            outside_adv_increment is not None and outside_adv_increment > 0
        ),
    }
    passed = all(checks.values())

    frozen_group = {
        "kind": spec["kind"],
        "sourceFeature": spec["source"],
    }
    if spec["kind"] == "F2_DYNAMIC":
        frozen_group["preferred"] = f2_preferred
        frozen_group["complement"] = (
            "INDIRECT_ONLY"
            if f2_preferred == "DIRECT_ONLY"
            else "DIRECT_ONLY"
        )
    elif spec["kind"] in {"Q1", "Q5"}:
        frozen_group["cutpoints"] = cutpoints[spec["source"]]
    elif spec["kind"] == "TRUE":
        frozen_group["preferred"] = True
        frozen_group["complement"] = False

    return {
        "variantId": variant_id,
        "family": spec["family"],
        "coverageClass": coverage_class,
        "status": "DISCOVERY_PASS" if passed else "DISCOVERY_FAIL",
        "observedCohortN": len(rows),
        "frozenGroupDefinition": frozen_group,
        "horizonSummaries": horizon_summaries,
        "primary126": {
            "eventWeightedIncrementalMean": event_increment,
            "issuerEqualWeightIncrementalMean": issuer_increment,
            "entrySessionEqualWeightIncrementalMean": session_increment,
            "top1PctRemovedIncrementalMean": top1_increment,
            "top1PctRemovedRows": top1_removed_n,
            "yearIncrementalMeans": year_increments,
            "positiveDiscoveryYears": positive_years,
            "incrementalMeanOutsideBottomDollarAdvQuintile": (
                outside_adv_increment
            ),
        },
        "contextStrata": _context_strata(rows, cutpoints),
        "benchmarkOverlap": _overlap_metrics(rows, benchmark_sets),
        "advancementChecks": checks,
        "discoveryPass": passed,
        "candidateScope": (
            "GENERAL"
            if coverage_class == "GENERAL_ELIGIBLE"
            else "SPECIALTY"
        ),
    }


def _select_family_winners(
    results: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    winners: dict[str, dict[str, Any]] = {}
    for family in ("F1", "F2", "F3", "F4"):
        passing = [
            row
            for row in results
            if row["family"] == family and row.get("discoveryPass") is True
        ]
        if not passing:
            winners[family] = {
                "family": family,
                "status": "NO_FAMILY_CANDIDATE",
            }
            continue

        def rank(row: dict[str, Any]) -> tuple[float, float, float, float, str]:
            p = row["primary126"]
            return (
                -float(p["top1PctRemovedIncrementalMean"]),
                -float(p["issuerEqualWeightIncrementalMean"]),
                -float(p["entrySessionEqualWeightIncrementalMean"]),
                -float(p["eventWeightedIncrementalMean"]),
                str(row["variantId"]),
            )

        winner = sorted(passing, key=rank)[0]
        winners[family] = {
            "family": family,
            "status": "DISCOVERY_FAMILY_CANDIDATE_FROZEN",
            "variantId": winner["variantId"],
            "coverageClass": winner["coverageClass"],
            "candidateScope": winner["candidateScope"],
            "frozenGroupDefinition": winner["frozenGroupDefinition"],
            "selectionTuple": {
                "top1PctRemovedIncrementalMean": winner["primary126"][
                    "top1PctRemovedIncrementalMean"
                ],
                "issuerEqualWeightIncrementalMean": winner["primary126"][
                    "issuerEqualWeightIncrementalMean"
                ],
                "entrySessionEqualWeightIncrementalMean": winner["primary126"][
                    "entrySessionEqualWeightIncrementalMean"
                ],
                "eventWeightedIncrementalMean": winner["primary126"][
                    "eventWeightedIncrementalMean"
                ],
            },
        }
    return winners


def run(
    *,
    stage_a_dir: Path,
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
    stage_a_summary, cutpoints, matrix = _load_stage_a(stage_a_dir)
    ledger = _load_ledger(ledger_path)
    final_rows = _load_final_contract(final_contract_path)
    actions = _load_actions(corporate_actions_path)

    benchmark_sets = {
        "B1": _benchmark_keys(b1_events_path),
        "B2": _benchmark_keys(b2_events_path),
        "B3": _benchmark_keys(b3_events_path),
        "B4": _benchmark_keys(b4_events_path),
    }

    outcomes = _value_outcomes(
        matrix,
        ledger,
        final_rows,
        actions,
        market_root,
        output,
    )

    results = [
        _evaluate_variant(
            variant_id=variant_id,
            outcomes=outcomes,
            stage_a_summary=stage_a_summary,
            cutpoints=cutpoints,
            benchmark_sets=benchmark_sets,
        )
        for variant_id in VARIANTS
    ]
    winners = _select_family_winners(results)

    output_rows = []
    feature_fields = list(matrix[0].keys())
    for row in outcomes:
        output_rows.append(
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
        )
    event_path = output / "discovery-event-outcomes.csv"
    with event_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)

    maturity = {
        str(horizon): {
            "valued": sum(row.get(f"excess_{horizon}") is not None for row in outcomes),
            "missing": sum(row.get(f"excess_{horizon}") is None for row in outcomes),
            "reasonCounts": dict(
                sorted(
                    Counter(
                        str(row.get(f"reason_{horizon}") or "VALUED")
                        for row in outcomes
                    ).items()
                )
            ),
        }
        for horizon in HORIZONS
    }

    payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_INSIDER_FEATURE_TOURNAMENT_DISCOVERY_COMPLETE",
        "definitionId": "PHASE1_INSIDER_FEATURE_TOURNAMENT_V1",
        "researchOnly": True,
        "discoveryPeriod": "2016-01-01 through 2018-12-31",
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "secondaryHorizonsSessions": [21, 63, 252],
        "sourceStageAEvents": EXPECTED_STAGE_A_EVENTS,
        "discoveryEvents": len(outcomes),
        "discoveryDistinctIssuers": len(
            {str(row["issuerCik"]) for row in outcomes}
        ),
        "maturity": maturity,
        "variantCount": len(results),
        "variantResults": results,
        "familyCandidates": winners,
        "familyCandidateCount": sum(
            row["status"] == "DISCOVERY_FAMILY_CANDIDATE_FROZEN"
            for row in winners.values()
        ),
        "confirmationOpened": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "compositeWeightsFit": False,
        "newVariantsAdded": False,
        "nextGate": (
            "Freeze these exact discovery family candidates, then apply them "
            "unchanged to 2019-2020 confirmation."
        ),
    }
    (output / "discovery-results.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-a-dir", type=Path, required=True)
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
                if key != "variantResults"
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
