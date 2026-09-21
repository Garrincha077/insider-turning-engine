"""Merge every frozen Stage-B continuity resolution into one 210-row contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

EXPECTED_ROWS = 210
EXPECTED_SAFE = 175
EXPECTED_POPE = 1
EXPECTED_PROVIDER = 17
EXPECTED_LONG_GAP = 7
EXPECTED_FINAL10 = 10

SEMANTIC_FIELDS = (
    "issuerCik",
    "ticker",
    "evaluationSession",
    "entrySession",
    "horizon",
    "targetExitSession",
)


def _semantic_key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row[field]) for field in SEMANTIC_FIELDS)


def _current_key(row: dict[str, Any], event_field: str) -> tuple[str, ...]:
    return (str(row[event_field]), *_semantic_key(row))


def _number(value: Any, *, default: str = "") -> str:
    if value in (None, ""):
        return default
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def _canonical_basket(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("invalid basket item")
        rows.append(
            {
                "symbol": str(item.get("symbol") or "").upper(),
                "securityClass": str(item.get("securityClass") or ""),
                "quantity": _number(
                    item.get("quantityPerEntryUnit", item.get("quantity"))
                ),
            }
        )
    return sorted(
        rows,
        key=lambda item: (
            item["symbol"],
            item["securityClass"],
            item["quantity"],
        ),
    )


def _fingerprint(row: dict[str, Any]) -> dict[str, Any]:
    state = str(row.get("resultState") or "")
    quantity = row.get("shareQuantityFactor")
    if quantity in (None, ""):
        quantity = row.get("successorSharesPerEntryShare")
    default = (
        "1"
        if state in {"PRICE_CONTINUOUS_ADJUSTED", "SYMBOL_CHANGED_SAME_SECURITY"}
        else ""
    )
    return {
        "resultState": state,
        "successorSymbol": str(row.get("successorSymbol") or "").upper(),
        "quantityFactor": _number(quantity, default=default),
        "cashPerEntryShare": _number(row.get("cashPerEntryShare"), default="0"),
        "basket": _canonical_basket(row.get("basket")),
    }


def _assert_boundary(payload: dict[str, Any], *, label: str) -> None:
    required = {
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"{label} boundary mismatch: {key}")
    if "featureOutcomesRead" in payload and payload["featureOutcomesRead"] is not False:
        raise ValueError(f"{label} opened feature outcomes")
    if "validationOpened" in payload and payload["validationOpened"] is not False:
        raise ValueError(f"{label} opened validation")
    if (
        "featureDiscoveryOutcomesOpened" in payload
        and payload["featureDiscoveryOutcomesOpened"] is not False
    ):
        raise ValueError(f"{label} opened discovery outcomes")


def _load_b1(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("contractId") != "phase1-b1-security-continuity-resolution-v1":
        raise ValueError("unexpected B1 contract")
    columns = payload.get("resolutionColumns")
    values = payload.get("resolutions")
    if not isinstance(columns, list) or not isinstance(values, list):
        raise ValueError("malformed B1 compact contract")
    rows = [
        dict(zip(columns, item, strict=True))
        for item in values
    ]
    if len(rows) != 54:
        raise ValueError("B1 resolution row count changed")
    return rows


def _load_b3(payload: dict[str, Any]) -> list[dict[str, Any]]:
    required = {
        "status": "B3_FINAL_CONTINUITY_CONTRACT_COMPLETE",
        "classifiedRows": 264,
        "unresolvedRows": 0,
        "finalResolutionContractCreated": True,
        "correctedPerformanceOpened": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"B3 contract mismatch: {key}")
    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != 264:
        raise ValueError("B3 resolution row count changed")
    return rows


def _source_index(
    rows: list[dict[str, Any]],
) -> dict[tuple[tuple[str, ...], int], dict[str, Any]]:
    result: dict[tuple[tuple[str, ...], int], dict[str, Any]] = {}
    for row in rows:
        key = (_semantic_key(row), int(row["eventNumber"]))
        if key in result:
            raise ValueError("duplicate prior source key")
        result[key] = row
    return result


def _prior_resolution(
    overlap_row: dict[str, Any],
    b1_index: dict[tuple[tuple[str, ...], int], dict[str, Any]],
    b3_index: dict[tuple[tuple[str, ...], int], dict[str, Any]],
) -> dict[str, Any]:
    if overlap_row.get("matchStatus") != "SAFE_PRIOR_ECONOMIC_MATCH":
        raise ValueError("non-safe overlap row passed to prior resolver")

    matches = overlap_row.get("priorMatches")
    if not isinstance(matches, list) or not matches:
        raise ValueError("safe overlap row lacks prior matches")

    selected = next(
        (item for item in matches if item.get("source") == "B3"),
        None,
    )
    if selected is None:
        selected = next(
            (item for item in matches if item.get("source") == "B1"),
            None,
        )
    if selected is None:
        raise ValueError("safe overlap row has no recognized prior source")

    source = str(selected["source"])
    prior_event = int(selected["priorEventNumber"])
    lookup_key = (_semantic_key(overlap_row), prior_event)
    source_row = (
        b3_index.get(lookup_key)
        if source == "B3"
        else b1_index.get(lookup_key)
    )
    if source_row is None:
        raise ValueError("selected prior evidence row not found")

    expected_fp = selected.get("economicFingerprint")
    if not isinstance(expected_fp, dict) or _fingerprint(source_row) != expected_fp:
        raise ValueError("selected prior evidence fingerprint changed")

    labels = selected.get("schemaLabels")
    if not isinstance(labels, dict):
        raise ValueError("selected prior schema labels missing")
    if str(source_row.get("resolutionDecision") or "") != str(
        labels.get("resolutionDecision") or ""
    ):
        raise ValueError("selected prior decision label changed")
    if str(source_row.get("transformationKind") or "") != str(
        labels.get("transformationKind") or ""
    ):
        raise ValueError("selected prior transformation label changed")

    state = str(source_row.get("resultState") or "")
    quantity = source_row.get("shareQuantityFactor")
    if quantity in (None, ""):
        quantity = source_row.get("successorSharesPerEntryShare")
    quantity_default = (
        "1"
        if state in {"PRICE_CONTINUOUS_ADJUSTED", "SYMBOL_CHANGED_SAME_SECURITY"}
        else ""
    )

    out = {
        "eventNumber": int(overlap_row["currentEventNumber"]),
        "issuerCik": str(overlap_row["issuerCik"]),
        "ticker": str(overlap_row["ticker"]),
        "evaluationSession": str(overlap_row["evaluationSession"]),
        "entrySession": str(overlap_row["entrySession"]),
        "horizon": int(overlap_row["horizon"]),
        "targetExitSession": str(overlap_row["targetExitSession"]),
        "expectedSourceResolutionSource": str(
            overlap_row.get("currentResolutionSource") or ""
        ),
        "effectiveDate": str(source_row.get("effectiveDate") or ""),
        "resolutionDecision": str(source_row.get("resolutionDecision") or ""),
        "transformationKind": str(source_row.get("transformationKind") or ""),
        "resultState": state,
        "successorSymbol": str(source_row.get("successorSymbol") or ""),
        "successorSharesPerEntryShare": _number(
            quantity,
            default=quantity_default,
        ),
        "cashPerEntryShare": _number(
            source_row.get("cashPerEntryShare"),
            default="0",
        ),
        "sourceActionIds": list(source_row.get("sourceActionIds") or []),
        "basket": _canonical_basket(source_row.get("basket")),
        "classificationSource": "SAFE_PRIOR_EVIDENCE_REUSE",
        "priorEvidenceSource": source,
        "priorEvidenceEventNumber": prior_event,
    }
    if source == "B3":
        out["evidenceClass"] = str(source_row.get("evidenceClass") or "")
        out["priorClassificationSource"] = str(
            source_row.get("classificationSource") or ""
        )
        out["priorClassificationSourceRelease"] = str(
            source_row.get("classificationSourceRelease") or ""
        )
    else:
        out["evidenceClass"] = "PRIOR_FROZEN_B1_CONTINUITY_EVIDENCE"
        out["priorClassificationSourceRelease"] = (
            "research/b1-security-continuity-resolution-v1.json"
        )
    return out


def _digest_keys(rows: list[dict[str, Any]]) -> str:
    material = sorted(
        json.dumps(
            {
                "eventNumber": int(row["eventNumber"]),
                **{
                    field: (
                        int(row[field])
                        if field == "horizon"
                        else str(row[field])
                    )
                    for field in SEMANTIC_FIELDS
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in rows
    )
    return "sha256:" + hashlib.sha256("\n".join(material).encode()).hexdigest()


def _resolution_rows(
    payload: dict[str, Any],
    *,
    label: str,
    expected_count: int,
) -> list[dict[str, Any]]:
    _assert_boundary(payload, label=label)
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != expected_count:
        raise ValueError(f"{label} resolution row count changed")
    return [dict(row) for row in rows]


def run(
    *,
    scope_path: Path,
    overlap_path: Path,
    b1_path: Path,
    b3_path: Path,
    pope_path: Path,
    provider_path: Path,
    long_gap_path: Path,
    final10_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    overlap = json.loads(overlap_path.read_text(encoding="utf-8"))
    b1 = json.loads(b1_path.read_text(encoding="utf-8"))
    b3 = json.loads(b3_path.read_text(encoding="utf-8"))
    pope = json.loads(pope_path.read_text(encoding="utf-8"))
    provider = json.loads(provider_path.read_text(encoding="utf-8"))
    long_gap = json.loads(long_gap_path.read_text(encoding="utf-8"))
    final10 = json.loads(final10_path.read_text(encoding="utf-8"))

    for label, payload in (
        ("scope", scope),
        ("overlap", overlap),
        ("B1", b1),
        ("B3", b3),
        ("POPE", pope),
        ("provider17", provider),
        ("long-gap7", long_gap),
        ("final10", final10),
    ):
        _assert_boundary(payload, label=label)

    if scope.get("status") != (
        "PHASE1_FEATURE_TOURNAMENT_STAGE_B_UNRESOLVED_SCOPE_FROZEN"
    ):
        raise ValueError("unexpected Stage-B unresolved scope")
    if scope.get("unresolvedRows") != EXPECTED_ROWS:
        raise ValueError("Stage-B unresolved source count changed")
    scope_rows = scope.get("rows")
    if not isinstance(scope_rows, list) or len(scope_rows) != EXPECTED_ROWS:
        raise ValueError("Stage-B unresolved rows changed")

    if overlap.get("status") != (
        "PHASE1_FEATURE_TOURNAMENT_PRIOR_CONTINUITY_OVERLAP_V2_COMPLETE"
    ):
        raise ValueError("unexpected overlap status")
    if overlap.get("safeReusableRows") != EXPECTED_SAFE:
        raise ValueError("safe prior row count changed")
    if overlap.get("conflictingPriorRows") != 1:
        raise ValueError("overlap conflict count changed")
    if overlap.get("unmatchedRows") != 34:
        raise ValueError("overlap unmatched count changed")

    b1_rows = _load_b1(b1)
    b3_rows = _load_b3(b3)
    b1_index = _source_index(b1_rows)
    b3_index = _source_index(b3_rows)

    overlap_rows = overlap.get("rows")
    if not isinstance(overlap_rows, list) or len(overlap_rows) != EXPECTED_ROWS:
        raise ValueError("overlap rows changed")
    safe_overlap = [
        row
        for row in overlap_rows
        if row.get("matchStatus") == "SAFE_PRIOR_ECONOMIC_MATCH"
    ]
    if len(safe_overlap) != EXPECTED_SAFE:
        raise ValueError("safe overlap row count changed")
    safe_rows = [
        _prior_resolution(row, b1_index, b3_index)
        for row in safe_overlap
    ]

    if pope.get("status") != "PHASE1_FEATURE_TOURNAMENT_POPE_CONFLICT_ADJUDICATED":
        raise ValueError("POPE adjudication status changed")
    if pope.get("adjudicatedRows") != EXPECTED_POPE:
        raise ValueError("POPE adjudication row count changed")
    pope_resolution = pope.get("resolution")
    if not isinstance(pope_resolution, dict):
        raise ValueError("POPE resolution missing")
    pope_row = dict(pope_resolution)
    pope_row["classificationSource"] = "POPE_PRIMARY_EVIDENCE_ADJUDICATION"

    provider_rows = _resolution_rows(
        provider,
        label="provider17",
        expected_count=EXPECTED_PROVIDER,
    )
    long_gap_rows = _resolution_rows(
        long_gap,
        label="long-gap7",
        expected_count=EXPECTED_LONG_GAP,
    )
    final10_rows = _resolution_rows(
        final10,
        label="final10",
        expected_count=EXPECTED_FINAL10,
    )

    groups = [
        ("SAFE_PRIOR_EVIDENCE", safe_rows),
        ("POPE_ADJUDICATION", [pope_row]),
        ("PROVIDER17", provider_rows),
        ("LONG_GAP7", long_gap_rows),
        ("NEW_PRIMARY10", final10_rows),
    ]
    merged: list[dict[str, Any]] = []
    for name, rows in groups:
        for row in rows:
            item = dict(row)
            item.setdefault("classificationSource", name)
            merged.append(item)

    if len(merged) != EXPECTED_ROWS:
        raise ValueError("merged continuity row count is not 210")

    merged_keys = {
        _current_key(row, "eventNumber")
        for row in merged
    }
    if len(merged_keys) != EXPECTED_ROWS:
        raise ValueError("merged continuity contract contains duplicate keys")

    source_keys = {
        _current_key(row, "eventNumber")
        for row in scope_rows
    }
    if len(source_keys) != EXPECTED_ROWS:
        raise ValueError("source unresolved scope contains duplicate keys")
    if merged_keys != source_keys:
        missing = source_keys - merged_keys
        extra = merged_keys - source_keys
        raise ValueError(
            f"merged keys differ from source scope: missing={len(missing)} "
            f"extra={len(extra)}"
        )

    decisions = Counter(str(row.get("resolutionDecision") or "") for row in merged)
    states = Counter(str(row.get("resultState") or "") for row in merged)
    if "" in decisions or "" in states:
        raise ValueError("merged row lacks final decision/state")

    baskets = [
        row for row in merged
        if row.get("resolutionDecision") == (
            "TRANSFORMED_MULTI_COMPONENT_CONSIDERATION"
        )
    ]
    if len(baskets) != 1:
        raise ValueError("multi-component continuity row count changed")
    basket = _canonical_basket(baskets[0].get("basket"))
    if {item["symbol"] for item in basket} != {"MIMO", "MIMO WS"}:
        raise ValueError("multi-component basket was not preserved")

    group_counts = {name: len(rows) for name, rows in groups}
    if group_counts != {
        "SAFE_PRIOR_EVIDENCE": 175,
        "POPE_ADJUDICATION": 1,
        "PROVIDER17": 17,
        "LONG_GAP7": 7,
        "NEW_PRIMARY10": 10,
    }:
        raise ValueError("final source group partition changed")

    merged.sort(
        key=lambda row: (
            int(row["eventNumber"]),
            int(row["horizon"]),
        )
    )
    key_digest = _digest_keys(merged)
    payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_STAGE_B_FINAL_CONTINUITY_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": EXPECTED_ROWS,
        "classifiedRows": EXPECTED_ROWS,
        "unresolvedRows": 0,
        "sourceGroupCounts": group_counts,
        "resolutionDecisionCounts": dict(sorted(decisions.items())),
        "resultStateCounts": dict(sorted(states.items())),
        "classifiedKeySha256": key_digest,
        "sourceScopeKeySha256": str(scope.get("scopeKeySha256") or ""),
        "resolutionRows": merged,
        "resolutionComplete": True,
        "finalResolutionContractCreated": True,
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
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--overlap", type=Path, required=True)
    parser.add_argument("--b1", type=Path, required=True)
    parser.add_argument("--b3", type=Path, required=True)
    parser.add_argument("--pope", type=Path, required=True)
    parser.add_argument("--provider", type=Path, required=True)
    parser.add_argument("--long-gap", type=Path, required=True)
    parser.add_argument("--final10", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        scope_path=args.scope,
        overlap_path=args.overlap,
        b1_path=args.b1,
        b3_path=args.b3,
        pope_path=args.pope,
        provider_path=args.provider,
        long_gap_path=args.long_gap,
        final10_path=args.final10,
        output_path=args.output,
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "resolutionRows"},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
