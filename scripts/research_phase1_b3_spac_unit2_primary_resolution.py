"""Resolve the second frozen B3 SPAC-unit subset from primary SEC evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

SOURCE_SCOPE_KEY_SHA256 = "sha256:ed13976872da6522da2973a450a1f1c39e22cc19e2ffcc8367b9cc1a1b016b50"
EXPECTED_RESOLUTION_KEY_SHA256 = "sha256:fae1020ef5d77cd93b885da6bc4e5c8b4a83ec1ded373f9ccc2148bf90add999"
EXPECTED_COUNTS = {
    ("0001719893", "MTECU"): 4,
    ("0001768910", "GRCYU"): 2,
    ("0001777393", "SBE.U"): 1,
    ("0001785424", "FSRVU"): 1,
}
SEALED_YEAR = 2023


def _load_scope(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "B3_RESIDUAL63_SCOPE_FROZEN":
        raise ValueError("unexpected residual-63 scope status")
    if payload.get("residualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-63 key digest changed")
    for field, expected in (
        ("performanceRead", False),
        ("oosOpened", False),
        ("productionScoringChanged", False),
    ):
        if payload.get(field) is not expected:
            raise ValueError(f"residual-63 boundary violated: {field}")
    if payload.get("priceFieldsRead") != []:
        raise ValueError("residual-63 source read price fields")
    cols = payload["scopeColumns"]
    rows = [dict(zip(cols, values, strict=True)) for values in payload["scopeRows"]]
    if len(rows) != 63 or base._key_digest(rows) != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-63 scope content changed")
    return rows


def _load_evidence(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    p = json.loads(path.read_text(encoding="utf-8"))
    if p.get("contractId") != "phase1-b3-spac-unit2-primary-evidence-v1":
        raise ValueError("unexpected evidence contract")
    if p.get("scopeResidualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("evidence scope digest changed")
    if p.get("expectedResolutionKeySha256") != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("expected resolution digest changed")
    if p.get("expectedResolutionRows") != 8:
        raise ValueError("expected row count changed")
    if p.get("performanceRead") is not False or p.get("oosOpened") is not False:
        raise ValueError("evidence boundary violated")
    if p.get("priceFieldsRead") != [] or p.get("productionScoringChanged") is not False:
        raise ValueError("evidence read prices or changed production")

    result = {}
    for fact in p.get("identities", []):
        key = (str(fact["issuerCik"]), str(fact["unitSymbol"]).upper())
        if key in result or int(fact["expectedRows"]) != EXPECTED_COUNTS.get(key):
            raise ValueError("identity composition changed")
        if fact.get("unitSecurityKind") != "SPAC_UNIT":
            raise ValueError("unexpected security kind")
        if fact.get("primaryConclusion") != "ORIGINAL_UNIT_REMAINED_LISTED_UNDER_SAME_SYMBOL":
            raise ValueError("primary conclusion changed")
        if fact.get("resolutionDecision") != "SAME_SECURITY_CONTINUITY":
            raise ValueError("decision changed")
        if fact.get("resultState") != "PRICE_CONTINUOUS_ADJUSTED":
            raise ValueError("state changed")
        if fact.get("successorSymbol") != fact.get("unitSymbol"):
            raise ValueError("unit successor symbol changed")
        if fact.get("componentCommonSymbol") == fact.get("unitSymbol"):
            raise ValueError("unit/common symbols not distinct")
        if float(fact.get("successorSharesPerEntryShare", 0)) != 1.0:
            raise ValueError("unit quantity changed")
        if float(fact.get("cashPerEntryShare", -1)) != 0.0:
            raise ValueError("unit cash changed")
        if not any(str(e["evidenceDate"]) >= str(fact["targetExitMax"]) for e in fact["evidence"]):
            raise ValueError("primary evidence does not bracket target")
        if any(int(str(e["evidenceDate"])[:4]) >= SEALED_YEAR for e in fact["evidence"]):
            raise ValueError("sealed OOS evidence date")
        result[key] = fact
    if set(result) != set(EXPECTED_COUNTS):
        raise ValueError("evidence identity set changed")
    return result


def resolve(scope_path: Path, evidence_path: Path, output_path: Path) -> dict[str, Any]:
    scope = _load_scope(scope_path)
    evidence = _load_evidence(evidence_path)
    rows = [r for r in scope if (str(r["issuerCik"]), str(r["ticker"])) in EXPECTED_COUNTS]
    if len(rows) != 8 or base._key_digest(rows) != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("exact SPAC-unit2 scope changed")
    counts = Counter((str(r["issuerCik"]), str(r["ticker"])) for r in rows)
    if dict(counts) != EXPECTED_COUNTS:
        raise ValueError("exact SPAC-unit2 identity counts changed")

    resolutions = []
    for row in rows:
        fact = evidence[(str(row["issuerCik"]), str(row["ticker"]))]
        if str(row["targetExitSession"]) > str(fact["targetExitMax"]):
            raise ValueError("target exceeds frozen evidence range")
        resolutions.append({
            **base._key_object(row),
            "evidenceClass": "PRIMARY_SEC_SPAC_UNIT_CONTINUITY_WAVE2",
            "expectedSourceResolutionSource": "long_internal_gap",
            "effectiveDate": str(row["pivotDate"]),
            "resolutionDecision": "SAME_SECURITY_CONTINUITY",
            "transformationKind": "",
            "resultState": "PRICE_CONTINUOUS_ADJUSTED",
            "successorSymbol": str(row["ticker"]),
            "successorSharesPerEntryShare": 1.0,
            "cashPerEntryShare": 0.0,
            "sourceActionIds": [],
            "componentCommonSymbol": str(fact["componentCommonSymbol"]),
            "primaryEvidenceAccessions": [str(e["accession"]) for e in fact["evidence"]],
        })
    if base._key_digest(resolutions) != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("resolution keys changed")

    payload = {
        "schemaVersion": "1.0.0",
        "status": "B3_SPAC_UNIT2_PRIMARY_RESOLUTION_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": 63,
        "resolvedRows": 8,
        "resolutionKeySha256": EXPECTED_RESOLUTION_KEY_SHA256,
        "resolutionRows": resolutions,
        "remainingResidualRowsBeforeOtherRules": 55,
        "finalResolutionContractCreated": False,
        "correctedPerformanceOpened": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", type=Path, required=True)
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    print(json.dumps(resolve(a.scope, a.evidence, a.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
