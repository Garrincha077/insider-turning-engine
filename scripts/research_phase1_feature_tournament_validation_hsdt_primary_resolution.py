"""Resolve the sole HSDT F2 validation long-gap continuity row."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED_KEY_DIGEST = (
    "sha256:2dec9e57b3e6927b9c387764e2bcbfe0955cb450e9a546dfb900bcd9c8e92827"
)
EXPECTED_RESIDUAL_SCOPE_DIGEST = (
    "sha256:9ee5091b18344e67b58fe567b92ce99d3f923e4df2829af935158947bdcae2a2"
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


def _digest(row: dict[str, Any]) -> str:
    payload = json.dumps(
        _key_object(row),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _load_scope(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
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
        "residualRows": 33,
        "scopeKeySha256": EXPECTED_RESIDUAL_SCOPE_DIGEST,
        "priorLongGapCandidateRows": 1,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"residual-33 scope mismatch: {key}")
    return payload


def _load_evidence(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "contractId": "phase1-f2-validation-hsdt-primary-evidence-v1",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "resolutionApplied": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"HSDT primary evidence mismatch: {key}")
    return payload


def run(
    *,
    scope_path: Path,
    evidence_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    scope = _load_scope(scope_path)
    evidence = _load_evidence(evidence_path)

    candidates = [
        row
        for row in scope.get("rows", [])
        if (row.get("evidenceAudit") or {}).get("category")
        == "LONG_GAP_PRIOR_SECURITY_CANDIDATE"
    ]
    if len(candidates) != 1:
        raise ValueError("expected exactly one prior-security long-gap row")
    source = dict(candidates[0])
    if _digest(source) != EXPECTED_KEY_DIGEST:
        raise ValueError("HSDT source semantic key changed")

    evidence_row = evidence.get("row")
    if not isinstance(evidence_row, dict):
        raise ValueError("HSDT evidence row missing")
    if _digest(evidence_row) != EXPECTED_KEY_DIGEST:
        raise ValueError("HSDT evidence semantic key changed")

    gap = evidence.get("gap")
    if not isinstance(gap, dict):
        raise ValueError("HSDT evidence gap missing")
    expected_gap = {
        "previousObservedSession": "2022-02-03",
        "firstMissingSession": "2022-02-04",
        "lastMissingSession": "2022-03-17",
        "nextObservedSession": "2022-03-18",
        "maxInternalGapSessions": 29,
    }
    if gap != expected_gap:
        raise ValueError("HSDT exact gap changed")

    interpretation = evidence.get("interpretation")
    if not isinstance(interpretation, dict):
        raise ValueError("HSDT interpretation missing")
    expected = {
        "sameIssuerAcrossEvidence": True,
        "sameTradingSymbolAcrossEvidence": True,
        "sameExchangeAcrossEvidence": True,
        "commonVsClassATitleNormalizationSupported": True,
        "frozenProviderCorporateActionCandidates": 0,
        "holderTransformationEvidenceFound": False,
        "decision": "SAME_SECURITY_CONTINUITY",
        "transformationKind": "",
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "successorSymbol": "HSDT",
        "successorSharesPerEntryShare": "1",
        "cashPerEntryShare": "0",
        "effectiveDate": "2022-03-18",
        "evidenceClass": "SEC_PRIMARY_EXACT_GAP_BRACKETING_SAME_SECURITY",
        "classificationSource": "VALIDATION_HSDT_PRIMARY_GAP_BRACKETING",
    }
    if interpretation != expected:
        raise ValueError("HSDT frozen interpretation changed")

    primary = evidence.get("primaryEvidence")
    if not isinstance(primary, list) or len(primary) != 5:
        raise ValueError("HSDT primary evidence row count changed")
    if not any(item.get("relationToGap") == "BEFORE_GAP" for item in primary):
        raise ValueError("HSDT before-gap primary evidence missing")
    if sum(item.get("relationToGap") == "INSIDE_GAP" for item in primary) < 3:
        raise ValueError("HSDT inside-gap primary evidence incomplete")
    if not any(item.get("relationToGap") == "AFTER_GAP" for item in primary):
        raise ValueError("HSDT after-gap primary evidence missing")
    if {
        str(item.get("issuerCik") or "")
        for item in primary
    } != {"0001610853"}:
        raise ValueError("HSDT primary evidence issuer changed")
    if {
        str(item.get("tradingSymbol") or "")
        for item in primary
    } != {"HSDT"}:
        raise ValueError("HSDT primary evidence symbol changed")
    if {
        str(item.get("exchange") or "")
        for item in primary
    } != {"The Nasdaq Stock Market LLC"}:
        raise ValueError("HSDT primary evidence exchange changed")

    resolution = {
        **_key_object(source),
        "expectedSourceResolutionSource": "long_internal_gap",
        "effectiveDate": "2022-03-18",
        "resolutionDecision": "SAME_SECURITY_CONTINUITY",
        "transformationKind": "",
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "successorSymbol": "HSDT",
        "successorSharesPerEntryShare": "1",
        "cashPerEntryShare": "0",
        "sourceActionIds": [],
        "basket": [],
        "classificationSource": "VALIDATION_HSDT_PRIMARY_GAP_BRACKETING",
        "evidenceClass": "SEC_PRIMARY_EXACT_GAP_BRACKETING_SAME_SECURITY",
        "evidenceSource": "research/validation-hsdt-primary-evidence-v1.json",
        "gapPreviousObservedSession": "2022-02-03",
        "gapFirstMissingSession": "2022-02-04",
        "gapLastMissingSession": "2022-03-17",
        "gapNextObservedSession": "2022-03-18",
        "maxInternalGapSessions": 29,
    }

    result = {
        "schemaVersion": "1.0.0",
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "HSDT_PRIMARY_RESOLUTION_COMPLETE"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": 33,
        "resolvedRows": 1,
        "remainingUnresolvedRows": 32,
        "resolvedKeySha256": EXPECTED_KEY_DIGEST,
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
