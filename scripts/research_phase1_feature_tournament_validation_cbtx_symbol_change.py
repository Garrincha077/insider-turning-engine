"""Resolve the frozen CBTX -> STEL validation symbol-change row."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_ROWS = 11
EXPECTED_REMAINING_ROWS = 10
EXPECTED_SOURCE_DIGEST = (
    "sha256:46381d68c3ad51f9d6d9d7a934d88d807c599f78712f34d4e210c9f4248e5d55"
)
EXPECTED_TARGET_DIGEST = (
    "sha256:a8705b17cd9f57eab966148e2ecaef12126e7010698ee812090b26151bed0e75"
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


def _digest(rows: list[dict[str, Any]]) -> str:
    lines = sorted(
        json.dumps(_key_object(row), sort_keys=True, separators=(",", ":"))
        for row in rows
    )
    return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _assert_boundary(payload: dict[str, Any], label: str) -> None:
    required = {
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"{label} boundary mismatch: {key}")


def _load_scope(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _assert_boundary(payload, "residual-11")
    if payload.get("status") != (
        "PHASE1_FEATURE_TOURNAMENT_VALIDATION_RESIDUAL11_SCOPE_FROZEN"
    ):
        raise ValueError("residual-11 status changed")
    if payload.get("residualRows") != EXPECTED_SOURCE_ROWS:
        raise ValueError("residual-11 row count changed")
    if payload.get("scopeKeySha256") != EXPECTED_SOURCE_DIGEST:
        raise ValueError("residual-11 scope digest changed")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_SOURCE_ROWS:
        raise ValueError("residual-11 rows changed")
    if _digest(rows) != EXPECTED_SOURCE_DIGEST:
        raise ValueError("residual-11 semantic keys changed")
    return payload


def _load_evidence(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _assert_boundary(payload, "CBTX evidence")
    required = {
        "contractId": (
            "phase1-feature-tournament-validation-"
            "cbtx-symbol-change-primary-evidence-v1"
        ),
        "sourceResidualAssetDigest": (
            "sha256:9f240f9c4fd4f565449ef5261d6a696bc70beb9725213f4a7c5f73d01781915d"
        ),
        "targetKeySha256": EXPECTED_TARGET_DIGEST,
        "resolutionApplied": False,
        "validationPerformanceOpened": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"CBTX evidence mismatch: {key}")
    rows = payload.get("evidence")
    if not isinstance(rows, list) or len(rows) != 1:
        raise ValueError("CBTX evidence row count changed")
    if _digest(rows) != EXPECTED_TARGET_DIGEST:
        raise ValueError("CBTX evidence key changed")
    return dict(rows[0])


def _resolution(row: dict[str, Any], fact: dict[str, Any]) -> dict[str, Any]:
    if _key_object(row) != _key_object(fact):
        raise ValueError("CBTX semantic key changed")
    if row.get("candidateActionTypes") != ["name_changes"]:
        raise ValueError("CBTX action type changed")
    if row.get("candidateActionIds") != [str(fact["actionId"])]:
        raise ValueError("CBTX action ID changed")
    if str(row.get("resolutionSource") or "") != "provider":
        raise ValueError("CBTX source classification changed")
    category = str((row.get("evidenceAudit") or {}).get("category") or "")
    if category != "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED":
        raise ValueError("CBTX evidence category changed")

    effective = str(fact["effectiveDate"])
    if not str(row["entrySession"]) < effective <= str(row["targetExitSession"]):
        raise ValueError("CBTX effective date outside event horizon")
    if fact["resolutionDecision"] != "SYMBOL_CHANGED_SAME_SECURITY":
        raise ValueError("CBTX decision changed")
    if fact["transformationKind"] != "SAME_SECURITY_SYMBOL_CHANGE":
        raise ValueError("CBTX transformation kind changed")
    if fact["resultState"] != "SYMBOL_CHANGED_SAME_SECURITY":
        raise ValueError("CBTX result state changed")
    if str(fact["successorSymbol"]).upper() != "STEL":
        raise ValueError("CBTX successor changed")
    if Decimal(str(fact["successorSharesPerEntryShare"])) != Decimal("1"):
        raise ValueError("CBTX share quantity changed")
    if Decimal(str(fact["cashPerEntryShare"])) != 0:
        raise ValueError("CBTX cash term changed")
    if not fact.get("primaryEvidence"):
        raise ValueError("CBTX primary evidence missing")

    return {
        **_key_object(row),
        "expectedSourceResolutionSource": "provider",
        "effectiveDate": effective,
        "resolutionDecision": "SYMBOL_CHANGED_SAME_SECURITY",
        "transformationKind": "SAME_SECURITY_SYMBOL_CHANGE",
        "resultState": "SYMBOL_CHANGED_SAME_SECURITY",
        "successorSymbol": "STEL",
        "successorSharesPerEntryShare": "1",
        "cashPerEntryShare": "0",
        "sourceActionIds": [str(fact["actionId"])],
        "basket": [],
        "classificationSource": "VALIDATION_PRIMARY_CBTX_STEL_SYMBOL_CHANGE",
        "evidenceClass": "PRIMARY_SEC_SURVIVING_CORPORATION_SYMBOL_CHANGE",
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
    fact = _load_evidence(evidence_path)
    rows = scope["rows"]
    targets = [
        row
        for row in rows
        if row["ticker"] == "CBTX"
        and row.get("candidateActionTypes") == ["name_changes"]
    ]
    if len(targets) != 1:
        raise ValueError("CBTX target count changed")
    if _digest(targets) != EXPECTED_TARGET_DIGEST:
        raise ValueError("CBTX target key changed")

    resolution = _resolution(targets[0], fact)
    result = {
        "schemaVersion": "1.0.0",
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "CBTX_SYMBOL_CHANGE_RESOLUTION_COMPLETE"
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
        "resolvedRows": 1,
        "remainingUnresolvedRows": EXPECTED_REMAINING_ROWS,
        "resolvedKeySha256": EXPECTED_TARGET_DIGEST,
        "resolutionRows": [resolution],
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
    compact = {key: value for key, value in result.items() if key != "resolutionRows"}
    print(json.dumps(compact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
