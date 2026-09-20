"""Resolve frozen B3 surviving-unit rows from primary SEC evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

SOURCE_SCOPE_KEY_SHA256 = (
    "sha256:cd190ed2cfbd8147b5f8c3b3c3f562e4b20093e775b88dfc9a6f0f57dc1167f5"
)
EXPECTED_RESOLUTION_KEY_SHA256 = (
    "sha256:a59cce3f542956da1d04b11ebcf783732ac0513668ef7fff3e4f40fa95a55371"
)
EXPECTED_COUNTS = {
    ("0001719489", "GIG.U"): 1,
    ("0001726146", "TWLVU"): 4,
    ("0001742927", "TZACU"): 2,
    ("0001743858", "LOACU"): 1,
    ("0001773086", "ZGYHU"): 2,
    ("0001781162", "SRACU"): 1,
}
SEALED_YEAR = 2023


def _load_scope(path: Path) -> list[dict[str, Any]]:
    p = json.loads(path.read_text(encoding="utf-8"))
    if p.get("status") != "B3_RESIDUAL24_SCOPE_FROZEN":
        raise ValueError("unexpected residual-24 scope status")
    if p.get("residualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-24 key digest changed")
    if p.get("performanceRead") is not False:
        raise ValueError("residual-24 scope is not performance-blind")
    if p.get("priceFieldsRead") != []:
        raise ValueError("residual-24 scope read price fields")
    if p.get("oosOpened") is not False:
        raise ValueError("residual-24 scope opened OOS")
    cols = p["scopeColumns"]
    rows = [dict(zip(cols, values, strict=True)) for values in p["scopeRows"]]
    if len(rows) != 24 or base._key_digest(rows) != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-24 scope content changed")
    return rows


def _year(value: object) -> int:
    text = str(value or "")
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        raise ValueError("invalid evidence date")
    return int(text[:4])


def _load_evidence(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    p = json.loads(path.read_text(encoding="utf-8"))
    if p.get("contractId") != "phase1-b3-surviving-unit-primary-evidence-v1":
        raise ValueError("unexpected surviving-unit evidence contract")
    if p.get("scopeResidualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("surviving-unit evidence scope digest changed")
    if p.get("expectedResolutionRows") != 11:
        raise ValueError("surviving-unit expected row count changed")
    if p.get("expectedResolutionKeySha256") != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("surviving-unit expected digest changed")
    if p.get("performanceRead") is not False or p.get("oosOpened") is not False:
        raise ValueError("surviving-unit evidence violates research boundary")
    if p.get("priceFieldsRead") != []:
        raise ValueError("surviving-unit evidence read price fields")

    out: dict[tuple[str, str], dict[str, Any]] = {}
    for fact in p.get("identities", []):
        key = (str(fact["issuerCik"]), str(fact["ticker"]).upper())
        if int(fact.get("expectedRows", -1)) != EXPECTED_COUNTS.get(key):
            raise ValueError("surviving-unit identity row count changed")
        if fact.get("mode") not in {"UNCHANGED_UNIT", "UNIT_SYMBOL_CHANGE"}:
            raise ValueError("unsupported surviving-unit mode")
        for item in fact.get("primaryEvidence", []):
            if _year(item["evidenceDate"]) >= SEALED_YEAR:
                raise ValueError("sealed OOS evidence date")
        if key in out:
            raise ValueError("duplicate surviving-unit evidence identity")
        out[key] = fact
    if set(out) != set(EXPECTED_COUNTS):
        raise ValueError("surviving-unit evidence identity set changed")
    return out


def _resolution(row: dict[str, Any], fact: dict[str, Any]) -> dict[str, Any]:
    mode = str(fact["mode"])
    target = str(row["targetExitSession"])
    if mode == "UNCHANGED_UNIT":
        return {
            **base._key_object(row),
            "evidenceClass": "PRIMARY_SEC_SURVIVING_UNIT",
            "expectedSourceResolutionSource": "long_internal_gap",
            "effectiveDate": str(row["pivotDate"]),
            "resolutionDecision": "SAME_SECURITY_CONTINUITY",
            "transformationKind": "",
            "resultState": "PRICE_CONTINUOUS_ADJUSTED",
            "successorSymbol": str(row["ticker"]).upper(),
            "successorSharesPerEntryShare": 1.0,
            "cashPerEntryShare": 0.0,
            "sourceActionIds": [],
            "primaryEvidenceAccessions": [
                str(item["accession"]) for item in fact["primaryEvidence"]
            ],
        }

    effective = str(fact["symbolChangeEffectiveDate"])
    if target < effective:
        decision = "SAME_SECURITY_CONTINUITY"
        state = "PRICE_CONTINUOUS_ADJUSTED"
        successor = str(row["ticker"]).upper()
        resolution_effective = str(row["pivotDate"])
    else:
        decision = "SYMBOL_CHANGED_SAME_SECURITY"
        state = "SYMBOL_CHANGED_SAME_SECURITY"
        successor = str(fact["successorSymbol"]).upper()
        resolution_effective = effective
    return {
        **base._key_object(row),
        "evidenceClass": "PRIMARY_SEC_SURVIVING_UNIT",
        "expectedSourceResolutionSource": "long_internal_gap",
        "effectiveDate": resolution_effective,
        "resolutionDecision": decision,
        "transformationKind": "SAME_SECURITY_SYMBOL_CHANGE" if decision.startswith("SYMBOL") else "",
        "resultState": state,
        "successorSymbol": successor,
        "successorSharesPerEntryShare": 1.0,
        "cashPerEntryShare": 0.0,
        "sourceActionIds": [],
        "primaryEvidenceAccessions": [
            str(item["accession"]) for item in fact["primaryEvidence"]
        ],
    }


def resolve(*, scope_path: Path, evidence_path: Path, output_path: Path) -> dict[str, Any]:
    scope = _load_scope(scope_path)
    evidence = _load_evidence(evidence_path)
    target = [
        row
        for row in scope
        if (str(row["issuerCik"]), str(row["ticker"]).upper()) in EXPECTED_COUNTS
    ]
    if len(target) != 11:
        raise ValueError("surviving-unit target row count changed")
    if base._key_digest(target) != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("surviving-unit target key digest changed")
    counts = Counter(
        (str(row["issuerCik"]), str(row["ticker"]).upper()) for row in target
    )
    if dict(counts) != EXPECTED_COUNTS:
        raise ValueError("surviving-unit target composition changed")

    resolutions = []
    for row in target:
        if str(row["resolutionSource"]) != "long_internal_gap":
            raise ValueError("surviving-unit row is not a long-gap row")
        if str(row.get("candidateActionIds") or ""):
            raise ValueError("surviving-unit row has provider action IDs")
        key = (str(row["issuerCik"]), str(row["ticker"]).upper())
        resolutions.append(_resolution(row, evidence[key]))

    if base._key_digest(resolutions) != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("surviving-unit resolution keys changed")

    decisions = Counter(str(row["resolutionDecision"]) for row in resolutions)
    payload = {
        "schemaVersion": "1.0.0",
        "status": "B3_SURVIVING_UNIT_PRIMARY_RESOLUTION_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": 24,
        "resolvedRows": 11,
        "resolutionKeySha256": EXPECTED_RESOLUTION_KEY_SHA256,
        "resolutionDecisionCounts": dict(sorted(decisions.items())),
        "resolutionRows": resolutions,
        "remainingResidualRowsBeforeOtherRules": 13,
        "finalResolutionContractCreated": False,
        "correctedPerformanceOpened": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(resolve(scope_path=args.scope, evidence_path=args.evidence, output_path=args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
