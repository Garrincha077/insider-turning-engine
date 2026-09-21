"""Freeze the 33-row F2 validation residual continuity scope."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_AUDIT_ROWS = 41
EXPECTED_RESOLVED_ROWS = 8
EXPECTED_RESIDUAL_ROWS = 33
EXPECTED_RESOLVED_DIGEST = (
    "sha256:fbd00d6952afad146499ae0cc998c1c79bee8ab15084eae4bdd45899bab8cb34"
)
EXPECTED_RESIDUAL_DIGEST = (
    "sha256:9ee5091b18344e67b58fe567b92ce99d3f923e4df2829af935158947bdcae2a2"
)

KEY_FIELDS = (
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


def _key_tuple(row: dict[str, Any]) -> tuple[str, ...]:
    key = _key_object(row)
    return tuple(str(key[field]) for field in ("eventNumber", *KEY_FIELDS))


def _key_digest(rows: list[dict[str, Any]]) -> str:
    lines = sorted(
        json.dumps(_key_object(row), sort_keys=True, separators=(",", ":"))
        for row in rows
    )
    return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _assert_audit(payload: dict[str, Any]) -> list[dict[str, Any]]:
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
        "sourceUnresolvedRows": EXPECTED_AUDIT_ROWS,
        "auditedRows": EXPECTED_AUDIT_ROWS,
        "resolutionApplied": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"prior-evidence audit mismatch: {key}")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_AUDIT_ROWS:
        raise ValueError("prior-evidence audit rows changed")
    return [dict(row) for row in rows]


def _assert_resolution(payload: dict[str, Any]) -> list[dict[str, Any]]:
    required = {
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
        "sourceUnresolvedRows": EXPECTED_AUDIT_ROWS,
        "resolvedRows": EXPECTED_RESOLVED_ROWS,
        "remainingUnresolvedRows": EXPECTED_RESIDUAL_ROWS,
        "resolvedKeySha256": EXPECTED_RESOLVED_DIGEST,
        "resolutionApplied": True,
        "resolutionComplete": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"exact-action resolution mismatch: {key}")
    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_RESOLVED_ROWS:
        raise ValueError("exact-action resolution rows changed")
    if _key_digest(rows) != EXPECTED_RESOLVED_DIGEST:
        raise ValueError("exact-action resolution key digest changed")
    return [dict(row) for row in rows]


def run(
    *,
    audit_path: Path,
    resolution_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    resolution = json.loads(resolution_path.read_text(encoding="utf-8"))
    audit_rows = _assert_audit(audit)
    resolved_rows = _assert_resolution(resolution)

    audit_keys = {_key_tuple(row) for row in audit_rows}
    resolved_keys = {_key_tuple(row) for row in resolved_rows}
    if len(audit_keys) != EXPECTED_AUDIT_ROWS:
        raise ValueError("duplicate audit semantic keys")
    if len(resolved_keys) != EXPECTED_RESOLVED_ROWS:
        raise ValueError("duplicate resolved semantic keys")
    if not resolved_keys.issubset(audit_keys):
        raise ValueError("resolved keys are not a subset of audit keys")

    residual = [
        row
        for row in audit_rows
        if _key_tuple(row) not in resolved_keys
    ]
    if len(residual) != EXPECTED_RESIDUAL_ROWS:
        raise ValueError("residual row count changed")
    if _key_digest(residual) != EXPECTED_RESIDUAL_DIGEST:
        raise ValueError("residual semantic-key digest changed")

    categories = Counter(
        str((row.get("evidenceAudit") or {}).get("category") or "")
        for row in residual
    )
    expected_categories = {
        "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED": 10,
        "LONG_GAP_PRIOR_SECURITY_CANDIDATE": 1,
        "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED": 22,
    }
    if dict(sorted(categories.items())) != expected_categories:
        raise ValueError("residual category partition changed")

    hsd = [
        row
        for row in residual
        if (row.get("evidenceAudit") or {}).get("category")
        == "LONG_GAP_PRIOR_SECURITY_CANDIDATE"
    ]
    if len(hsd) != 1 or str(hsd[0]["ticker"]).upper() != "HSDT":
        raise ValueError("expected one HSDT prior-security long-gap candidate")

    residual.sort(key=lambda row: (int(row["eventNumber"]), int(row["horizon"])))
    result = {
        "schemaVersion": "1.0.0",
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "RESIDUAL33_SCOPE_FROZEN"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceAuditRows": EXPECTED_AUDIT_ROWS,
        "subtractedResolvedRows": EXPECTED_RESOLVED_ROWS,
        "residualRows": EXPECTED_RESIDUAL_ROWS,
        "scopeKeySha256": EXPECTED_RESIDUAL_DIGEST,
        "categoryCounts": expected_categories,
        "priorLongGapCandidateRows": 1,
        "newPrimaryEvidenceRows": 32,
        "rows": residual,
        "resolutionComplete": False,
        "validationPerformanceOpened": False,
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
    parser.add_argument("--resolution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        audit_path=args.audit,
        resolution_path=args.resolution,
        output_path=args.output,
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "rows"},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
