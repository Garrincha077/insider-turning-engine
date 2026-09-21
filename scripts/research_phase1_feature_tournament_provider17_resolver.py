"""Resolve the 17 exact provider-action rows from the frozen residual34 audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_ROWS = 34
EXPECTED_PROVIDER_ROWS = 17
EXPECTED_LONG_GAP_ROWS = 17

ALLOWED_PROVIDER_CATEGORIES = {
    "PROVIDER_ACTION_REUSE_B3",
    "PROVIDER_ACTION_REUSE_B1_STOCK_DIVIDEND",
}


def _assert_boundary(payload: dict[str, Any]) -> None:
    required = {
        "status": "PHASE1_FEATURE_TOURNAMENT_RESIDUAL_EVIDENCE_AUDIT_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": EXPECTED_SOURCE_ROWS,
        "auditedRows": EXPECTED_SOURCE_ROWS,
        "providerRows": EXPECTED_PROVIDER_ROWS,
        "providerActionReusableRows": EXPECTED_PROVIDER_ROWS,
        "longGapRows": EXPECTED_LONG_GAP_ROWS,
        "newPrimaryEvidenceRows": 10,
        "auditOnly": True,
        "resolutionApplied": False,
        "featureDiscoveryOutcomesOpened": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"residual evidence audit mismatch: {key}")


def _decimal_text(value: Any) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid provider economic term: {value}") from exc
    text = format(number.normalize(), "f")
    return "0" if text in {"", "-0"} else text


def _sha(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> str:
    material = [
        {field: row[field] for field in fields}
        for row in rows
    ]
    raw = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _resolution(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("currentResolutionSource") != "provider":
        raise ValueError("non-provider row passed to provider resolver")

    evidence = row.get("evidenceAudit")
    if not isinstance(evidence, dict):
        raise ValueError("provider row missing evidence audit")

    category = str(evidence.get("category") or "")
    if category not in ALLOWED_PROVIDER_CATEGORIES:
        raise ValueError(f"provider row is not reusable: {category}")

    action_ids = [str(item) for item in row.get("candidateActionIds") or []]
    evidence_action_ids = [str(item) for item in evidence.get("actionIds") or []]
    if not action_ids or sorted(action_ids) != sorted(evidence_action_ids):
        raise ValueError("provider action identity mismatch")

    fingerprint = evidence.get("economicFingerprint")
    if not isinstance(fingerprint, list) or len(fingerprint) != 6:
        raise ValueError("provider economic fingerprint malformed")

    decision, kind, state, successor, shares, cash = [
        str(item)
        for item in fingerprint
    ]
    if decision != "TRANSFORMED_HOLDER_CONSIDERATION":
        raise ValueError("provider reuse must transform holder consideration")
    if state != "TRANSFORMED_HOLDER_CONSIDERATION":
        raise ValueError("provider reuse result state changed")

    effective = str(evidence.get("effectiveDate") or "")
    entry = str(row.get("entrySession") or "")
    target = str(row.get("targetExitSession") or "")
    if not effective or not (entry < effective <= target):
        raise ValueError("provider action effective date outside event horizon")

    if kind == "STOCK_DIVIDEND_QUANTITY" and successor != str(row["ticker"]):
        raise ValueError("stock-dividend successor symbol changed unexpectedly")

    prior_count = int(evidence.get("priorMatchCount") or 0)
    if prior_count < 1:
        raise ValueError("provider reuse has no prior frozen evidence match")

    return {
        "eventNumber": int(row["currentEventNumber"]),
        "issuerCik": str(row["issuerCik"]),
        "ticker": str(row["ticker"]),
        "evaluationSession": str(row["evaluationSession"]),
        "entrySession": entry,
        "horizon": int(row["horizon"]),
        "targetExitSession": target,
        "expectedSourceResolutionSource": "provider",
        "effectiveDate": effective,
        "resolutionDecision": decision,
        "transformationKind": kind,
        "resultState": state,
        "successorSymbol": successor,
        "successorSharesPerEntryShare": _decimal_text(shares),
        "cashPerEntryShare": _decimal_text(cash),
        "sourceActionIds": sorted(action_ids),
        "candidateActionTypes": sorted(
            str(item)
            for item in row.get("candidateActionTypes") or []
        ),
        "reuseCategory": category,
        "evidenceClass": str(evidence.get("evidenceClass") or ""),
        "evidenceSourceRelease": str(evidence.get("sourceRelease") or ""),
        "priorMatchCount": prior_count,
    }


def run(
    *,
    audit_path: Path,
    resolution_output: Path,
    residual_output: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    _assert_boundary(audit)

    rows = audit.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_SOURCE_ROWS:
        raise ValueError("residual evidence audit row count changed")

    provider_rows = [
        row for row in rows
        if row.get("currentResolutionSource") == "provider"
    ]
    long_gap_rows = [
        row for row in rows
        if row.get("currentResolutionSource") == "long_internal_gap"
    ]
    if len(provider_rows) != EXPECTED_PROVIDER_ROWS:
        raise ValueError("provider row count changed")
    if len(long_gap_rows) != EXPECTED_LONG_GAP_ROWS:
        raise ValueError("long-gap row count changed")

    resolutions = [_resolution(row) for row in provider_rows]
    resolutions.sort(key=lambda row: (row["eventNumber"], row["horizon"]))

    keys = [
        (
            row["eventNumber"],
            row["issuerCik"],
            row["ticker"],
            row["entrySession"],
            row["horizon"],
            row["targetExitSession"],
        )
        for row in resolutions
    ]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate provider resolution key")

    categories = Counter(row["reuseCategory"] for row in resolutions)
    if dict(categories) != {
        "PROVIDER_ACTION_REUSE_B3": 16,
        "PROVIDER_ACTION_REUSE_B1_STOCK_DIVIDEND": 1,
    }:
        raise ValueError("provider reuse category partition changed")

    transformation_counts = Counter(
        row["transformationKind"]
        for row in resolutions
    )
    if dict(transformation_counts) != {
        "STOCK_AND_CASH_MERGER": 4,
        "STOCK_DIVIDEND_QUANTITY": 13,
    }:
        raise ValueError("provider transformation partition changed")

    resolution_fields = (
        "eventNumber",
        "issuerCik",
        "ticker",
        "evaluationSession",
        "entrySession",
        "horizon",
        "targetExitSession",
        "effectiveDate",
        "resolutionDecision",
        "transformationKind",
        "successorSymbol",
        "successorSharesPerEntryShare",
        "cashPerEntryShare",
    )

    resolution_payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_PROVIDER17_RESOLVED",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": EXPECTED_SOURCE_ROWS,
        "resolvedProviderRows": len(resolutions),
        "remainingLongGapRows": len(long_gap_rows),
        "reuseCategoryCounts": dict(sorted(categories.items())),
        "transformationCounts": dict(sorted(transformation_counts.items())),
        "resolutionKeySha256": _sha(resolutions, resolution_fields),
        "rows": resolutions,
        "resolutionApplied": True,
        "featureDiscoveryOutcomesOpened": False,
    }

    long_gap_rows = sorted(
        long_gap_rows,
        key=lambda row: (
            int(row["currentEventNumber"]),
            int(row["horizon"]),
        ),
    )
    long_gap_categories = Counter(
        str(row["evidenceAudit"]["category"])
        for row in long_gap_rows
    )
    if dict(long_gap_categories) != {
        "LONG_GAP_PRIOR_SECURITY_CANDIDATE": 7,
        "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED": 10,
    }:
        raise ValueError("long-gap residual partition changed")

    residual_payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_LONG_GAP17_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": EXPECTED_SOURCE_ROWS,
        "providerRowsResolved": len(resolutions),
        "residualRows": len(long_gap_rows),
        "priorSecurityCandidateRows": long_gap_categories[
            "LONG_GAP_PRIOR_SECURITY_CANDIDATE"
        ],
        "newPrimaryEvidenceRows": long_gap_categories[
            "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED"
        ],
        "categoryCounts": dict(sorted(long_gap_categories.items())),
        "rows": long_gap_rows,
        "resolutionComplete": False,
        "featureDiscoveryOutcomesOpened": False,
    }

    resolution_output.parent.mkdir(parents=True, exist_ok=True)
    residual_output.parent.mkdir(parents=True, exist_ok=True)
    resolution_output.write_text(
        json.dumps(resolution_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    residual_output.write_text(
        json.dumps(residual_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return resolution_payload, residual_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--resolution-output", type=Path, required=True)
    parser.add_argument("--residual-output", type=Path, required=True)
    args = parser.parse_args()

    resolution, residual = run(
        audit_path=args.audit,
        resolution_output=args.resolution_output,
        residual_output=args.residual_output,
    )
    print(
        json.dumps(
            {
                "resolution": {
                    key: value
                    for key, value in resolution.items()
                    if key != "rows"
                },
                "residual": {
                    key: value
                    for key, value in residual.items()
                    if key != "rows"
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
