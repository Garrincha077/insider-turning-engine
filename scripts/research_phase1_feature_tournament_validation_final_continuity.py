"""Freeze the complete performance-blind F2 validation continuity contract."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

EXPECTED_SCOPE_ROWS = 7493
EXPECTED_ORDINARY_ROWS = 7302
EXPECTED_PROVIDER_SYMBOL_ROWS = 99
EXPECTED_PROVIDER_TRANSFORMED_ROWS = 51
EXPECTED_UNRESOLVED_ROWS = 41
EXPECTED_AFFECTED_ROWS = 191
EXPECTED_SCOPE_KEY = (
    "sha256:8f2d7d09c43689007d22690d8c846cf253532d8cff15997c8def2ddde8df7bc3"
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


def _key_object(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventNumber": int(row["eventNumber"]),
        "issuerCik": str(row["issuerCik"]),
        "ticker": str(row["ticker"]).upper(),
        "evaluationSession": str(row["evaluationSession"]),
        "entrySession": str(row["entrySession"]),
        "horizon": int(row["horizon"]),
        "targetExitSession": str(row["targetExitSession"]),
    }


def _key_digest(rows: list[dict[str, Any]]) -> str:
    lines = sorted(
        json.dumps(
            _key_object(row),
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in rows
    )
    return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _number(value: object, *, default: str = "") -> str:
    if value in (None, ""):
        return default
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"invalid numeric value: {value}") from None
    if not number.is_finite():
        raise ValueError("non-finite numeric value")
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def _assert_boundary(payload: dict[str, Any], label: str) -> None:
    required = {
        "researchOnly": True,
        "performanceRead": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for field, expected in required.items():
        if payload.get(field) != expected:
            raise ValueError(f"{label} boundary mismatch: {field}")
    if "priceFieldsRead" in payload and payload["priceFieldsRead"] != []:
        raise ValueError(f"{label} opened price fields")
    if (
        "featureOutcomesRead" in payload
        and payload["featureOutcomesRead"] is not False
    ):
        raise ValueError(f"{label} opened feature outcomes")
    if "validationOpened" in payload and payload["validationOpened"] is not False:
        raise ValueError(f"{label} opened validation")
    if (
        "validationPerformanceOpened" in payload
        and payload["validationPerformanceOpened"] is not False
    ):
        raise ValueError(f"{label} opened validation performance")


def _load_actions(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _assert_boundary(payload, "corporate-action inventory")
    if payload.get("period") != ["2016-01-01", "2022-12-31"]:
        raise ValueError("corporate-action period changed")
    actions = payload.get("actions")
    if not isinstance(actions, list):
        raise ValueError("corporate-action inventory missing actions")
    result: dict[str, dict[str, Any]] = {}
    for action in actions:
        action_id = str(action.get("id") or "")
        if not action_id or action_id in result:
            raise ValueError("duplicate or empty corporate-action ID")
        result[action_id] = dict(action)
    return result


def _candidate_ids(row: dict[str, Any]) -> list[str]:
    value = row.get("candidateActionIds")
    if value in (None, "", []):
        value = row.get("sourceActionIds")
    if isinstance(value, list):
        return sorted(str(item) for item in value if str(item))
    return sorted(item for item in str(value or "").split(";") if item)


def _provider_resolution(
    row: dict[str, Any],
    action_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    ids = _candidate_ids(row)
    if len(ids) != 1:
        raise ValueError("pre-resolved provider row does not have one action")
    action = action_index.get(ids[0])
    if action is None:
        raise ValueError("pre-resolved provider action is missing")

    state = str(row["state"])
    ticker = str(row["ticker"]).upper()
    successor = str(row.get("successorSymbol") or "").upper()
    action_date = str(action.get("actionDate") or "")
    if not str(row["entrySession"]) < action_date <= str(row["targetExitSession"]):
        raise ValueError("pre-resolved provider effective date outside horizon")

    out = {
        **_key_object(row),
        "expectedSourceResolutionSource": "provider",
        "effectiveDate": action_date,
        "sourceActionIds": ids,
        "classificationSource": "VALIDATION_PROVIDER_COMPLETE_TERMS",
        "evidenceClass": "FROZEN_PROVIDER_COMPLETE_ECONOMIC_TERMS",
        "basket": [],
    }

    if state == "SYMBOL_CHANGED_SAME_SECURITY":
        if action.get("bucket") != "name_changes":
            raise ValueError("same-security provider row is not a name change")
        if str(action.get("old_symbol") or "").upper() != ticker:
            raise ValueError("name-change old symbol changed")
        new_symbol = str(action.get("new_symbol") or "").upper()
        if not new_symbol or new_symbol != successor:
            raise ValueError("name-change successor symbol changed")
        old_cusip = str(action.get("old_cusip") or "")
        new_cusip = str(action.get("new_cusip") or "")
        if not old_cusip or old_cusip != new_cusip:
            raise ValueError("name-change CUSIP no longer proves same security")
        out.update(
            resolutionDecision="SYMBOL_CHANGED_SAME_SECURITY",
            transformationKind="SAME_SECURITY_SYMBOL_CHANGE",
            resultState="SYMBOL_CHANGED_SAME_SECURITY",
            successorSymbol=new_symbol,
            successorSharesPerEntryShare="1",
            cashPerEntryShare="0",
        )
        return out

    if state != "TRANSFORMED_HOLDER_CONSIDERATION":
        raise ValueError("unexpected pre-resolved provider state")

    bucket = str(action.get("bucket") or "")
    if bucket == "cash_mergers":
        cash = Decimal(_number(action.get("rate")))
        if cash < 0 or successor:
            raise ValueError("invalid complete cash-merger terms")
        out.update(
            resolutionDecision="TRANSFORMED_HOLDER_CONSIDERATION",
            transformationKind="PROVIDER_CASH_MERGER",
            resultState="TRANSFORMED_HOLDER_CONSIDERATION",
            successorSymbol="",
            successorSharesPerEntryShare="0",
            cashPerEntryShare=_number(cash),
        )
        return out

    if bucket == "stock_mergers":
        acquiree = Decimal(_number(action.get("acquiree_rate")))
        acquirer = Decimal(_number(action.get("acquirer_rate")))
        new_symbol = str(action.get("acquirer_symbol") or "").upper()
        if acquiree <= 0 or acquirer <= 0 or not new_symbol:
            raise ValueError("invalid complete stock-merger terms")
        if new_symbol != successor:
            raise ValueError("stock-merger successor symbol changed")
        quantity = acquirer / acquiree
        out.update(
            resolutionDecision="TRANSFORMED_HOLDER_CONSIDERATION",
            transformationKind="PROVIDER_STOCK_MERGER",
            resultState="TRANSFORMED_HOLDER_CONSIDERATION",
            successorSymbol=new_symbol,
            successorSharesPerEntryShare=_number(quantity),
            cashPerEntryShare="0",
        )
        return out

    raise ValueError(f"unsupported pre-resolved provider bucket: {bucket}")


def _resolution_rows(
    path: Path,
    *,
    label: str,
    expected_rows: int,
) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _assert_boundary(payload, label)
    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != expected_rows:
        raise ValueError(f"{label} resolution row count changed")
    return [dict(row) for row in rows]


def _validate_explicit(
    row: dict[str, Any],
    source: dict[str, Any],
) -> None:
    if source.get("state") != "UNRESOLVED_CONTINUITY":
        raise ValueError("explicit resolution no longer targets unresolved row")
    expected_source = str(row.get("expectedSourceResolutionSource") or "")
    if expected_source and expected_source != str(source["resolutionSource"]):
        raise ValueError("explicit source provenance changed")
    if _candidate_ids(row) != _candidate_ids(source):
        raise ValueError("explicit corporate-action identity changed")

    effective = str(row.get("effectiveDate") or "")
    if not str(source["entrySession"]) < effective <= str(source["targetExitSession"]):
        raise ValueError("explicit effective date outside frozen horizon")

    decision = str(row.get("resolutionDecision") or "")
    state = str(row.get("resultState") or "")
    successor = str(row.get("successorSymbol") or "").upper()
    quantity = Decimal(_number(row.get("successorSharesPerEntryShare"), default="0"))
    cash = Decimal(_number(row.get("cashPerEntryShare"), default="0"))
    if quantity < 0 or cash < 0:
        raise ValueError("negative explicit holder terms")

    if decision == "SAME_SECURITY_CONTINUITY":
        if (
            state != "PRICE_CONTINUOUS_ADJUSTED"
            or successor != str(source["ticker"]).upper()
            or quantity != 1
            or cash != 0
        ):
            raise ValueError("invalid same-security explicit resolution")
        return

    if decision == "SYMBOL_CHANGED_SAME_SECURITY":
        if (
            state != "SYMBOL_CHANGED_SAME_SECURITY"
            or not successor
            or quantity != 1
            or cash != 0
        ):
            raise ValueError("invalid symbol-change explicit resolution")
        return

    if decision == "TRANSFORMED_HOLDER_CONSIDERATION":
        basket = row.get("basket") or []
        if state != "TRANSFORMED_HOLDER_CONSIDERATION":
            raise ValueError("transformed explicit result state changed")
        if successor and quantity <= 0:
            raise ValueError("transformed successor quantity is not positive")
        if not successor and cash <= 0 and not basket:
            raise ValueError("transformed explicit row has no consideration")
        return

    raise ValueError(f"unsupported explicit decision: {decision}")


def run(
    *,
    audit_csv: Path,
    audit_summary: Path,
    corporate_actions: Path,
    exact_action: Path,
    hsdt: Path,
    stock_dividend: Path,
    incomplete_merger: Path,
    spac_exchange: Path,
    cbtx: Path,
    long_gap10: Path,
    output: Path,
) -> dict[str, Any]:
    summary = json.loads(audit_summary.read_text(encoding="utf-8"))
    _assert_boundary(summary, "validation continuity audit")
    if summary.get("status") != (
        "PHASE1_FEATURE_TOURNAMENT_VALIDATION_CONTINUITY_AUDITED"
    ):
        raise ValueError("validation continuity audit status changed")
    if summary.get("scopeRows") != EXPECTED_SCOPE_ROWS:
        raise ValueError("validation continuity scope count changed")
    if summary.get("unresolvedRows") != EXPECTED_UNRESOLVED_ROWS:
        raise ValueError("validation continuity unresolved count changed")
    if summary.get("sourceScopeKeySha256") != EXPECTED_SCOPE_KEY:
        raise ValueError("validation source-scope key changed")

    audit = _load_csv(audit_csv)
    if len(audit) != EXPECTED_SCOPE_ROWS:
        raise ValueError("validation audit CSV row count changed")
    source_counts = Counter(str(row["state"]) for row in audit)
    expected_counts = {
        "PRICE_CONTINUOUS_ADJUSTED": EXPECTED_ORDINARY_ROWS,
        "SYMBOL_CHANGED_SAME_SECURITY": EXPECTED_PROVIDER_SYMBOL_ROWS,
        "TRANSFORMED_HOLDER_CONSIDERATION": EXPECTED_PROVIDER_TRANSFORMED_ROWS,
        "UNRESOLVED_CONTINUITY": EXPECTED_UNRESOLVED_ROWS,
    }
    if dict(sorted(source_counts.items())) != expected_counts:
        raise ValueError("validation audit state partition changed")

    action_index = _load_actions(corporate_actions)
    provider_source = [
        row
        for row in audit
        if row["state"]
        in {
            "SYMBOL_CHANGED_SAME_SECURITY",
            "TRANSFORMED_HOLDER_CONSIDERATION",
        }
    ]
    provider_rows = [
        _provider_resolution(row, action_index)
        for row in provider_source
    ]
    if len(provider_rows) != (
        EXPECTED_PROVIDER_SYMBOL_ROWS + EXPECTED_PROVIDER_TRANSFORMED_ROWS
    ):
        raise ValueError("provider-complete row count changed")

    groups = [
        ("EXACT_ACTION_PRIOR", _resolution_rows(
            exact_action,
            label="exact-action prior",
            expected_rows=8,
        )),
        ("HSDT_PRIMARY", _resolution_rows(
            hsdt,
            label="HSDT primary",
            expected_rows=1,
        )),
        ("STOCK_DIVIDEND_PRIMARY", _resolution_rows(
            stock_dividend,
            label="stock-dividend primary",
            expected_rows=5,
        )),
        ("INCOMPLETE_STOCK_MERGER_PRIMARY", _resolution_rows(
            incomplete_merger,
            label="incomplete-stock-merger primary",
            expected_rows=8,
        )),
        ("SPAC_SHARE_EXCHANGE_PRIMARY", _resolution_rows(
            spac_exchange,
            label="SPAC share-exchange primary",
            expected_rows=8,
        )),
        ("CBTX_PRIMARY", _resolution_rows(
            cbtx,
            label="CBTX primary",
            expected_rows=1,
        )),
        ("LONG_GAP10_PRIMARY", _resolution_rows(
            long_gap10,
            label="long-gap10 primary",
            expected_rows=10,
        )),
    ]
    explicit_rows = [row for _, rows in groups for row in rows]
    if len(explicit_rows) != EXPECTED_UNRESOLVED_ROWS:
        raise ValueError("explicit resolution union is not 41 rows")

    unresolved_source = [
        row for row in audit if row["state"] == "UNRESOLVED_CONTINUITY"
    ]
    unresolved_index = {_key(row): row for row in unresolved_source}
    if len(unresolved_index) != EXPECTED_UNRESOLVED_ROWS:
        raise ValueError("duplicate unresolved validation key")
    explicit_index = {_key(row): row for row in explicit_rows}
    if len(explicit_index) != EXPECTED_UNRESOLVED_ROWS:
        raise ValueError("duplicate explicit validation resolution key")
    if set(explicit_index) != set(unresolved_index):
        raise ValueError("explicit 41-row union differs from frozen unresolved scope")
    for key, row in explicit_index.items():
        _validate_explicit(row, unresolved_index[key])

    merged: list[dict[str, Any]] = []
    for row in provider_rows:
        item = dict(row)
        item["resolutionGroup"] = "PROVIDER_COMPLETE_TERMS"
        merged.append(item)
    for group, rows in groups:
        for row in rows:
            item = dict(row)
            item["resolutionGroup"] = group
            merged.append(item)

    if len(merged) != EXPECTED_AFFECTED_ROWS:
        raise ValueError("final validation continuity row count is not 191")
    if len({_key(row) for row in merged}) != EXPECTED_AFFECTED_ROWS:
        raise ValueError("final validation continuity contract has duplicate keys")

    affected_source = [
        row for row in audit if row["state"] != "PRICE_CONTINUOUS_ADJUSTED"
    ]
    if {_key(row) for row in affected_source} != {_key(row) for row in merged}:
        raise ValueError("final contract does not cover every affected validation row")

    decisions = Counter(str(row.get("resolutionDecision") or "") for row in merged)
    states = Counter(str(row.get("resultState") or "") for row in merged)
    if decisions != {
        "SAME_SECURITY_CONTINUITY": 11,
        "SYMBOL_CHANGED_SAME_SECURITY": 101,
        "TRANSFORMED_HOLDER_CONSIDERATION": 79,
    }:
        raise ValueError("final validation decision partition changed")
    if states != {
        "PRICE_CONTINUOUS_ADJUSTED": 11,
        "SYMBOL_CHANGED_SAME_SECURITY": 101,
        "TRANSFORMED_HOLDER_CONSIDERATION": 79,
    }:
        raise ValueError("final validation result-state partition changed")

    merged.sort(key=lambda row: int(row["eventNumber"]))
    group_counts = {
        "PROVIDER_COMPLETE_TERMS": len(provider_rows),
        **{name: len(rows) for name, rows in groups},
    }
    payload = {
        "schemaVersion": "1.0.0",
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
        "sourceOrdinaryAdjustedRows": EXPECTED_ORDINARY_ROWS,
        "sourceAffectedRows": EXPECTED_AFFECTED_ROWS,
        "sourceUnresolvedRows": EXPECTED_UNRESOLVED_ROWS,
        "classifiedRows": EXPECTED_AFFECTED_ROWS,
        "unresolvedRows": 0,
        "sourceGroupCounts": group_counts,
        "resolutionDecisionCounts": dict(sorted(decisions.items())),
        "resultStateCounts": dict(sorted(states.items())),
        "classifiedKeySha256": _key_digest(merged),
        "sourceValidationScopeKeySha256": EXPECTED_SCOPE_KEY,
        "resolutionRows": merged,
        "resolutionComplete": True,
        "finalResolutionContractCreated": True,
        "validationPerformanceOpened": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-csv", type=Path, required=True)
    parser.add_argument("--audit-summary", type=Path, required=True)
    parser.add_argument("--corporate-actions", type=Path, required=True)
    parser.add_argument("--exact-action", type=Path, required=True)
    parser.add_argument("--hsdt", type=Path, required=True)
    parser.add_argument("--stock-dividend", type=Path, required=True)
    parser.add_argument("--incomplete-merger", type=Path, required=True)
    parser.add_argument("--spac-exchange", type=Path, required=True)
    parser.add_argument("--cbtx", type=Path, required=True)
    parser.add_argument("--long-gap10", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        audit_csv=args.audit_csv,
        audit_summary=args.audit_summary,
        corporate_actions=args.corporate_actions,
        exact_action=args.exact_action,
        hsdt=args.hsdt,
        stock_dividend=args.stock_dividend,
        incomplete_merger=args.incomplete_merger,
        spac_exchange=args.spac_exchange,
        cbtx=args.cbtx,
        long_gap10=args.long_gap10,
        output=args.output,
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "resolutionRows"},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
