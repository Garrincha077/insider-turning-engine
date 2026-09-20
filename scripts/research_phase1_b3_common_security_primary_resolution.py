"""Resolve frozen ordinary-common B3 continuity rows from primary evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

SOURCE_SCOPE_KEY_SHA256 = (
    "sha256:be82164c63ed8c8528017ff3201d5172e818655e5c7a8fa48bd7576c7cb02cd6"
)
EXPECTED_RESOLUTION_KEY_SHA256 = (
    "sha256:a99206160529fc915c30b9859307e1cd603f7f4fab5d24278519af18919bc430"
)
EXPECTED_COUNTS = {
    ("0001624326", "PAVM"): 6,
    ("0000100716", "UNAM"): 3,
    ("0000744452", "APDN"): 3,
    ("0001610853", "HSDT"): 3,
    ("0001023994", "SGBX"): 2,
    ("0001130166", "CYCC"): 1,
    ("0001640384", "LMFA"): 1,
}
SEALED_YEAR = 2023


def _load_scope(path: Path) -> list[dict[str, Any]]:
    p = json.loads(path.read_text(encoding="utf-8"))
    if p.get("status") != "B3_RESIDUAL43_SCOPE_FROZEN":
        raise ValueError("unexpected residual-43 scope status")
    if p.get("residualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-43 key digest changed")
    if p.get("performanceRead") is not False:
        raise ValueError("residual-43 scope is not performance-blind")
    if p.get("priceFieldsRead") != []:
        raise ValueError("residual-43 scope read price fields")
    if p.get("oosOpened") is not False:
        raise ValueError("residual-43 scope opened OOS")
    if p.get("productionScoringChanged") is not False:
        raise ValueError("residual-43 scope changed production scoring")
    cols = p["scopeColumns"]
    rows = [dict(zip(cols, values, strict=True)) for values in p["scopeRows"]]
    if len(rows) != 43 or base._key_digest(rows) != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-43 scope content changed")
    return rows


def _year(value: object) -> int:
    text = str(value or "")
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        raise ValueError("invalid evidence date")
    return int(text[:4])


def _load_evidence(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    p = json.loads(path.read_text(encoding="utf-8"))
    if p.get("contractId") != "phase1-b3-common-security-primary-evidence-v1":
        raise ValueError("unexpected common-security evidence contract")
    if p.get("scopeResidualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("common-security evidence scope digest changed")
    if p.get("expectedResolutionRows") != 19:
        raise ValueError("expected common-security row count changed")
    if p.get("expectedResolutionKeySha256") != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("expected common-security key digest changed")
    if p.get("researchOnly") is not True:
        raise ValueError("common-security evidence is not research-only")
    if p.get("performanceRead") is not False:
        raise ValueError("common-security evidence is not performance-blind")
    if p.get("priceFieldsRead") != []:
        raise ValueError("common-security evidence read price fields")
    if p.get("oosOpened") is not False:
        raise ValueError("common-security evidence opened OOS")
    if p.get("productionScoringChanged") is not False:
        raise ValueError("common-security evidence changed production scoring")

    result: dict[tuple[str, str], dict[str, Any]] = {}
    for fact in p.get("identities", []):
        key = (str(fact["issuerCik"]), str(fact["ticker"]).upper())
        if key in result:
            raise ValueError("duplicate common-security evidence identity")
        if int(fact.get("expectedRows", -1)) != EXPECTED_COUNTS.get(key):
            raise ValueError("common-security identity row count changed")

        if fact.get("resolutionDecision") != "SAME_SECURITY_CONTINUITY":
            raise ValueError("common-security decision changed")
        if fact.get("resultState") != "PRICE_CONTINUOUS_ADJUSTED":
            raise ValueError("common-security state changed")
        if str(fact.get("transformationKind") or ""):
            raise ValueError("common-security transformation kind changed")
        if str(fact.get("successorSymbol") or "").upper() != key[1]:
            raise ValueError("common-security successor symbol changed")
        if str(fact.get("successorIssuerCik") or "") != key[0]:
            raise ValueError("common-security successor issuer changed")
        if float(fact.get("successorSharesPerEntryShare", 0)) != 1.0:
            raise ValueError("common-security quantity changed")
        if float(fact.get("cashPerEntryShare", -1)) != 0.0:
            raise ValueError("common-security cash changed")
        for item in fact.get("primaryEvidence", []):
            if _year(item["evidenceDate"]) >= SEALED_YEAR:
                raise ValueError("sealed OOS evidence date")
        result[key] = fact

    if set(result) != set(EXPECTED_COUNTS):
        raise ValueError("common-security evidence identity set changed")
    return result


def resolve(
    *,
    scope_path: Path,
    evidence_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    scope = _load_scope(scope_path)
    evidence = _load_evidence(evidence_path)
    target = [
        row
        for row in scope
        if (str(row["issuerCik"]), str(row["ticker"]).upper())
        in EXPECTED_COUNTS
    ]
    if len(target) != 19:
        raise ValueError("common-security target row count changed")
    if base._key_digest(target) != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("common-security target key digest changed")
    counts = Counter(
        (str(row["issuerCik"]), str(row["ticker"]).upper()) for row in target
    )
    if dict(counts) != EXPECTED_COUNTS:
        raise ValueError("common-security target composition changed")

    resolutions: list[dict[str, Any]] = []
    for row in target:
        if str(row["resolutionSource"]) != "long_internal_gap":
            raise ValueError("common-security row is not a long-gap row")
        if str(row.get("candidateActionIds") or ""):
            raise ValueError("common-security row has provider action IDs")
        identity = (str(row["issuerCik"]), str(row["ticker"]).upper())
        fact = evidence[identity]
        resolutions.append(
            {
                **base._key_object(row),
                "evidenceClass": "PRIMARY_SEC_COMMON_SECURITY_CONTINUITY",
                "expectedSourceResolutionSource": "long_internal_gap",
                "effectiveDate": str(row["pivotDate"]),
                "resolutionDecision": "SAME_SECURITY_CONTINUITY",
                "transformationKind": "",
                "resultState": "PRICE_CONTINUOUS_ADJUSTED",
                "successorSymbol": identity[1],
                "successorIssuerCik": identity[0],
                "successorSharesPerEntryShare": 1.0,
                "cashPerEntryShare": 0.0,
                "sourceActionIds": [],
                "splitAdjustmentOnly": bool(
                    fact.get("splitAdjustmentOnly", False)
                ),
                "primaryEvidenceAccessions": [
                    str(item["accession"])
                    for item in fact["primaryEvidence"]
                ],
            }
        )

    if base._key_digest(resolutions) != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("common-security resolution keys changed")

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_COMMON_SECURITY_PRIMARY_RESOLUTION_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": 43,
        "resolvedRows": 19,
        "resolutionKeySha256": EXPECTED_RESOLUTION_KEY_SHA256,
        "resolutionRows": resolutions,
        "remainingResidualRowsBeforeOtherRules": 24,
        "finalResolutionContractCreated": False,
        "correctedPerformanceOpened": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            resolve(
                scope_path=args.scope,
                evidence_path=args.evidence,
                output_path=args.output,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
