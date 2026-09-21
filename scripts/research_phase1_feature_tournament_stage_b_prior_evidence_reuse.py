"""Reuse prior frozen B1/B3 continuity evidence on the exact Stage-B residual scope.

This stage is deliberately performance-blind. It matches only the full historical
identity/event-horizon key and never reads forward returns, SPY excess returns,
MAE, feature outcomes, validation outcomes, or sealed 2023+ data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

EXPECTED_SCOPE_ROWS = 210
EXPECTED_B3_EXACT_MATCHES = 168
EXPECTED_B1_ONLY_EXACT_MATCHES = 8
EXPECTED_REUSED_ROWS = 176
EXPECTED_RESIDUAL_ROWS = 34
SEALED_YEAR = 2023

KEY_FIELDS = (
    "issuerCik",
    "ticker",
    "evaluationSession",
    "entrySession",
    "horizon",
    "targetExitSession",
)
PERFORMANCE_PREFIXES = ("raw_", "excess_", "mae_")


def _key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row[field]) for field in KEY_FIELDS)


def _digest(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> str:
    payload = [
        {field: row[field] for field in fields}
        for row in rows
    ]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _assert_performance_blind_row(row: dict[str, Any]) -> None:
    forbidden = [
        key
        for key in row
        if str(key).lower().startswith(PERFORMANCE_PREFIXES)
    ]
    if forbidden:
        raise ValueError(f"performance fields are forbidden: {forbidden}")


def _assert_pre_oos(row: dict[str, Any]) -> None:
    for field in ("evaluationSession", "entrySession", "targetExitSession"):
        value = str(row.get(field) or "")
        if value and int(value[:4]) >= SEALED_YEAR:
            raise ValueError(f"sealed OOS boundary violated by {field}={value}")


def _decimal_text(value: Any, *, default: str = "0") -> str:
    if value is None or value == "":
        value = default
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid numeric continuity term: {value}") from exc
    text = format(number.normalize(), "f")
    return "0" if text in {"-0", ""} else text


def _load_scope(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
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
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"unresolved scope contract mismatch: {key}")

    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_SCOPE_ROWS:
        raise ValueError("unresolved scope row count changed")

    seen: set[tuple[str, ...]] = set()
    for row in rows:
        _assert_performance_blind_row(row)
        _assert_pre_oos(row)
        key = _key(row)
        if key in seen:
            raise ValueError("duplicate unresolved historical key")
        seen.add(key)
    return payload


def _load_b3(path: Path) -> dict[tuple[str, ...], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "classifiedRows": 264,
        "finalResolutionContractCreated": True,
        "correctedPerformanceOpened": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"B3 final continuity contract mismatch: {key}")

    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != 264:
        raise ValueError("B3 final continuity resolutionRows changed")

    index: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        _assert_performance_blind_row(row)
        _assert_pre_oos(row)
        key = _key(row)
        if key in index:
            raise ValueError("duplicate B3 continuity historical key")
        index[key] = row
    return index


def _load_b1(path: Path) -> dict[tuple[str, ...], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contractId") != "phase1-b1-security-continuity-resolution-v1":
        raise ValueError("unexpected B1 continuity contract")
    if payload.get("researchOnly") is not True:
        raise ValueError("B1 contract is not research-only")
    if payload.get("performanceRead") is not False:
        raise ValueError("B1 contract opened performance")
    if payload.get("oosOpened") is not False:
        raise ValueError("B1 contract opened OOS")
    if payload.get("productionScoringChanged") is not False:
        raise ValueError("B1 contract changed production scoring")

    columns = payload.get("resolutionColumns")
    raw_rows = payload.get("resolutions")
    if not isinstance(columns, list) or not isinstance(raw_rows, list):
        raise ValueError("malformed B1 resolution table")
    expected = int(payload.get("frozenScope", {}).get("expectedSourceUnresolvedRows", -1))
    if expected != 54 or len(raw_rows) != 54:
        raise ValueError("B1 frozen resolution row count changed")

    index: dict[tuple[str, ...], dict[str, Any]] = {}
    for values in raw_rows:
        if len(values) != len(columns):
            raise ValueError("malformed B1 resolution row")
        row = dict(zip(columns, values))
        _assert_performance_blind_row(row)
        _assert_pre_oos(row)
        key = _key(row)
        if key in index:
            raise ValueError("duplicate B1 continuity historical key")
        index[key] = row
    return index


def _normalized_resolution(
    scope_row: dict[str, Any],
    evidence_row: dict[str, Any],
    *,
    source: str,
) -> dict[str, Any]:
    if str(evidence_row.get("expectedSourceResolutionSource") or "") != str(
        scope_row.get("resolutionSource") or ""
    ):
        raise ValueError("prior evidence resolutionSource mismatch")

    if source == "B3_FINAL_CONTINUITY_CONTRACT":
        share_factor = evidence_row.get("successorSharesPerEntryShare", 1)
        cash = evidence_row.get("cashPerEntryShare", 0)
        classification_source = evidence_row.get("classificationSource", "")
        classification_release = evidence_row.get("classificationSourceRelease", "")
        evidence_class = evidence_row.get("evidenceClass", "")
        prior_event = evidence_row.get("eventNumber")
    elif source == "B1_FROZEN_CONTINUITY_RESOLUTION":
        share_factor = evidence_row.get("shareQuantityFactor", 1)
        cash = 0
        classification_source = "b1_frozen_resolution_contract"
        classification_release = "research/b1-security-continuity-resolution-v1.json"
        evidence_class = "PRIOR_FROZEN_B1_CONTINUITY_EVIDENCE"
        prior_event = evidence_row.get("eventNumber")
    else:
        raise ValueError(f"unknown prior evidence source: {source}")

    return {
        "eventNumber": int(scope_row["eventNumber"]),
        "issuerCik": str(scope_row["issuerCik"]),
        "ticker": str(scope_row["ticker"]).upper(),
        "evaluationSession": str(scope_row["evaluationSession"]),
        "entrySession": str(scope_row["entrySession"]),
        "horizon": int(scope_row["horizon"]),
        "targetExitSession": str(scope_row["targetExitSession"]),
        "expectedSourceResolutionSource": str(scope_row["resolutionSource"]),
        "resolutionDecision": str(evidence_row.get("resolutionDecision") or ""),
        "resultState": str(evidence_row.get("resultState") or ""),
        "effectiveDate": str(evidence_row.get("effectiveDate") or ""),
        "successorSymbol": str(evidence_row.get("successorSymbol") or "").upper(),
        "successorSharesPerEntryShare": _decimal_text(share_factor, default="1"),
        "cashPerEntryShare": _decimal_text(cash, default="0"),
        "transformationKind": str(evidence_row.get("transformationKind") or ""),
        "sourceActionIds": list(evidence_row.get("sourceActionIds") or []),
        "reuseSource": source,
        "priorEvidenceEventNumber": int(prior_event) if prior_event not in (None, "") else None,
        "classificationSource": str(classification_source),
        "classificationSourceRelease": str(classification_release),
        "evidenceClass": str(evidence_class),
    }


def _semantic_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["resolutionDecision"],
        row["resultState"],
        row["successorSymbol"],
        row["successorSharesPerEntryShare"],
        row["cashPerEntryShare"],
        row["transformationKind"],
    )


def run(
    *,
    scope_path: Path,
    b3_contract_path: Path,
    b1_contract_path: Path,
    reuse_output: Path,
    residual_output: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    scope_payload = _load_scope(scope_path)
    scope_rows = scope_payload["rows"]
    b3_index = _load_b3(b3_contract_path)
    b1_index = _load_b1(b1_contract_path)

    reused: list[dict[str, Any]] = []
    residual: list[dict[str, Any]] = []
    b3_matches = 0
    b1_only_matches = 0

    for scope_row in scope_rows:
        key = _key(scope_row)
        b3_row = b3_index.get(key)
        b1_row = b1_index.get(key)

        if b3_row is not None and b1_row is not None:
            b3_norm = _normalized_resolution(
                scope_row,
                b3_row,
                source="B3_FINAL_CONTINUITY_CONTRACT",
            )
            b1_norm = _normalized_resolution(
                scope_row,
                b1_row,
                source="B1_FROZEN_CONTINUITY_RESOLUTION",
            )
            if _semantic_signature(b3_norm) != _semantic_signature(b1_norm):
                raise ValueError("B1/B3 prior evidence semantic conflict on exact key")
            reused.append(b3_norm)
            b3_matches += 1
        elif b3_row is not None:
            reused.append(
                _normalized_resolution(
                    scope_row,
                    b3_row,
                    source="B3_FINAL_CONTINUITY_CONTRACT",
                )
            )
            b3_matches += 1
        elif b1_row is not None:
            reused.append(
                _normalized_resolution(
                    scope_row,
                    b1_row,
                    source="B1_FROZEN_CONTINUITY_RESOLUTION",
                )
            )
            b1_only_matches += 1
        else:
            residual.append(dict(scope_row))

    reused.sort(key=lambda row: (row["eventNumber"], row["horizon"]))
    residual.sort(key=lambda row: (int(row["eventNumber"]), int(row["horizon"])))

    observed = (
        b3_matches,
        b1_only_matches,
        len(reused),
        len(residual),
    )
    expected = (
        EXPECTED_B3_EXACT_MATCHES,
        EXPECTED_B1_ONLY_EXACT_MATCHES,
        EXPECTED_REUSED_ROWS,
        EXPECTED_RESIDUAL_ROWS,
    )
    if observed != expected:
        raise ValueError(f"prior-evidence overlap changed: {observed} != {expected}")

    decisions = Counter(row["resolutionDecision"] for row in reused)
    reuse_sources = Counter(row["reuseSource"] for row in reused)
    residual_sources = Counter(str(row["resolutionSource"]) for row in residual)
    residual_horizons = Counter(str(row["horizon"]) for row in residual)

    key_fields = ("eventNumber",) + KEY_FIELDS
    reuse_payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_STAGE_B_PRIOR_EVIDENCE_REUSE_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": EXPECTED_SCOPE_ROWS,
        "b3ExactMatches": b3_matches,
        "b1OnlyExactMatches": b1_only_matches,
        "reusedRows": len(reused),
        "residualRows": len(residual),
        "rowsByReuseSource": dict(sorted(reuse_sources.items())),
        "resolutionDecisionCounts": dict(sorted(decisions.items())),
        "reuseKeySha256": _digest(reused, key_fields),
        "rows": reused,
        "resolutionComplete": False,
        "featureDiscoveryOutcomesOpened": False,
    }

    residual_key_fields = (
        "eventNumber",
        "issuerCik",
        "ticker",
        "evaluationSession",
        "entrySession",
        "horizon",
        "targetExitSession",
    )
    residual_payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_STAGE_B_RESIDUAL_PRIMARY_EVIDENCE_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": EXPECTED_SCOPE_ROWS,
        "priorEvidenceReusedRows": len(reused),
        "residualRows": len(residual),
        "residualUniqueEvents": len({int(row["eventNumber"]) for row in residual}),
        "residualUniqueIssuers": len({str(row["issuerCik"]) for row in residual}),
        "residualUniqueTickers": len({str(row["ticker"]) for row in residual}),
        "rowsByResolutionSource": dict(sorted(residual_sources.items())),
        "rowsByHorizon": dict(sorted(residual_horizons.items())),
        "residualScopeKeySha256": _digest(residual, residual_key_fields),
        "rows": residual,
        "resolutionComplete": False,
        "featureDiscoveryOutcomesOpened": False,
    }

    reuse_output.parent.mkdir(parents=True, exist_ok=True)
    residual_output.parent.mkdir(parents=True, exist_ok=True)
    reuse_output.write_text(
        json.dumps(reuse_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    residual_output.write_text(
        json.dumps(residual_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return reuse_payload, residual_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--b3-contract", type=Path, required=True)
    parser.add_argument("--b1-contract", type=Path, required=True)
    parser.add_argument("--reuse-output", type=Path, required=True)
    parser.add_argument("--residual-output", type=Path, required=True)
    args = parser.parse_args()
    reuse, residual = run(
        scope_path=args.scope,
        b3_contract_path=args.b3_contract,
        b1_contract_path=args.b1_contract,
        reuse_output=args.reuse_output,
        residual_output=args.residual_output,
    )
    compact = {
        "reuse": {k: v for k, v in reuse.items() if k != "rows"},
        "residual": {k: v for k, v in residual.items() if k != "rows"},
    }
    print(json.dumps(compact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
