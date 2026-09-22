"""Evaluate frozen Monster Winner candidates on maximum existing pre-2023 data."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import exchange_calendars as xcals

import research_monster_winner_discovery as monster

CANDIDATES = ("F3_DRAWDOWN_252", "F4_DISTANCE_BELOW")
DATA_BOUNDARY = "2022-12-30"
SEALED_YEAR = 2023
MIN_COVERAGE = 0.95
MAX_GAP = 5

LABELS = {
    126: {
        "M100_126_CLOSE": 2.0,
        "M200_126_CLOSE": 3.0,
    },
    252: {
        "M50_252_CLOSE": 1.5,
        "M100_252_CLOSE": 2.0,
        "M200_252_CLOSE": 3.0,
        "M500_252_CLOSE": 6.0,
    },
}


def _semantic_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(row["issuerCik"]),
        str(row["ticker"]).upper(),
        str(row["evaluationSession"]),
        str(row["entrySession"]),
        str(row["horizon"]),
        str(row["targetExitSession"]),
    )


def _event_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(row["issuerCik"]),
        str(row["ticker"]).upper(),
        str(row["evaluationSession"]),
        str(row["entrySession"]),
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def _load_scope(
    csv_path: Path,
    summary_path: Path,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    required = {
        "status": "MONSTER_MAX_EXISTING_DATA_EXTENSION_FEATURE_SCOPE_FROZEN",
        "outcomesRead": False,
        "priceOutcomeFieldsRead": [],
        "monsterLabelsComputed": False,
        "knownSampleOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "events": 9872,
        "mature126Events": 7493,
        "mature252Events": 4582,
        "marketDataBoundary": DATA_BOUNDARY,
    }
    for key, expected in required.items():
        if summary.get(key) != expected:
            raise ValueError(f"extension scope mismatch: {key}")
    rows = _read_csv(csv_path)
    if len(rows) != 9872:
        raise ValueError("extension feature matrix row count changed")
    return summary, rows


def _load_audit(
    csv_path: Path,
    summary_path: Path,
) -> tuple[dict[str, Any], dict[tuple[str, ...], dict[str, str]]]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    required = {
        "status": "MONSTER_MAX_EXISTING_DATA_EXTENSION_CONTINUITY_AUDITED",
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "knownSampleOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "matureHorizonRows": 12075,
        "horizonRowCounts": {"126": 7493, "252": 4582},
        "unresolvedRows": 109,
        "unresolvedByHorizon": {"126": 41, "252": 68},
    }
    for key, expected in required.items():
        if summary.get(key) != expected:
            raise ValueError(f"extension continuity mismatch: {key}")
    rows = _read_csv(csv_path)
    if len(rows) != 12075:
        raise ValueError("extension continuity CSV row count changed")
    result = {_semantic_key(row): row for row in rows}
    if len(result) != len(rows):
        raise ValueError("duplicate extension continuity semantic key")
    return summary, result


def _load_final_126_contract(path: Path) -> dict[tuple[str, ...], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "status": "PHASE1_FEATURE_TOURNAMENT_VALIDATION_FINAL_CONTINUITY_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceScopeRows": 7493,
        "classifiedRows": 191,
        "unresolvedRows": 0,
        "resolutionComplete": True,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"final 126 continuity contract mismatch: {key}")
    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != 191:
        raise ValueError("final 126 continuity rows changed")
    result = {_semantic_key(row): dict(row) for row in rows}
    if len(result) != 191:
        raise ValueError("duplicate final 126 continuity semantic key")
    return result


def _load_actions(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("period") != ["2016-01-01", "2022-12-31"]:
        raise ValueError("corporate-action period changed")
    if payload.get("performanceRead") is not False:
        raise ValueError("corporate actions are not outcome-blind")
    if payload.get("oosOpened") is not False:
        raise ValueError("corporate actions opened OOS")
    rows = payload.get("actions")
    if not isinstance(rows, list):
        raise ValueError("corporate action inventory missing actions")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        action_id = str(row.get("id") or "")
        if not action_id or action_id in result:
            raise ValueError("duplicate/empty corporate-action ID")
        result[action_id] = dict(row)
    return result


def _action_ids(row: dict[str, Any]) -> list[str]:
    return sorted(
        item
        for item in str(row.get("candidateActionIds") or "").split(";")
        if item
    )


def _market_maps(
    root: Path,
    tickers: set[str],
) -> dict[str, dict[str, tuple[float, float, int, int, bool]]]:
    if (root / "2023").exists():
        raise ValueError("sealed 2023 market directory mounted")
    result = {ticker: {} for ticker in tickers}
    for year in (2021, 2022):
        matches = list(root.rglob(f"canonical-market-{year}.csv"))
        if len(matches) != 1:
            raise ValueError(
                f"expected one canonical-market-{year}.csv, got {len(matches)}"
            )
        with matches[0].open(encoding="utf-8", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader)
            index = {name: pos for pos, name in enumerate(header)}
            required = {
                "ticker", "date", "open", "close",
                "volume", "trade_count", "terminal_candidate",
            }
            if not required.issubset(index):
                raise ValueError("market outcome fields missing")
            for raw in reader:
                ticker = raw[index["ticker"]].strip().upper()
                if ticker not in result:
                    continue
                day = raw[index["date"]][:10]
                if int(day[:4]) >= SEALED_YEAR:
                    raise ValueError("sealed OOS market row encountered")
                result[ticker][day] = (
                    float(raw[index["open"]]),
                    float(raw[index["close"]]),
                    int(float(raw[index["volume"]] or 0)),
                    int(float(raw[index["trade_count"]] or 0)),
                    raw[index["terminal_candidate"]].strip().lower() == "true",
                )
    return result


def _regular(row: tuple[float, float, int, int, bool] | None) -> bool:
    return (
        row is not None
        and not bool(row[4])
        and int(row[2]) > 0
        and int(row[3]) > 0
    )


def _contract_terms(
    ticker: str,
    contract: dict[str, Any] | None,
) -> dict[str, Any]:
    if contract is None:
        return {
            "mode": "ORDINARY",
            "effectiveDate": "",
            "successor": ticker,
            "quantity": 1.0,
            "cash": 0.0,
        }

    decision = str(contract.get("resolutionDecision") or "")
    kind = str(contract.get("transformationKind") or "")
    effective = str(contract.get("effectiveDate") or "")[:10]
    successor = str(contract.get("successorSymbol") or "").upper()
    quantity = float(contract.get("successorSharesPerEntryShare") or 0.0)
    cash = float(contract.get("cashPerEntryShare") or 0.0)

    if decision == "SAME_SECURITY_CONTINUITY":
        return {
            "mode": "ORDINARY",
            "effectiveDate": "",
            "successor": ticker,
            "quantity": 1.0,
            "cash": 0.0,
        }

    if decision == "SYMBOL_CHANGED_SAME_SECURITY":
        if not effective or not successor:
            raise ValueError("incomplete symbol-change 126 contract")
        return {
            "mode": "TRANSFORM",
            "effectiveDate": effective,
            "successor": successor,
            "quantity": 1.0,
            "cash": 0.0,
        }

    if decision == "TRANSFORMED_HOLDER_CONSIDERATION":
        if kind == "STOCK_DIVIDEND_QUANTITY":
            return {
                "mode": "ORDINARY",
                "effectiveDate": "",
                "successor": ticker,
                "quantity": 1.0,
                "cash": 0.0,
            }
        if not effective:
            raise ValueError("transformed 126 contract lacks effective date")
        if quantity > 0 and not successor:
            raise ValueError("transformed 126 contract lacks successor")
        if quantity <= 0 and cash <= 0:
            raise ValueError("transformed 126 contract lacks consideration")
        return {
            "mode": "TRANSFORM",
            "effectiveDate": effective,
            "successor": successor,
            "quantity": quantity,
            "cash": cash,
        }

    raise ValueError(f"unsupported 126 continuity decision: {decision}")


def _provider_terms(
    source: dict[str, str],
    actions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    ticker = str(source["ticker"]).upper()
    state = str(source["state"])

    if state == "PRICE_CONTINUOUS_ADJUSTED":
        return {
            "mode": "ORDINARY",
            "effectiveDate": "",
            "successor": ticker,
            "quantity": 1.0,
            "cash": 0.0,
            "forcedUnknown": False,
        }

    ids = _action_ids(source)
    rows = [actions[action_id] for action_id in ids if action_id in actions]
    if len(rows) != len(ids):
        raise ValueError("252 audit action missing from frozen inventory")

    if state == "UNRESOLVED_CONTINUITY":
        dates = sorted(
            {
                str(row.get("actionDate") or "")[:10]
                for row in rows
                if str(row.get("actionDate") or "")[:10]
            }
        )
        if str(source["resolutionSource"]) == "long_internal_gap":
            return {
                "mode": "UNRESOLVED_GAP",
                "effectiveDate": "",
                "successor": ticker,
                "quantity": 1.0,
                "cash": 0.0,
                "forcedUnknown": True,
            }
        return {
            "mode": "UNRESOLVED_ACTION",
            "effectiveDate": dates[0] if dates else str(source["entrySession"]),
            "successor": "",
            "quantity": 0.0,
            "cash": 0.0,
            "forcedUnknown": True,
        }

    if len(rows) != 1:
        raise ValueError("deterministic 252 provider row must have one action")
    action = rows[0]
    effective = str(action.get("actionDate") or "")[:10]
    bucket = str(action.get("bucket") or "")

    if state == "SYMBOL_CHANGED_SAME_SECURITY":
        if bucket != "name_changes":
            raise ValueError("deterministic symbol change uses wrong action")
        successor = str(action.get("new_symbol") or "").upper()
        if not effective or not successor:
            raise ValueError("incomplete deterministic symbol change")
        return {
            "mode": "TRANSFORM",
            "effectiveDate": effective,
            "successor": successor,
            "quantity": 1.0,
            "cash": 0.0,
            "forcedUnknown": False,
        }

    if state != "TRANSFORMED_HOLDER_CONSIDERATION":
        raise ValueError(f"unsupported deterministic 252 state: {state}")

    if bucket == "cash_mergers":
        cash = float(action["rate"])
        return {
            "mode": "TRANSFORM",
            "effectiveDate": effective,
            "successor": "",
            "quantity": 0.0,
            "cash": cash,
            "forcedUnknown": False,
        }
    if bucket == "redemptions":
        cash = float(action["rate"])
        return {
            "mode": "TRANSFORM",
            "effectiveDate": effective,
            "successor": "",
            "quantity": 0.0,
            "cash": cash,
            "forcedUnknown": False,
        }
    if bucket == "stock_mergers":
        acquiree = float(action["acquiree_rate"])
        acquirer = float(action["acquirer_rate"])
        successor = str(action.get("acquirer_symbol") or "").upper()
        if acquiree <= 0 or acquirer <= 0 or not successor:
            raise ValueError("incomplete deterministic stock merger")
        return {
            "mode": "TRANSFORM",
            "effectiveDate": effective,
            "successor": successor,
            "quantity": acquirer / acquiree,
            "cash": 0.0,
            "forcedUnknown": False,
        }
    if bucket == "stock_and_cash_mergers":
        acquiree = float(action["acquiree_rate"])
        acquirer = float(action["acquirer_rate"])
        successor = str(action.get("acquirer_symbol") or "").upper()
        cash = float(action["cash_rate"])
        if acquiree <= 0 or acquirer <= 0 or not successor or cash < 0:
            raise ValueError("incomplete deterministic stock-and-cash merger")
        return {
            "mode": "TRANSFORM",
            "effectiveDate": effective,
            "successor": successor,
            "quantity": acquirer / acquiree,
            "cash": cash,
            "forcedUnknown": False,
        }

    raise ValueError(f"unsupported deterministic provider bucket: {bucket}")


def _required_tickers(
    feature_rows: list[dict[str, str]],
    audit: dict[tuple[str, ...], dict[str, str]],
    contract126: dict[tuple[str, ...], dict[str, Any]],
    actions: dict[str, dict[str, Any]],
) -> set[str]:
    tickers = {str(row["ticker"]).upper() for row in feature_rows}
    for contract in contract126.values():
        successor = str(contract.get("successorSymbol") or "").upper()
        if successor:
            tickers.add(successor)
    for row in audit.values():
        if row["horizon"] != "252" or row["state"] == "UNRESOLVED_CONTINUITY":
            continue
        for action_id in _action_ids(row):
            action = actions.get(action_id)
            if action is None:
                continue
            for field in ("new_symbol", "acquirer_symbol"):
                symbol = str(action.get(field) or "").upper()
                if symbol:
                    tickers.add(symbol)
    return tickers


def _path_value(
    *,
    day: str,
    ticker: str,
    terms: dict[str, Any],
    maps: dict[str, dict[str, tuple[float, float, int, int, bool]]],
) -> float | None:
    mode = str(terms["mode"])
    effective = str(terms.get("effectiveDate") or "")

    if mode == "UNRESOLVED_ACTION" and day >= effective:
        return None

    if mode in {"ORDINARY", "UNRESOLVED_GAP", "UNRESOLVED_ACTION"}:
        row = maps.get(ticker, {}).get(day)
        return float(row[1]) if _regular(row) else None

    if mode != "TRANSFORM":
        raise ValueError(f"unsupported holder path mode: {mode}")

    if day < effective:
        row = maps.get(ticker, {}).get(day)
        return float(row[1]) if _regular(row) else None

    value = float(terms["cash"])
    quantity = float(terms["quantity"])
    successor = str(terms["successor"])
    if quantity > 0:
        row = maps.get(successor, {}).get(day)
        if not _regular(row):
            return None
        value += quantity * float(row[1])
    return value


def _stats(values: list[float | None]) -> tuple[float, int]:
    coverage = sum(value is not None for value in values) / len(values)
    run = 0
    max_run = 0
    for value in values:
        if value is None:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return coverage, max_run


def _label(
    *,
    values: list[float | None],
    entry_open: float,
    multiple: float,
    forced_unknown: bool,
) -> str:
    threshold = entry_open * multiple
    if any(value is not None and value >= threshold for value in values):
        return "POSITIVE"
    if forced_unknown:
        return "UNKNOWN"
    coverage, max_gap = _stats(values)
    if coverage >= MIN_COVERAGE and max_gap <= MAX_GAP:
        return "NEGATIVE"
    return "UNKNOWN"


def _group_counts(
    rows: list[dict[str, Any]],
    label: str,
    group: str,
) -> dict[str, Any]:
    subset = [row for row in rows if row["_group"] == group]
    counts = Counter(str(row[label]) for row in subset)
    n = len(subset)
    resolvable = counts["POSITIVE"] + counts["NEGATIVE"]
    return {
        "N": n,
        "positive": counts["POSITIVE"],
        "negative": counts["NEGATIVE"],
        "unknown": counts["UNKNOWN"],
        "observedPositiveDensity": counts["POSITIVE"] / n if n else None,
        "evaluableHitRate": counts["POSITIVE"] / resolvable if resolvable else None,
        "unknownShare": counts["UNKNOWN"] / n if n else None,
    }


def _evaluate(
    outcomes: list[dict[str, Any]],
    *,
    candidate: str,
    label: str,
    horizon: int,
    year: str | None = None,
) -> dict[str, Any]:
    group_field = (
        "F3_DRAWDOWN_252_GROUP"
        if candidate == "F3_DRAWDOWN_252"
        else "F4_DISTANCE_BELOW_GROUP"
    )
    rows: list[dict[str, Any]] = []
    for source in outcomes:
        if int(source["horizon"]) != horizon:
            continue
        if year and not str(source["evaluationSession"]).startswith(year):
            continue
        group = str(source.get(group_field) or "")
        if group not in {"PREFERRED", "COMPLEMENT"}:
            continue
        row = dict(source)
        row["_group"] = group
        rows.append(row)

    preferred = _group_counts(rows, label, "PREFERRED")
    complement = _group_counts(rows, label, "COMPLEMENT")
    pd = preferred["observedPositiveDensity"]
    cd = complement["observedPositiveDensity"]
    lift = pd / cd if pd is not None and cd not in (None, 0.0) else None
    total_positive = preferred["positive"] + complement["positive"]
    capture = preferred["positive"] / total_positive if total_positive else None
    total_n = preferred["N"] + complement["N"]
    review_share = preferred["N"] / total_n if total_n else None
    return {
        "candidate": candidate,
        "horizon": horizon,
        "label": label,
        "year": year or "POOLED_MATURE",
        "cohortN": total_n,
        "preferred": preferred,
        "complement": complement,
        "lift": lift,
        "capture": capture,
        "reviewShare": review_share,
        "reviewReduction": 1.0 - review_share if review_share is not None else None,
    }


def run(
    *,
    feature_csv: Path,
    feature_summary: Path,
    audit_csv: Path,
    audit_summary: Path,
    corporate_actions: Path,
    final_126_contract: Path,
    market_root: Path,
    output: Path,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    scope_meta, feature_rows = _load_scope(feature_csv, feature_summary)
    audit_meta, audit = _load_audit(audit_csv, audit_summary)
    contract126 = _load_final_126_contract(final_126_contract)
    actions = _load_actions(corporate_actions)

    feature_by_event = {_event_key(row): row for row in feature_rows}
    if len(feature_by_event) != len(feature_rows):
        raise ValueError("duplicate extension feature event key")

    tickers = _required_tickers(feature_rows, audit, contract126, actions)
    maps = _market_maps(market_root, tickers)

    calendar = xcals.get_calendar("XNYS")
    sessions = [
        str(value.date())
        for value in calendar.sessions_in_range("2021-01-01", DATA_BOUNDARY)
    ]
    session_index = {day: idx for idx, day in enumerate(sessions)}

    # The complete frozen 126 contract must cover every affected 126 row and no
    # unrelated row. Ordinary 126 rows are implicit.
    mature126_keys = {
        key for key, row in audit.items() if row["horizon"] == "126"
    }
    if not set(contract126).issubset(mature126_keys):
        raise ValueError("final 126 contract contains row outside extension mature scope")

    outcomes: list[dict[str, Any]] = []
    for key, cont in sorted(
        audit.items(),
        key=lambda item: (
            item[1]["evaluationSession"],
            int(item[1]["horizon"]),
            int(item[1]["eventNumber"]),
        ),
    ):
        event = feature_by_event.get(_event_key(cont))
        if event is None:
            raise ValueError("continuity row missing extension feature event")

        horizon = int(cont["horizon"])
        ticker = str(cont["ticker"]).upper()
        entry = str(cont["entrySession"])
        target = str(cont["targetExitSession"])
        if target > DATA_BOUNDARY:
            raise ValueError("outcome row crossed market boundary")

        entry_row = maps.get(ticker, {}).get(entry)
        if not _regular(entry_row):
            raise ValueError("frozen extension exact entry bar disappeared")
        entry_open = float(entry_row[0])
        if entry_open <= 0:
            raise ValueError("non-positive extension entry open")

        if horizon == 126:
            terms = _contract_terms(ticker, contract126.get(key))
            forced_unknown = False
        elif horizon == 252:
            terms = _provider_terms(cont, actions)
            forced_unknown = bool(terms.get("forcedUnknown"))
        else:
            raise ValueError("unexpected extension horizon")

        if entry not in session_index or target not in session_index:
            raise ValueError("extension path boundary absent from XNYS calendar")
        start = session_index[entry]
        stop = session_index[target]
        if stop - start != horizon:
            raise ValueError("extension exact horizon clock changed")
        path_sessions = sessions[start : stop + 1]
        values = [
            _path_value(
                day=day,
                ticker=ticker,
                terms=terms,
                maps=maps,
            )
            for day in path_sessions
        ]

        result: dict[str, Any] = {
            "eventNumber": int(cont["eventNumber"]),
            "issuerCik": str(cont["issuerCik"]),
            "ticker": ticker,
            "evaluationSession": str(cont["evaluationSession"]),
            "entrySession": entry,
            "horizon": horizon,
            "targetExitSession": target,
            "F3_DRAWDOWN_252_GROUP": str(
                event.get("F3_DRAWDOWN_252_GROUP") or ""
            ),
            "F4_DISTANCE_BELOW_GROUP": str(
                event.get("F4_DISTANCE_BELOW_GROUP") or ""
            ),
            "continuityAuditState": str(cont["state"]),
            "continuityResolutionSource": str(cont["resolutionSource"]),
            "forcedUnknownContinuity": forced_unknown,
        }
        for label, multiple in LABELS[horizon].items():
            result[label] = _label(
                values=values,
                entry_open=entry_open,
                multiple=multiple,
                forced_unknown=forced_unknown,
            )
        outcomes.append(result)

    if len(outcomes) != 12075:
        raise ValueError("extension outcome row count changed")

    evaluations: list[dict[str, Any]] = []
    for candidate in CANDIDATES:
        for label in LABELS[252]:
            evaluations.append(
                _evaluate(
                    outcomes,
                    candidate=candidate,
                    label=label,
                    horizon=252,
                    year="2021",
                )
            )
        for label in LABELS[126]:
            evaluations.append(
                _evaluate(
                    outcomes,
                    candidate=candidate,
                    label=label,
                    horizon=126,
                    year="2021",
                )
            )
            evaluations.append(
                _evaluate(
                    outcomes,
                    candidate=candidate,
                    label=label,
                    horizon=126,
                    year="2022",
                )
            )

    max_2022_eval = max(
        str(row["evaluationSession"])
        for row in outcomes
        if int(row["horizon"]) == 126
        and str(row["evaluationSession"]).startswith("2022")
    )

    fields = [
        "eventNumber",
        "issuerCik",
        "ticker",
        "evaluationSession",
        "entrySession",
        "horizon",
        "targetExitSession",
        "F3_DRAWDOWN_252_GROUP",
        "F4_DISTANCE_BELOW_GROUP",
        "continuityAuditState",
        "continuityResolutionSource",
        "forcedUnknownContinuity",
        "M50_252_CLOSE",
        "M100_252_CLOSE",
        "M200_252_CLOSE",
        "M500_252_CLOSE",
        "M100_126_CLOSE",
        "M200_126_CLOSE",
    ]
    with (output / "monster-max-existing-event-outcomes.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in outcomes:
            writer.writerow({field: row.get(field, "") for field in fields})

    payload = {
        "schemaVersion": "1.0.0",
        "status": "MONSTER_MAX_EXISTING_DATA_EXTENSION_OUTCOMES_COMPLETE",
        "definitionId": "MONSTER_WINNER_ENRICHMENT_V1",
        "researchOnly": True,
        "dataPeriodAvailable": ["2016-01-01", DATA_BOUNDARY],
        "extensionEvaluationPeriod": ["2021-01-01", "2022-12-31"],
        "primary252ExtensionEvaluationYear": "2021",
        "mature126Events": 7493,
        "mature252Events": 4582,
        "rightCensored126Events": int(scope_meta["rightCensored126Events"]),
        "rightCensored252Events": int(scope_meta["rightCensored252Events"]),
        "unresolved252RowsConservative": int(
            audit_meta["unresolvedByHorizon"]["252"]
        ),
        "latestMature2022EvaluationSessionFor126": max_2022_eval,
        "priceFieldsRead": ["entry_open", "exact_path_close"],
        "intradayHighRead": False,
        "knownSampleOnly": True,
        "knownSampleLabel": "KNOWN_SAMPLE_MAX_AVAILABLE_EXTENSION",
        "oosOpened": False,
        "productionScoringChanged": False,
        "retuningPerformed": False,
        "compositeFit": False,
        "candidateResults": evaluations,
        "nextBoundary": (
            "The maximum comparable existing-data extension is complete. "
            "A full 252-session 2022 result requires opening 2023 market data."
        ),
    }
    (output / "monster-max-existing-results.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-csv", type=Path, required=True)
    parser.add_argument("--feature-summary", type=Path, required=True)
    parser.add_argument("--audit-csv", type=Path, required=True)
    parser.add_argument("--audit-summary", type=Path, required=True)
    parser.add_argument("--corporate-actions", type=Path, required=True)
    parser.add_argument("--final-126-contract", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        feature_csv=args.feature_csv,
        feature_summary=args.feature_summary,
        audit_csv=args.audit_csv,
        audit_summary=args.audit_summary,
        corporate_actions=args.corporate_actions,
        final_126_contract=args.final_126_contract,
        market_root=args.market_root,
        output=args.output,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "latestMature2022EvaluationSessionFor126": (
                    result["latestMature2022EvaluationSessionFor126"]
                ),
                "candidateResults": result["candidateResults"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
