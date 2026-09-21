"""Economic-equivalence pass for frozen B1/B3 continuity evidence overlap.

This pass exists because the B1 and B3 frozen contracts use slightly different
schema representations. It compares substantive holder outcomes without using
performance or price data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

EXPECTED_SCOPE_ROWS = 210
SEALED_YEAR = 2023
SEMANTIC_KEY_FIELDS = (
    "issuerCik",
    "ticker",
    "evaluationSession",
    "entrySession",
    "horizon",
    "targetExitSession",
)
FORBIDDEN_PREFIXES = ("raw_", "excess_", "mae_", "forward_return", "future_return")


def _semantic_key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row[field]) for field in SEMANTIC_KEY_FIELDS)


def _key_object(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "issuerCik": str(row["issuerCik"]),
        "ticker": str(row["ticker"]).upper(),
        "evaluationSession": str(row["evaluationSession"]),
        "entrySession": str(row["entrySession"]),
        "horizon": int(row["horizon"]),
        "targetExitSession": str(row["targetExitSession"]),
    }


def _key_digest(rows: list[dict[str, Any]]) -> str:
    lines = sorted(
        json.dumps(_key_object(row), sort_keys=True, separators=(",", ":"))
        for row in rows
    )
    return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _assert_safe(value: Any, source: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            name = str(key).lower()
            if any(name.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
                raise ValueError(f"{source} contains forbidden field {key}")
            _assert_safe(nested, source)
    elif isinstance(value, list):
        for nested in value:
            _assert_safe(nested, source)


def _assert_date(value: object, field: str) -> None:
    text = str(value or "")
    if len(text) < 10:
        raise ValueError(f"invalid {field}")
    if int(text[:4]) >= SEALED_YEAR:
        raise ValueError(f"sealed OOS boundary violated by {field}")


def _number(value: object, *, default: str = "") -> str:
    if value in (None, ""):
        return default
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    if number == 0:
        return "0"
    normalized = number.normalize()
    return format(normalized, "f")


def _normalize_b1(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("researchOnly") is not True:
        raise ValueError("B1 contract is not research-only")
    if payload.get("performanceRead") is not False:
        raise ValueError("B1 contract is not performance-blind")
    if payload.get("oosOpened") is not False:
        raise ValueError("B1 contract opened OOS")
    if payload.get("productionScoringChanged") is not False:
        raise ValueError("B1 contract changed production scoring")
    columns = payload.get("resolutionColumns")
    values = payload.get("resolutions")
    if not isinstance(columns, list) or not isinstance(values, list):
        raise ValueError("invalid B1 compact resolution contract")
    rows = []
    for item in values:
        if not isinstance(item, list) or len(item) != len(columns):
            raise ValueError("invalid B1 compact resolution row")
        rows.append(dict(zip(columns, item, strict=True)))
    if len(rows) != 54:
        raise ValueError("B1 resolution row count changed")
    return rows


def _normalize_b3(payload: dict[str, Any]) -> list[dict[str, Any]]:
    required = {
        "status": "B3_FINAL_CONTINUITY_CONTRACT_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "classifiedRows": 264,
        "unresolvedRows": 0,
        "finalResolutionContractCreated": True,
        "correctedPerformanceOpened": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"B3 final contract mismatch: {key}")
    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != 264:
        raise ValueError("B3 final contract row count changed")
    return rows


def _canonical_basket(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("invalid basket item")
        normalized.append(
            {
                "symbol": str(item.get("symbol") or "").upper(),
                "securityClass": str(item.get("securityClass") or ""),
                "quantity": _number(
                    item.get("quantityPerEntryUnit", item.get("quantity"))
                ),
            }
        )
    return sorted(
        normalized,
        key=lambda item: (
            item["symbol"],
            item["securityClass"],
            item["quantity"],
        ),
    )


def _economic_fingerprint(row: dict[str, Any]) -> dict[str, Any]:
    result_state = str(row.get("resultState") or "")
    successor = str(row.get("successorSymbol") or "").upper()
    quantity = row.get("shareQuantityFactor")
    if quantity in (None, ""):
        quantity = row.get("successorSharesPerEntryShare")
    quantity_default = (
        "1"
        if result_state in {"PRICE_CONTINUOUS_ADJUSTED", "SYMBOL_CHANGED_SAME_SECURITY"}
        else ""
    )
    return {
        "resultState": result_state,
        "successorSymbol": successor,
        "quantityFactor": _number(quantity, default=quantity_default),
        "cashPerEntryShare": _number(row.get("cashPerEntryShare"), default="0"),
        "basket": _canonical_basket(row.get("basket")),
    }


def _schema_labels(row: dict[str, Any]) -> dict[str, str]:
    return {
        "resolutionDecision": str(row.get("resolutionDecision") or ""),
        "transformationKind": str(row.get("transformationKind") or ""),
    }


def _compatible(rows: list[dict[str, Any]]) -> bool:
    if len(rows) <= 1:
        return True
    first = _economic_fingerprint(rows[0])
    return all(_economic_fingerprint(row) == first for row in rows[1:])


def run(
    *,
    unresolved_scope_path: Path,
    b1_contract_path: Path,
    b3_contract_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    scope = json.loads(unresolved_scope_path.read_text(encoding="utf-8"))
    b1 = json.loads(b1_contract_path.read_text(encoding="utf-8"))
    b3 = json.loads(b3_contract_path.read_text(encoding="utf-8"))
    for payload, name in ((scope, "scope"), (b1, "B1"), (b3, "B3")):
        _assert_safe(payload, name)

    required_scope = {
        "status": "PHASE1_FEATURE_TOURNAMENT_STAGE_B_UNRESOLVED_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "unresolvedRows": EXPECTED_SCOPE_ROWS,
        "resolutionComplete": False,
        "featureDiscoveryOutcomesOpened": False,
    }
    for key, expected in required_scope.items():
        if scope.get(key) != expected:
            raise ValueError(f"unresolved scope mismatch: {key}")
    scope_rows = scope.get("rows")
    if not isinstance(scope_rows, list) or len(scope_rows) != EXPECTED_SCOPE_ROWS:
        raise ValueError("invalid unresolved scope rows")

    b1_rows = _normalize_b1(b1)
    b3_rows = _normalize_b3(b3)
    prior: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for source_name, rows in (("B1", b1_rows), ("B3", b3_rows)):
        for row in rows:
            for field in ("evaluationSession", "entrySession", "targetExitSession"):
                _assert_date(row[field], field)
            annotated = dict(row)
            annotated["_priorSource"] = source_name
            prior[_semantic_key(annotated)].append(annotated)

    results: list[dict[str, Any]] = []
    source_hits: Counter[str] = Counter()
    source_combos: Counter[str] = Counter()
    safe_rows = conflict_rows = unmatched_rows = 0
    schema_label_difference_rows = 0

    for row in scope_rows:
        for field in ("evaluationSession", "entrySession", "targetExitSession"):
            _assert_date(row[field], field)
        matches = prior.get(_semantic_key(row), [])
        sources = sorted({str(match["_priorSource"]) for match in matches})
        for source in sources:
            source_hits[source] += 1
        source_combos["+".join(sources) if sources else "NONE"] += 1

        labels = {
            json.dumps(_schema_labels(match), sort_keys=True)
            for match in matches
        }
        if len(labels) > 1:
            schema_label_difference_rows += 1

        compatible = bool(matches) and _compatible(matches)
        if compatible:
            safe_rows += 1
            status = "SAFE_PRIOR_ECONOMIC_MATCH"
        elif matches:
            conflict_rows += 1
            status = "PRIOR_ECONOMIC_CONFLICT"
        else:
            unmatched_rows += 1
            status = "NO_PRIOR_EVIDENCE_MATCH"

        results.append(
            {
                **_key_object(row),
                "currentEventNumber": int(row["eventNumber"]),
                "currentResolutionSource": str(row.get("resolutionSource") or ""),
                "matchStatus": status,
                "priorSources": sources,
                "priorMatches": [
                    {
                        "source": match["_priorSource"],
                        "priorEventNumber": int(match["eventNumber"]),
                        "economicFingerprint": _economic_fingerprint(match),
                        "schemaLabels": _schema_labels(match),
                    }
                    for match in matches
                ],
            }
        )

    if safe_rows + conflict_rows + unmatched_rows != EXPECTED_SCOPE_ROWS:
        raise ValueError("overlap partition does not cover frozen scope")

    safe_match_rows = [
        row for row in results if row["matchStatus"] == "SAFE_PRIOR_ECONOMIC_MATCH"
    ]
    payload = {
        "schemaVersion": "2.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_PRIOR_CONTINUITY_OVERLAP_V2_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": EXPECTED_SCOPE_ROWS,
        "sourceScopeKeySha256": scope["scopeKeySha256"],
        "sourceHitRows": dict(sorted(source_hits.items())),
        "sourceCombinationRows": dict(sorted(source_combos.items())),
        "safeReusableRows": safe_rows,
        "conflictingPriorRows": conflict_rows,
        "unmatchedRows": unmatched_rows,
        "schemaLabelDifferenceRows": schema_label_difference_rows,
        "safeReusableSemanticKeySha256": _key_digest(safe_match_rows),
        "rows": results,
        "resolutionApplied": False,
        "featureDiscoveryOutcomesOpened": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unresolved-scope", type=Path, required=True)
    parser.add_argument("--b1-contract", type=Path, required=True)
    parser.add_argument("--b3-contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        unresolved_scope_path=args.unresolved_scope,
        b1_contract_path=args.b1_contract,
        b3_contract_path=args.b3_contract,
        output_path=args.output,
    )
    compact = {key: value for key, value in result.items() if key != "rows"}
    print(json.dumps(compact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
