"""Phase-1 B1 continuity-corrected performance, development evidence only.

Downstream of the frozen zero-unresolved continuity gate. Selection definitions are
not changed. B1 terminal holder returns are recomputed under frozen continuity rules;
frozen canonical B0/B1/B2/B4 results are retained side-by-side as comparators.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

import research_market_event_audit as market_audit
import research_phase1_b0 as b0
import research_phase1_security_continuity_resolution as continuity

HORIZONS = (21, 63, 126, 252)
PRIMARY_HORIZON = 126
SEALED_YEAR = 2023
DEVELOPMENT_START = "2016-01-01"
DEVELOPMENT_END = "2020-12-31"
OUTCOME_END = "2022-12-31"
CONTINUITY_RUN_ID = 35275669277
CONTINUITY_ARTIFACT = "phase1-security-continuity-resolution-35275669277"
CONTINUITY_ARTIFACT_DIGEST = (
    "sha256:f5d1dbbb2978bf495d439dfaa0981f4f0d987260e85e96f266866647b0d65f8c"
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _year(value: str, field: str) -> int:
    text = str(value or "").strip()
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        raise ValueError(f"invalid ISO date for {field}: {text!r}")
    return int(text[:4])


def _assert_unsealed(value: str, field: str) -> None:
    if _year(value, field) >= SEALED_YEAR:
        raise ValueError(f"sealed OOS boundary violated by {field}")


def _load_continuity_summary(path: Path) -> dict[str, Any]:
    summary = _read_json(path)
    required = {
        "status": "PHASE1_SECURITY_CONTINUITY_RESOLUTION_COMPLETE",
        "unresolvedEventHorizonRows": 0,
        "performanceStageBlocked": False,
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceLedgerUntouched": True,
        "frozenScopeExpanded": False,
        "sealedYear": SEALED_YEAR,
        "outcomeEnd": OUTCOME_END,
        "primaryHorizon": PRIMARY_HORIZON,
        "horizons": list(HORIZONS),
    }
    for key, expected in required.items():
        if summary.get(key) != expected:
            raise ValueError(f"continuity gate mismatch for {key}: {summary.get(key)!r}")
    if summary.get("developmentCohortYears") != [2016, 2017, 2018, 2019, 2020]:
        raise ValueError("continuity gate development cohort changed")
    return summary


def _load_events(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        required = {
            "issuerCik",
            "ticker",
            "evaluationSession",
            "entrySession",
            "entryOpen",
            *(f"exit_{h}" for h in HORIZONS),
            *(f"raw_{h}" for h in HORIZONS),
            *(f"excess_{h}" for h in HORIZONS),
        }
        if not required.issubset(fields):
            raise ValueError("B1 event file missing canonical outcome fields")
        rows = []
        for raw in reader:
            row = {field: str(raw.get(field) or "").strip() for field in reader.fieldnames or []}
            evaluation = row["evaluationSession"]
            if not DEVELOPMENT_START <= evaluation <= DEVELOPMENT_END:
                raise ValueError("B1 event outside frozen development cohort")
            _assert_unsealed(evaluation, "events.evaluationSession")
            _assert_unsealed(row["entrySession"], "events.entrySession")
            for horizon in HORIZONS:
                exit_session = row[f"exit_{horizon}"]
                if exit_session:
                    _assert_unsealed(exit_session, f"events.exit_{horizon}")
                    if exit_session > OUTCOME_END:
                        raise ValueError("B1 outcome exceeds frozen 2022 boundary")
            rows.append(row)
    if not rows:
        raise ValueError("B1 event file is empty")
    return rows


def _load_ledger(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
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
            "candidateActionIds",
            "resolutionSource",
            "resolutionEffectiveDate",
            "shareQuantityFactor",
            "frozenResolutionApplied",
        }
        if not required.issubset(fields):
            raise ValueError("resolved continuity ledger missing required fields")
        rows = []
        for raw in reader:
            row = {field: str(raw.get(field) or "").strip() for field in reader.fieldnames or []}
            if row["state"] == "UNRESOLVED_CONTINUITY":
                raise ValueError("corrected performance cannot consume unresolved continuity")
            for field in ("evaluationSession", "entrySession", "targetExitSession"):
                _assert_unsealed(row[field], f"ledger.{field}")
            if int(row["horizon"]) not in HORIZONS:
                raise ValueError("resolved ledger contains non-frozen horizon")
            rows.append(row)
    if not rows:
        raise ValueError("resolved continuity ledger is empty")
    return rows


def _load_actions(path: Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(path)
    if payload.get("period") != ["2016-01-01", OUTCOME_END]:
        raise ValueError("corporate-action inventory period changed")
    if payload.get("performanceRead") is not False or payload.get("oosOpened") is not False:
        raise ValueError("corporate-action inventory violates frozen research boundary")
    actions = payload.get("actions")
    if not isinstance(actions, list):
        raise ValueError("corporate-action inventory missing actions")
    by_id = {}
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("invalid corporate action")
        action_id = str(action.get("id") or "")
        if not action_id:
            raise ValueError("corporate action missing id")
        action_date = str(action.get("actionDate") or "")
        if action_date:
            _assert_unsealed(action_date, "corporateAction.actionDate")
        by_id[action_id] = action
    return by_id


def _load_fixtures(path: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    payload = _read_json(path)
    if payload.get("performanceRead") is not False or payload.get("oosOpened") is not False:
        raise ValueError("fixture contract violates frozen research boundary")
    result = {}
    for fixture in payload.get("fixtures", []):
        effective = str(fixture["effectiveDate"])
        _assert_unsealed(effective, "fixture.effectiveDate")
        key = (
            str(fixture["issuerCik"]),
            str(fixture["ticker"]).upper(),
            str(fixture["entrySession"]),
        )
        result[key] = fixture
    return result


def _fixture_for(
    row: dict[str, str], fixtures: dict[tuple[str, str, str], dict[str, Any]]
) -> dict[str, Any] | None:
    return fixtures.get((row["issuerCik"], row["ticker"].upper(), row["entrySession"]))


def _single_action(row: dict[str, str], actions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ids = [value for value in row["candidateActionIds"].split(";") if value]
    if len(ids) != 1:
        raise ValueError(
            "deterministic provider valuation requires exactly one action; "
            f"event={row['eventNumber']} horizon={row['horizon']} ids={ids}"
        )
    if ids[0] not in actions:
        raise ValueError(f"candidate action absent from frozen inventory: {ids[0]}")
    return actions[ids[0]]


def _validate_effective(row: dict[str, str], effective: str) -> None:
    _assert_unsealed(effective, "valuation.effectiveDate")
    if not row["entrySession"] < effective <= row["targetExitSession"]:
        raise ValueError("valuation effective date falls outside event horizon")


def _valuation_terms(
    row: dict[str, str],
    *,
    actions: dict[str, dict[str, Any]],
    fixtures: dict[tuple[str, str, str], dict[str, Any]],
) -> dict[str, Any]:
    """Return deterministic terminal holder consideration for one frozen ledger row."""
    state = row["state"]
    original = row["ticker"].upper()
    successor = row["successorSymbol"].upper()
    if state == "PRICE_CONTINUOUS_ADJUSTED":
        return {
            "kind": state,
            "effectiveDate": row.get("resolutionEffectiveDate") or "",
            "terminalTicker": original,
            "shareQuantity": 1.0,
            "cashPerEntryShare": 0.0,
        }

    fixture = _fixture_for(row, fixtures)
    if state == "DISCONTINUOUS_NO_COMPLETE_VALUATION":
        if fixture is None or fixture.get("correctionState") != state:
            raise ValueError("discontinuous state lacks matching frozen fixture")
        effective = str(fixture["effectiveDate"])
        _validate_effective(row, effective)
        return {
            "kind": state,
            "effectiveDate": effective,
            "terminalTicker": "",
            "shareQuantity": 0.0,
            "cashPerEntryShare": 0.0,
        }

    if state == "SYMBOL_CHANGED_SAME_SECURITY":
        if not successor:
            raise ValueError("symbol-change state missing successor")
        if fixture is not None and fixture.get("correctionState") == state:
            effective = str(fixture["effectiveDate"])
        else:
            action = _single_action(row, actions)
            if action.get("bucket") != "name_changes":
                raise ValueError("symbol change is not backed by a name-change action")
            effective = str(action.get("actionDate") or "")
            if str(action.get("new_symbol") or "").upper() != successor:
                raise ValueError("symbol-change successor differs from frozen provider action")
        _validate_effective(row, effective)
        return {
            "kind": state,
            "effectiveDate": effective,
            "terminalTicker": successor,
            "shareQuantity": 1.0,
            "cashPerEntryShare": 0.0,
        }

    if state != "TRANSFORMED_HOLDER_CONSIDERATION":
        raise ValueError(f"unsupported continuity state: {state}")

    if row.get("frozenResolutionApplied", "").lower() == "true":
        effective = row["resolutionEffectiveDate"]
        quantity_text = row["shareQuantityFactor"]
        quantity = float(quantity_text) if quantity_text else 0.0
        if not effective or quantity <= 0 or not successor:
            raise ValueError("frozen overlay transformation lacks deterministic stock terms")
        _validate_effective(row, effective)
        return {
            "kind": "FROZEN_RESOLUTION_STOCK_TRANSFORMATION",
            "effectiveDate": effective,
            "terminalTicker": successor,
            "shareQuantity": quantity,
            "cashPerEntryShare": 0.0,
        }

    if fixture is not None and fixture.get("correctionState") == state:
        effective = str(fixture["effectiveDate"])
        quantity = float(fixture.get("successorSharesPerEntryShare"))
        fixture_successor = str(fixture.get("successorSymbol") or "").upper()
        if quantity <= 0 or not fixture_successor:
            raise ValueError("holder-transformation fixture lacks stock terms")
        if successor and successor != fixture_successor:
            raise ValueError("fixture successor differs from resolved ledger")
        _validate_effective(row, effective)
        return {
            "kind": "VERIFIED_FIXTURE_STOCK_TRANSFORMATION",
            "effectiveDate": effective,
            "terminalTicker": fixture_successor,
            "shareQuantity": quantity,
            "cashPerEntryShare": 0.0,
        }

    action = _single_action(row, actions)
    effective = str(action.get("actionDate") or "")
    _validate_effective(row, effective)
    bucket = str(action.get("bucket") or "")
    if bucket == "cash_mergers":
        cash = float(action["rate"])
        if cash < 0:
            raise ValueError("negative cash-merger rate")
        return {
            "kind": "CASH_MERGER",
            "effectiveDate": effective,
            "terminalTicker": "",
            "shareQuantity": 0.0,
            "cashPerEntryShare": cash,
        }
    if bucket in {"stock_mergers", "stock_and_cash_mergers"}:
        acquiree_rate = float(action["acquiree_rate"])
        acquirer_rate = float(action["acquirer_rate"])
        if acquiree_rate <= 0 or acquirer_rate < 0:
            raise ValueError("invalid provider merger share rates")
        quantity = acquirer_rate / acquiree_rate
        cash = 0.0
        if bucket == "stock_and_cash_mergers":
            cash = float(action["cash_rate"]) / acquiree_rate
        action_successor = str(action.get("acquirer_symbol") or "").upper()
        if not action_successor or quantity <= 0:
            raise ValueError("provider stock merger lacks successor terms")
        if successor and successor != action_successor:
            raise ValueError("provider merger successor differs from resolved ledger")
        return {
            "kind": bucket.upper(),
            "effectiveDate": effective,
            "terminalTicker": action_successor,
            "shareQuantity": quantity,
            "cashPerEntryShare": cash,
        }
    if bucket == "redemptions":
        cash = float(action["rate"])
        if cash < 0:
            raise ValueError("negative redemption rate")
        return {
            "kind": "REDEMPTION",
            "effectiveDate": effective,
            "terminalTicker": "",
            "shareQuantity": 0.0,
            "cashPerEntryShare": cash,
        }
    raise ValueError(f"unsupported holder transformation bucket: {bucket}")


def _load_market_maps(
    market_root: Path, output: Path, tickers: set[str]
) -> tuple[dict[str, dict[str, tuple[Any, ...]]], Path]:
    if (market_root / "2023").exists():
        raise ValueError("sealed 2023 market directory must not be present")
    market_files = market_audit._market_files(market_root)
    if not market_files:
        raise ValueError("no frozen market files found")
    for path in market_files:
        relative = path.relative_to(market_root)
        if relative.parts and relative.parts[0].isdigit() and int(relative.parts[0]) >= SEALED_YEAR:
            raise ValueError("sealed OOS market file discovered")
    db_path = output / "phase1-b1-corrected.sqlite"
    db_path.unlink(missing_ok=True)
    market_audit._build_market_db(market_files, db_path)
    conn = sqlite3.connect(db_path)
    maps = {}
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


def _optional_float(value: str) -> float | None:
    text = str(value or "").strip()
    return float(text) if text else None


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
        row for row in rows if row["horizon"] == horizon and row["correctedExcess"] is not None
    ]
    raw = [float(row["correctedRaw"]) for row in matured]
    excess = [float(row["correctedExcess"]) for row in matured]
    return {
        "horizonSessions": horizon,
        "maturedOutcomeCount": len(matured),
        "distinctIssuers": len({row["issuerCik"] for row in matured}),
        "rawReturnMean": statistics.fmean(raw) if raw else None,
        "rawReturnMedian": statistics.median(raw) if raw else None,
        "spyExcessMean": statistics.fmean(excess) if excess else None,
        "spyExcessMedian": statistics.median(excess) if excess else None,
        "spyExcessWinRate": sum(value > 0 for value in excess) / len(excess) if excess else None,
        "spyExcessP05": _percentile(excess, 0.05),
        "spyExcessP10": _percentile(excess, 0.10),
        "maeRecomputed": False,
    }


def _delta(left: object, right: object) -> float | None:
    if left is None or right is None:
        return None
    return float(left) - float(right)


def _canonical_horizon(summary: dict[str, Any], horizon: int) -> dict[str, Any]:
    value = summary.get("horizons", {}).get(str(horizon))
    if not isinstance(value, dict):
        raise ValueError(f"canonical summary missing horizon {horizon}")
    return value


def _validate_canonical_summary(summary: dict[str, Any], label: str) -> None:
    if summary.get("period") != "2016-2020 XNYS evaluation-session cohort":
        raise ValueError(f"{label} period changed")
    if summary.get("outcomeMarketBoundary") != "2016-2022 only":
        raise ValueError(f"{label} outcome boundary changed")
    if summary.get("primaryHorizonSessions") != PRIMARY_HORIZON:
        raise ValueError(f"{label} primary horizon changed")
    if summary.get("researchOnly") is not True or summary.get("oosOpened") is not False:
        raise ValueError(f"{label} research boundary changed")
    if summary.get("productionScoringChanged") is not False:
        raise ValueError(f"{label} production scoring boundary changed")


def _b4_coverage(path: Path, keys: set[tuple[str, str, str, str]]) -> dict[str, Any]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"issuerCik", "ticker", "evaluationSession", "entrySession"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("B4 event file missing identity fields")
        total = 0
        covered = 0
        for row in reader:
            evaluation = str(row["evaluationSession"])
            entry = str(row["entrySession"])
            _assert_unsealed(evaluation, "b4.evaluationSession")
            _assert_unsealed(entry, "b4.entrySession")
            total += 1
            key = (str(row["issuerCik"]), str(row["ticker"]), evaluation, entry)
            covered += key in keys
    return {
        "b4ExactEntryEvents": total,
        "coveredByFrozenB1ContinuityLedger": covered,
        "outsideFrozenB1ContinuityLedger": total - covered,
        "correctedB4Claimed": False,
        "reason": (
            "B4 is intersected before its own 20-session deduplication; events outside the frozen "
            "deduplicated B1 continuity cohort are not auto-added to the continuity scope."
        ),
    }


def run(
    *,
    b1_events_path: Path,
    resolved_ledger_path: Path,
    continuity_summary_path: Path,
    corporate_actions_path: Path,
    fixtures_path: Path,
    resolution_contract_path: Path,
    market_root: Path,
    b0_summary_path: Path,
    b1_summary_path: Path,
    b2_summary_path: Path,
    b4_summary_path: Path,
    b4_events_path: Path,
    output: Path,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    gate = _load_continuity_summary(continuity_summary_path)
    _, contract_sha = continuity._load_contract(resolution_contract_path)
    if contract_sha != gate.get("contractSha256"):
        raise ValueError("resolution contract SHA differs from green continuity gate")
    events = _load_events(b1_events_path)
    ledger = _load_ledger(resolved_ledger_path)
    if len(events) != 6094 or len(ledger) != 24376:
        raise ValueError("B1 frozen event/horizon scope changed")
    actions = _load_actions(corporate_actions_path)
    fixtures = _load_fixtures(fixtures_path)

    ledger_by_key = {}
    event_keys = set()
    needed_tickers = {row["ticker"].upper() for row in ledger}
    terms_by_key = {}
    for row in ledger:
        key = (int(row["eventNumber"]), int(row["horizon"]))
        if key in ledger_by_key:
            raise ValueError("duplicate event/horizon in resolved ledger")
        ledger_by_key[key] = row
        event_keys.add(
            (row["issuerCik"], row["ticker"], row["evaluationSession"], row["entrySession"])
        )
        terms = _valuation_terms(row, actions=actions, fixtures=fixtures)
        terms_by_key[key] = terms
        terminal_ticker = str(terms["terminalTicker"])
        if terminal_ticker:
            needed_tickers.add(terminal_ticker)

    maps, db_path = _load_market_maps(market_root, output, needed_tickers)
    corrected_rows = []
    status_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    changed_value_rows = 0
    try:
        for event_number, event in enumerate(events, start=1):
            identity = (
                event["issuerCik"],
                event["ticker"].upper(),
                event["evaluationSession"],
                event["entrySession"],
            )
            if identity not in event_keys:
                raise ValueError(f"B1 event missing from continuity ledger: {identity}")
            entry_open = float(event["entryOpen"])
            if entry_open <= 0:
                raise ValueError("non-positive canonical B1 entry open")
            spy_entry = maps["SPY"].get(event["entrySession"])
            if not b0._regular(spy_entry):
                raise ValueError("canonical B1 entry lacks regular SPY bar")
            spy_entry_open = float(spy_entry[1])

            for horizon in HORIZONS:
                row = ledger_by_key.get((event_number, horizon))
                if row is None:
                    raise ValueError("missing frozen continuity horizon row")
                if (
                    row["issuerCik"],
                    row["ticker"],
                    row["evaluationSession"],
                    row["entrySession"],
                ) != identity:
                    raise ValueError("event numbering no longer matches frozen B1 order")
                target = row["targetExitSession"]
                if target != event[f"exit_{horizon}"]:
                    raise ValueError("canonical B1 exit differs from continuity target")
                state_counts[row["state"]] += 1
                terms = terms_by_key[(event_number, horizon)]
                original_raw = _optional_float(event[f"raw_{horizon}"])
                original_excess = _optional_float(event[f"excess_{horizon}"])
                corrected_raw = None
                corrected_excess = None
                spy_return = None
                terminal_value = None
                reason = ""

                if row["state"] == "DISCONTINUOUS_NO_COMPLETE_VALUATION":
                    status = "MISSING_DISCONTINUOUS_NO_COMPLETE_VALUATION"
                    reason = "complete holder consideration is not deterministically valued"
                else:
                    spy_exit = maps["SPY"].get(target)
                    if not b0._regular(spy_exit):
                        status = "MISSING_EXACT_SPY_EXIT_BAR"
                        reason = "canonical SPY target exit bar missing"
                    else:
                        spy_return = float(spy_exit[4]) / spy_entry_open - 1.0
                        cash = float(terms["cashPerEntryShare"])
                        quantity = float(terms["shareQuantity"])
                        terminal_ticker = str(terms["terminalTicker"])
                        stock_value = 0.0
                        status = ""
                        if quantity:
                            terminal = maps.get(terminal_ticker, {}).get(target)
                            if not b0._regular(terminal):
                                status = "MISSING_EXACT_TERMINAL_HOLDER_BAR"
                                reason = f"missing exact target bar for {terminal_ticker}"
                            else:
                                stock_value = quantity * float(terminal[4])
                        if not status:
                            terminal_value = cash + stock_value
                            corrected_raw = terminal_value / entry_open - 1.0
                            corrected_excess = corrected_raw - spy_return
                            status = "VALUED"
                            if row["state"] == "PRICE_CONTINUOUS_ADJUSTED":
                                if original_raw is None or not math.isclose(
                                    corrected_raw, original_raw, rel_tol=1e-12, abs_tol=1e-12
                                ):
                                    raise ValueError(
                                        "ordinary price continuity changed versus frozen B1"
                                    )
                            if original_raw is None or not math.isclose(
                                corrected_raw, original_raw, rel_tol=1e-12, abs_tol=1e-12
                            ):
                                changed_value_rows += 1
                status_counts[status] += 1
                corrected_rows.append(
                    {
                        "eventNumber": event_number,
                        "issuerCik": event["issuerCik"],
                        "ticker": event["ticker"].upper(),
                        "evaluationSession": event["evaluationSession"],
                        "entrySession": event["entrySession"],
                        "entryOpen": entry_open,
                        "horizon": horizon,
                        "targetExitSession": target,
                        "continuityState": row["state"],
                        "successorSymbol": row["successorSymbol"],
                        "valuationKind": terms["kind"],
                        "effectiveDate": terms["effectiveDate"],
                        "terminalTicker": terms["terminalTicker"],
                        "shareQuantity": terms["shareQuantity"],
                        "cashPerEntryShare": terms["cashPerEntryShare"],
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
    finally:
        db_path.unlink(missing_ok=True)

    with (output / "b1-corrected-event-horizons.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(corrected_rows[0]))
        writer.writeheader()
        writer.writerows(corrected_rows)

    corrected_horizons = {str(h): _aggregate(corrected_rows, h) for h in HORIZONS}
    canonical = {
        "B0": _read_json(b0_summary_path),
        "B1": _read_json(b1_summary_path),
        "B2": _read_json(b2_summary_path),
        "B4": _read_json(b4_summary_path),
    }
    for label, summary in canonical.items():
        _validate_canonical_summary(summary, label)

    side_by_side = {}
    for horizon in HORIZONS:
        key = str(horizon)
        original_b1 = _canonical_horizon(canonical["B1"], horizon)
        corrected = corrected_horizons[key]
        side_by_side[key] = {
            "B0Canonical": _canonical_horizon(canonical["B0"], horizon),
            "B1Canonical": original_b1,
            "B1ContinuityCorrected": corrected,
            "B2Canonical": _canonical_horizon(canonical["B2"], horizon),
            "B4Canonical": _canonical_horizon(canonical["B4"], horizon),
            "B1CorrectedMinusCanonical": {
                "maturedOutcomeCountDelta": (
                    corrected["maturedOutcomeCount"] - original_b1["maturedOutcomeCount"]
                ),
                "rawReturnMeanDelta": _delta(
                    corrected["rawReturnMean"], original_b1["rawReturnMean"]
                ),
                "rawReturnMedianDelta": _delta(
                    corrected["rawReturnMedian"], original_b1["rawReturnMedian"]
                ),
                "spyExcessMeanDelta": _delta(
                    corrected["spyExcessMean"], original_b1["spyExcessMean"]
                ),
                "spyExcessMedianDelta": _delta(
                    corrected["spyExcessMedian"], original_b1["spyExcessMedian"]
                ),
                "spyExcessWinRateDelta": _delta(
                    corrected["spyExcessWinRate"], original_b1["spyExcessWinRate"]
                ),
            },
        }

    coverage = _b4_coverage(b4_events_path, event_keys)
    summary = {
        "schemaVersion": 1,
        "status": "PHASE1_B1_CONTINUITY_CORRECTED_PERFORMANCE_COMPLETE",
        "resultClass": "research/descriptive",
        "formalAlphaClaimed": False,
        "p0Status": "exploratory",
        "dependenceAwareRobustnessComplete": False,
        "calendarTimeRobustnessComplete": False,
        "hacRobustnessComplete": False,
        "period": "2016-2020 XNYS evaluation-session cohort",
        "outcomeMarketBoundary": "2016-2022 only",
        "horizonsSessions": list(HORIZONS),
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "b1DefinitionChanged": False,
        "b2DefinitionChanged": False,
        "b4DefinitionChanged": False,
        "continuityGate": {
            "runId": CONTINUITY_RUN_ID,
            "artifact": CONTINUITY_ARTIFACT,
            "artifactDigest": CONTINUITY_ARTIFACT_DIGEST,
            "contractSha256": contract_sha,
            "unresolvedEventHorizonRows": 0,
        },
        "scope": {
            "b1Events": len(events),
            "b1EventHorizonRows": len(corrected_rows),
            "continuityStates": dict(sorted(state_counts.items())),
            "valuationStatusCounts": dict(sorted(status_counts.items())),
            "rowsWhereCorrectedRawDiffersOrOriginalWasMissing": changed_value_rows,
        },
        "b4ContinuityCoverageBoundary": coverage,
        "horizons": side_by_side,
        "primary126": side_by_side[str(PRIMARY_HORIZON)],
        "interpretationGuardrail": (
            "Continuity-corrected B1 development outcomes are descriptive research evidence only. "
            "Frozen canonical B0/B2/B4 are comparators, not relabeled as continuity-corrected, "
            "because their full event sets were not in the frozen B1 continuity scope. No formal "
            "alpha claim is permitted before dependence-aware, calendar-time and HAC work."
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--b1-events", type=Path, required=True)
    parser.add_argument("--resolved-ledger", type=Path, required=True)
    parser.add_argument("--continuity-summary", type=Path, required=True)
    parser.add_argument("--corporate-actions", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--resolution-contract", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--b0-summary", type=Path, required=True)
    parser.add_argument("--b1-summary", type=Path, required=True)
    parser.add_argument("--b2-summary", type=Path, required=True)
    parser.add_argument("--b4-summary", type=Path, required=True)
    parser.add_argument("--b4-events", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run(
        b1_events_path=args.b1_events,
        resolved_ledger_path=args.resolved_ledger,
        continuity_summary_path=args.continuity_summary,
        corporate_actions_path=args.corporate_actions,
        fixtures_path=args.fixtures,
        resolution_contract_path=args.resolution_contract,
        market_root=args.market_root,
        b0_summary_path=args.b0_summary,
        b1_summary_path=args.b1_summary,
        b2_summary_path=args.b2_summary,
        b4_summary_path=args.b4_summary,
        b4_events_path=args.b4_events,
        output=args.output,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
