"""Resolve eight F2 validation incomplete stock-merger rows from frozen SEC evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_ROWS = 27
EXPECTED_TARGET_ROWS = 8
EXPECTED_REMAINING_ROWS = 19
EXPECTED_SOURCE_DIGEST = (
    "sha256:683086e2a4ba61f734b45a22a24371f3f2a5ffa0f1fd74e7e9576275ab32da9f"
)
EXPECTED_TARGET_DIGEST = (
    "sha256:31296aeae352b58fc55a6eba4cbfaf2fa0d600134a004afcf6c7980782a5b776"
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
        json.dumps(_key_object(row), sort_keys=True, separators=(",", ":"))
        for row in rows
    )
    return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _number(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"invalid numeric value: {value}") from None
    if not result.is_finite():
        raise ValueError("non-finite numeric value")
    return result


def _format(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _load_scope(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "RESIDUAL27_SCOPE_FROZEN"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "residualRows": EXPECTED_SOURCE_ROWS,
        "scopeKeySha256": EXPECTED_SOURCE_DIGEST,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"residual-27 mismatch: {key}")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_SOURCE_ROWS:
        raise ValueError("residual-27 rows changed")
    if _key_digest(rows) != EXPECTED_SOURCE_DIGEST:
        raise ValueError("residual-27 semantic-key set changed")
    return [dict(row) for row in rows]


def _load_evidence(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "contractId": (
            "phase1-feature-tournament-validation-"
            "incomplete-stock-merger-primary-evidence-v1"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualAssetDigest": (
            "sha256:04b4e2280e9059aed8c10f9a6d9ac1853f23f34f5028dba6482c014c1ff190a4"
        ),
        "expectedRows": EXPECTED_TARGET_ROWS,
        "expectedActions": 5,
        "expectedKeySha256": EXPECTED_TARGET_DIGEST,
        "resolutionApplied": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"incomplete-merger evidence mismatch: {key}")

    rows = payload.get("evidence")
    if not isinstance(rows, list) or len(rows) != 5:
        raise ValueError("incomplete-merger evidence action count changed")

    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        action_id = str(row.get("actionId") or "")
        if not action_id or action_id in result:
            raise ValueError("duplicate or empty incomplete-merger action ID")
        if not row.get("primaryEvidence"):
            raise ValueError("primary SEC evidence missing")
        result[action_id] = dict(row)
    return result


def _resolution(
    row: dict[str, Any],
    fact: dict[str, Any],
) -> dict[str, Any]:
    ids = [str(item) for item in row.get("candidateActionIds") or []]
    if ids != [str(fact["actionId"])]:
        raise ValueError("incomplete-merger source action identity changed")
    if row.get("candidateActionTypes") != ["stock_mergers"]:
        raise ValueError("incomplete-merger source action type changed")
    if str(row.get("resolutionSource") or "") != "provider_incomplete_terms":
        raise ValueError("incomplete-merger source classification changed")
    category = str((row.get("evidenceAudit") or {}).get("category") or "")
    if category != "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED":
        raise ValueError("incomplete-merger evidence category changed")

    if str(row["issuerCik"]) != str(fact["issuerCik"]):
        raise ValueError("incomplete-merger issuer changed")
    if str(row["ticker"]).upper() != str(fact["ticker"]).upper():
        raise ValueError("incomplete-merger historical ticker changed")

    effective = str(fact["effectiveDate"])
    if not str(row["entrySession"]) < effective <= str(row["targetExitSession"]):
        raise ValueError("incomplete-merger effective date outside event horizon")

    if fact["resolutionDecision"] != "TRANSFORMED_HOLDER_CONSIDERATION":
        raise ValueError("incomplete-merger decision changed")
    if fact["resultState"] != "TRANSFORMED_HOLDER_CONSIDERATION":
        raise ValueError("incomplete-merger result state changed")

    transformation = str(fact["transformationKind"])
    if transformation not in {
        "PRIMARY_SEC_STOCK_MERGER",
        "PRIMARY_SEC_SAME_SYMBOL_REORGANIZATION",
    }:
        raise ValueError("unexpected incomplete-merger transformation kind")

    successor = str(fact["successorSymbol"]).upper()
    quantity = _number(fact["successorSharesPerEntryShare"])
    cash = _number(fact["cashPerEntryShare"])
    if not successor or quantity <= 0 or cash != 0:
        raise ValueError("incomplete or invalid holder economics")

    ticker = str(row["ticker"]).upper()
    if transformation == "PRIMARY_SEC_SAME_SYMBOL_REORGANIZATION":
        if successor != ticker or quantity != Decimal("1"):
            raise ValueError("same-symbol reorganization economics changed")
    elif ticker == "SPRT":
        if successor != "GREE" or quantity != Decimal("0.115"):
            raise ValueError("SPRT merger economics changed")

    return {
        **_key_object(row),
        "expectedSourceResolutionSource": "provider_incomplete_terms",
        "effectiveDate": effective,
        "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
        "transformationKind": transformation,
        "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol": successor,
        "successorSharesPerEntryShare": _format(quantity),
        "cashPerEntryShare": "0",
        "sourceActionIds": [str(fact["actionId"])],
        "basket": [],
        "classificationSource": (
            "VALIDATION_PRIMARY_INCOMPLETE_STOCK_MERGER_TERMS"
        ),
        "evidenceClass": "PRIMARY_SEC_COMPLETE_HOLDER_EXCHANGE_TERMS",
        "primaryEvidenceAccessions": [
            str(item["accession"]) for item in fact["primaryEvidence"]
        ],
    }


def run(
    *,
    scope_path: Path,
    evidence_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    scope = _load_scope(scope_path)
    evidence = _load_evidence(evidence_path)

    targets = [
        row
        for row in scope
        if str(row.get("resolutionSource") or "") == "provider_incomplete_terms"
        and row.get("candidateActionTypes") == ["stock_mergers"]
    ]
    if len(targets) != EXPECTED_TARGET_ROWS:
        raise ValueError("incomplete-merger target row count changed")
    if _key_digest(targets) != EXPECTED_TARGET_DIGEST:
        raise ValueError("incomplete-merger target key digest changed")

    action_ids = {
        str(row["candidateActionIds"][0])
        for row in targets
        if len(row.get("candidateActionIds") or []) == 1
    }
    if action_ids != set(evidence):
        raise ValueError("incomplete-merger action set changed")

    resolutions = []
    for row in targets:
        ids = row.get("candidateActionIds") or []
        if len(ids) != 1:
            raise ValueError("incomplete-merger row does not have exactly one action")
        resolutions.append(_resolution(row, evidence[str(ids[0])]))

    resolutions.sort(key=lambda row: (int(row["eventNumber"]), int(row["horizon"])))
    if _key_digest(resolutions) != EXPECTED_TARGET_DIGEST:
        raise ValueError("resolved incomplete-merger keys changed")

    result = {
        "schemaVersion": "1.0.0",
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "INCOMPLETE_STOCK_MERGER_PRIMARY_RESOLUTION_COMPLETE"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": EXPECTED_SOURCE_ROWS,
        "resolvedRows": len(resolutions),
        "remainingUnresolvedRows": EXPECTED_REMAINING_ROWS,
        "resolvedKeySha256": EXPECTED_TARGET_DIGEST,
        "resolutionRows": resolutions,
        "resolutionApplied": True,
        "resolutionComplete": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        scope_path=args.scope,
        evidence_path=args.evidence,
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
