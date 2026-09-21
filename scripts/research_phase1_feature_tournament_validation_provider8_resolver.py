"""Resolve the eight exact-action F2 validation provider residual rows."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_ROWS = 41
EXPECTED_PROVIDER_REUSE = 8
EXPECTED_RESIDUAL_ROWS = 33
EXPECTED_PROVIDER_TICKERS = {
    "BOTJ": 2,
    "CLDB": 3,
    "GNTY": 1,
    "HWBK": 1,
    "WPF": 1,
}


def _number(value: object) -> str:
    number = Decimal(str(0 if value in (None, "") else value))
    text = format(number.normalize(), "f")
    return "0" if text in {"", "-0"} else text


def _resolution(row: dict[str, Any]) -> dict[str, Any]:
    evidence = row.get("evidenceAudit")
    if not isinstance(evidence, dict):
        raise ValueError("provider candidate lacks evidence audit")
    if evidence.get("category") != "PROVIDER_EXACT_ACTION_PRIOR_CANDIDATE":
        raise ValueError("row is not an exact-action prior candidate")

    action_ids = [str(item) for item in row.get("candidateActionIds") or []]
    if not action_ids:
        raise ValueError("provider candidate has no action IDs")
    if action_ids != [str(item) for item in evidence.get("actionIds") or []]:
        raise ValueError("provider action identity changed")

    fingerprint = evidence.get("economicFingerprint")
    if not isinstance(fingerprint, list) or len(fingerprint) != 5:
        raise ValueError("provider economic fingerprint malformed")
    state, successor, quantity, cash, basket = fingerprint
    labels = evidence.get("schemaLabels")
    if not isinstance(labels, list) or len(labels) != 1:
        raise ValueError("provider schema labels are not uniquely frozen")
    if not isinstance(labels[0], list) or len(labels[0]) != 2:
        raise ValueError("provider schema label shape changed")
    decision, kind = labels[0]

    effective = str(evidence.get("exampleEffectiveDate") or "")
    entry = str(row["entrySession"])
    target = str(row["targetExitSession"])
    if not effective or not (entry < effective <= target):
        raise ValueError("prior action effective date outside current horizon")

    normalized_basket = []
    if basket:
        if not isinstance(basket, list):
            raise ValueError("provider basket fingerprint malformed")
        for item in basket:
            if not isinstance(item, list) or len(item) != 3:
                raise ValueError("provider basket component malformed")
            symbol, security_class, component_quantity = item
            normalized_basket.append(
                {
                    "symbol": str(symbol),
                    "securityClass": str(security_class),
                    "quantityPerEntryUnit": _number(component_quantity),
                }
            )

    result = {
        "eventNumber": int(row["eventNumber"]),
        "issuerCik": str(row["issuerCik"]),
        "ticker": str(row["ticker"]),
        "evaluationSession": str(row["evaluationSession"]),
        "entrySession": entry,
        "horizon": int(row["horizon"]),
        "targetExitSession": target,
        "expectedSourceResolutionSource": str(row["resolutionSource"]),
        "effectiveDate": effective,
        "resolutionDecision": str(decision),
        "transformationKind": str(kind),
        "resultState": str(state),
        "successorSymbol": str(successor),
        "successorSharesPerEntryShare": _number(quantity),
        "cashPerEntryShare": _number(cash),
        "sourceActionIds": action_ids,
        "priorEvidenceSources": list(evidence.get("priorSources") or []),
        "priorMatchCount": int(evidence.get("priorMatchCount") or 0),
        "evidenceClass": "FROZEN_EXACT_ACTION_PRIOR_EVIDENCE",
    }
    if normalized_basket:
        result["basket"] = normalized_basket
    return result


def run(
    *,
    audit_path: Path,
    resolution_output: Path,
    residual_output: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
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
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": EXPECTED_SOURCE_ROWS,
        "auditedRows": EXPECTED_SOURCE_ROWS,
        "auditOnly": True,
        "resolutionApplied": False,
        "validationPerformanceOpened": False,
    }
    for key, expected in required.items():
        if audit.get(key) != expected:
            raise ValueError(f"prior-evidence audit mismatch: {key}")

    rows = audit.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_SOURCE_ROWS:
        raise ValueError("prior-evidence audit rows changed")

    reusable = [
        row
        for row in rows
        if row.get("evidenceAudit", {}).get("category")
        == "PROVIDER_EXACT_ACTION_PRIOR_CANDIDATE"
    ]
    residual = [
        row
        for row in rows
        if row not in reusable
    ]
    if len(reusable) != EXPECTED_PROVIDER_REUSE:
        raise ValueError("provider reuse count changed")
    if len(residual) != EXPECTED_RESIDUAL_ROWS:
        raise ValueError("post-provider residual count changed")

    resolutions = [_resolution(row) for row in reusable]
    resolutions.sort(key=lambda item: item["eventNumber"])
    ticker_counts = Counter(row["ticker"] for row in resolutions)
    if dict(sorted(ticker_counts.items())) != EXPECTED_PROVIDER_TICKERS:
        raise ValueError("provider8 ticker partition changed")

    decisions = Counter(row["resolutionDecision"] for row in resolutions)
    if dict(sorted(decisions.items())) != {
        "SYMBOL_CHANGED_SAME_SECURITY": 1,
        "TRANSFORMED_HOLDER_CONSIDERATION": 7,
    }:
        raise ValueError("provider8 decision partition changed")

    resolution_payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_VALIDATION_PROVIDER8_RESOLVED",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": EXPECTED_SOURCE_ROWS,
        "resolvedProviderRows": len(resolutions),
        "remainingResidualRows": len(residual),
        "tickerCounts": dict(sorted(ticker_counts.items())),
        "resolutionDecisionCounts": dict(sorted(decisions.items())),
        "resolutionRows": resolutions,
        "resolutionApplied": True,
        "validationPerformanceOpened": False,
    }

    residual_categories = Counter(
        str(row["evidenceAudit"]["category"])
        for row in residual
    )
    residual_payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_VALIDATION_RESIDUAL33_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": EXPECTED_SOURCE_ROWS,
        "providerRowsResolved": len(resolutions),
        "residualRows": len(residual),
        "categoryCounts": dict(sorted(residual_categories.items())),
        "rows": sorted(
            residual,
            key=lambda item: (
                int(item["eventNumber"]),
                int(item["horizon"]),
            ),
        ),
        "resolutionComplete": False,
        "validationPerformanceOpened": False,
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
                    if key != "resolutionRows"
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
