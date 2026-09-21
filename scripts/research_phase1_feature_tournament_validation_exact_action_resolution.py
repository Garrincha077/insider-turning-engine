"""Resolve the 8 frozen F2 validation exact-action prior-evidence rows."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_ROWS = 41
EXPECTED_RESOLVED_ROWS = 8
EXPECTED_REMAINING_ROWS = 33
EXPECTED_KEY_DIGEST = (
    "sha256:fbd00d6952afad146499ae0cc998c1c79bee8ab15084eae4bdd45899bab8cb34"
)
CATEGORY = "PROVIDER_EXACT_ACTION_PRIOR_CANDIDATE"

KEY_FIELDS = (
    "issuerCik",
    "ticker",
    "evaluationSession",
    "entrySession",
    "horizon",
    "targetExitSession",
)


def _number(value: object, *, default: str = "") -> str:
    if value in (None, ""):
        return default
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"invalid numeric holder term: {value}") from None
    if not number.is_finite():
        raise ValueError("non-finite holder term")
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


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


def _basket(value: object) -> list[dict[str, str]]:
    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise ValueError("invalid frozen basket")
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise ValueError("invalid frozen basket item")
        symbol, security_class, quantity = item
        result.append(
            {
                "symbol": str(symbol).upper(),
                "securityClass": str(security_class),
                "quantityPerEntryUnit": _number(quantity),
            }
        )
    return sorted(
        result,
        key=lambda row: (
            row["symbol"],
            row["securityClass"],
            row["quantityPerEntryUnit"],
        ),
    )


def _assert_source(payload: dict[str, Any]) -> list[dict[str, Any]]:
    required = {
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "PRIOR_EVIDENCE_AUDIT_COMPLETE"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": EXPECTED_SOURCE_ROWS,
        "auditedRows": EXPECTED_SOURCE_ROWS,
        "resolutionApplied": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"prior-evidence audit mismatch: {key}")

    expected_categories = {
        "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED": 10,
        "LONG_GAP_PRIOR_SECURITY_CANDIDATE": 1,
        "PROVIDER_EXACT_ACTION_PRIOR_CANDIDATE": 8,
        "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED": 22,
    }
    if payload.get("categoryCounts") != expected_categories:
        raise ValueError("prior-evidence category partition changed")

    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_SOURCE_ROWS:
        raise ValueError("prior-evidence row count changed")
    return [dict(row) for row in rows]


def _resolution(row: dict[str, Any]) -> dict[str, Any]:
    evidence = row.get("evidenceAudit")
    if not isinstance(evidence, dict) or evidence.get("category") != CATEGORY:
        raise ValueError("non-exact-action row passed to resolver")

    action_ids = sorted(str(item) for item in row.get("candidateActionIds") or [])
    if not action_ids:
        raise ValueError("exact-action candidate has no action IDs")

    labels = evidence.get("schemaLabels")
    if not isinstance(labels, list) or len(labels) != 1:
        raise ValueError("exact-action candidate lacks singular schema labels")
    label = labels[0]
    if not isinstance(label, list) or len(label) != 2:
        raise ValueError("invalid schema-label pair")
    resolution_decision = str(label[0])
    transformation_kind = str(label[1])
    if not resolution_decision or not transformation_kind:
        raise ValueError("empty schema label")

    fp = evidence.get("economicFingerprint")
    if not isinstance(fp, list) or len(fp) != 5:
        raise ValueError("invalid frozen economic fingerprint")
    state = str(fp[0])
    successor = str(fp[1]).upper()
    quantity = _number(fp[2])
    cash = _number(fp[3], default="0")
    basket = _basket(fp[4])

    if not state:
        raise ValueError("empty result state")
    cash_number = Decimal(cash)
    if cash_number < 0:
        raise ValueError("negative cash holder term")

    if state == "SYMBOL_CHANGED_SAME_SECURITY":
        if not successor or Decimal(quantity) != Decimal("1") or basket:
            raise ValueError("invalid same-security symbol-change economics")
    elif state == "TRANSFORMED_HOLDER_CONSIDERATION":
        if successor:
            if not quantity or Decimal(quantity) <= 0:
                raise ValueError("invalid transformed successor quantity")
        elif cash_number <= 0 and not basket:
            raise ValueError("transformed holder row lacks consideration")
    else:
        raise ValueError(f"unexpected exact-action result state: {state}")

    effective = str(evidence.get("exampleEffectiveDate") or "")
    entry = str(row["entrySession"])
    target = str(row["targetExitSession"])
    if len(effective) != 10 or not (entry < effective <= target):
        raise ValueError("effective date outside validation horizon")

    prior_sources = evidence.get("priorSources")
    if not isinstance(prior_sources, list) or not prior_sources:
        raise ValueError("exact-action row lacks frozen prior sources")

    return {
        **_key_object(row),
        "expectedSourceResolutionSource": str(row.get("resolutionSource") or ""),
        "effectiveDate": effective,
        "resolutionDecision": resolution_decision,
        "transformationKind": transformation_kind,
        "resultState": state,
        "successorSymbol": successor,
        "successorSharesPerEntryShare": quantity,
        "cashPerEntryShare": cash,
        "sourceActionIds": action_ids,
        "basket": basket,
        "classificationSource": (
            "VALIDATION_EXACT_ACTION_PRIOR_EVIDENCE_REUSE"
        ),
        "evidenceClass": (
            "PRIOR_FROZEN_EXACT_ACTION_ECONOMIC_AGREEMENT"
        ),
        "priorEvidenceSources": sorted(str(item) for item in prior_sources),
        "priorMatchCount": int(evidence.get("priorMatchCount") or 0),
    }


def run(*, audit_path: Path, output_path: Path) -> dict[str, Any]:
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    rows = _assert_source(payload)
    candidates = [
        row
        for row in rows
        if (row.get("evidenceAudit") or {}).get("category") == CATEGORY
    ]
    if len(candidates) != EXPECTED_RESOLVED_ROWS:
        raise ValueError("exact-action candidate count changed")
    if _key_digest(candidates) != EXPECTED_KEY_DIGEST:
        raise ValueError("exact-action semantic-key digest changed")

    resolved = [_resolution(row) for row in candidates]
    if _key_digest(resolved) != EXPECTED_KEY_DIGEST:
        raise ValueError("resolved semantic keys changed")

    resolved.sort(key=lambda row: (int(row["eventNumber"]), int(row["horizon"])))
    result = {
        "schemaVersion": "1.0.0",
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "EXACT_ACTION_PRIOR_RESOLUTION_COMPLETE"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": EXPECTED_SOURCE_ROWS,
        "eligibleExactActionRows": EXPECTED_RESOLVED_ROWS,
        "resolvedRows": len(resolved),
        "remainingUnresolvedRows": EXPECTED_REMAINING_ROWS,
        "resolvedKeySha256": EXPECTED_KEY_DIGEST,
        "resolutionRows": resolved,
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
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(audit_path=args.audit, output_path=args.output)
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key != "resolutionRows"
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
