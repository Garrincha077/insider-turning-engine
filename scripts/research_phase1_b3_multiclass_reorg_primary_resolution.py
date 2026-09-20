"""Resolve frozen B3 multi-class/reorganization rows from primary evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

SOURCE_SCOPE_KEY_SHA256 = (
    "sha256:378820b3ab1a31441aa5b6a3e0faa54c51961e08aa5747d502a5638000e5a6dc"
)
EXPECTED_RESOLUTION_KEY_SHA256 = (
    "sha256:d9103eb5d9b5e04e18f955f4f6361ba39932ad285dff823a1046f72b613c2e91"
)
EXPECTED_COUNTS = {
    ("0001635193", "GGO"): 8,
    ("0001471824", "TAGS"): 1,
    ("0001647088", "EAGL"): 2,
    ("0001697152", "FMCIU"): 1,
}
SEALED_YEAR = 2023


def _load_scope(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "B3_RESIDUAL55_SCOPE_FROZEN":
        raise ValueError("unexpected residual-55 scope status")
    if payload.get("residualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-55 scope digest changed")
    if payload.get("performanceRead") is not False:
        raise ValueError("residual-55 scope is not performance-blind")
    if payload.get("priceFieldsRead") != []:
        raise ValueError("residual-55 scope read price fields")
    if payload.get("oosOpened") is not False:
        raise ValueError("residual-55 scope opened OOS")
    if payload.get("productionScoringChanged") is not False:
        raise ValueError("residual-55 scope changed production scoring")

    columns = payload["scopeColumns"]
    rows = [
        dict(zip(columns, values, strict=True))
        for values in payload["scopeRows"]
    ]
    if len(rows) != 55 or base._key_digest(rows) != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-55 scope content changed")
    return rows


def _evidence_year(value: object) -> int:
    text = str(value or "")
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        raise ValueError("invalid primary evidence date")
    return int(text[:4])


def _load_evidence(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contractId") != (
        "phase1-b3-multiclass-reorg-primary-evidence-v1"
    ):
        raise ValueError("unexpected multi-class evidence contract")
    if payload.get("scopeResidualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("multi-class evidence scope digest changed")
    if payload.get("expectedResolutionRows") != 12:
        raise ValueError("multi-class expected resolution count changed")
    if payload.get("expectedResolutionKeySha256") != (
        EXPECTED_RESOLUTION_KEY_SHA256
    ):
        raise ValueError("multi-class expected resolution digest changed")
    if payload.get("researchOnly") is not True:
        raise ValueError("multi-class evidence is not research-only")
    if payload.get("performanceRead") is not False:
        raise ValueError("multi-class evidence is not performance-blind")
    if payload.get("priceFieldsRead") != []:
        raise ValueError("multi-class evidence read price fields")
    if payload.get("oosOpened") is not False:
        raise ValueError("multi-class evidence opened OOS")
    if payload.get("productionScoringChanged") is not False:
        raise ValueError("multi-class evidence changed production scoring")

    result: dict[tuple[str, str], dict[str, Any]] = {}
    for fact in payload.get("identities", []):
        key = (str(fact["issuerCik"]), str(fact["ticker"]).upper())
        if key in result:
            raise ValueError("duplicate multi-class evidence identity")
        if int(fact.get("expectedRows", -1)) != EXPECTED_COUNTS.get(key):
            raise ValueError("multi-class identity row count changed")

        for item in fact.get("primaryEvidence", []):
            date_value = item.get("evidenceDate")
            if _evidence_year(date_value) >= SEALED_YEAR:
                raise ValueError("sealed OOS primary evidence date")

        decision = str(fact["resolutionDecision"])
        state = str(fact["resultState"])
        successor = str(fact.get("successorSymbol") or "").upper()
        quantity = float(fact["successorSharesPerEntryShare"])
        cash = float(fact["cashPerEntryShare"])

        if key in {("0001635193", "GGO"), ("0001471824", "TAGS")}:
            if decision != "SAME_SECURITY_CONTINUITY":
                raise ValueError("same-security identity decision changed")
            if state != "PRICE_CONTINUOUS_ADJUSTED":
                raise ValueError("same-security identity state changed")
            if successor != key[1] or quantity != 1.0 or cash != 0.0:
                raise ValueError("same-security identity terms changed")
            if str(fact.get("successorIssuerCik")) != key[0]:
                raise ValueError("same-security issuer changed")
        elif key == ("0001647088", "EAGL"):
            if decision != "SYMBOL_CHANGED_SAME_SECURITY":
                raise ValueError("EAGL decision changed")
            if state != "SYMBOL_CHANGED_SAME_SECURITY":
                raise ValueError("EAGL result state changed")
            if str(fact.get("transformationKind")) != (
                "SAME_SECURITY_DOMESTICATION"
            ):
                raise ValueError("EAGL transformation kind changed")
            if str(fact.get("effectiveDate")) != "2017-11-30":
                raise ValueError("EAGL effective date changed")
            if successor != "WSC" or quantity != 1.0 or cash != 0.0:
                raise ValueError("EAGL continuation terms changed")
            if str(fact.get("successorIssuerCik")) != "0001647088":
                raise ValueError("EAGL successor issuer changed")
        elif key == ("0001697152", "FMCIU"):
            if decision != "DISCONTINUOUS_NO_COMPLETE_VALUATION":
                raise ValueError("FMCIU discontinuity decision changed")
            if state != "DISCONTINUOUS_NO_COMPLETE_VALUATION":
                raise ValueError("FMCIU discontinuity state changed")
            if str(fact.get("transformationKind")) != (
                "MULTI_LEG_UNIT_SEPARATION_UNVALUED_WARRANT"
            ):
                raise ValueError("FMCIU transformation kind changed")
            if str(fact.get("effectiveDate")) != "2018-02-22":
                raise ValueError("FMCIU effective date changed")
            if successor or quantity != 0.0 or cash != 0.0:
                raise ValueError("FMCIU incomplete-valuation terms changed")
            composition = fact.get("unitComposition") or {}
            if (
                float(composition.get("commonShares", -1)) != 1.0
                or float(composition.get("rightsPerUnit", -1)) != 1.0
                or float(composition.get("warrantPerUnit", -1)) != 0.5
                or float(composition.get("rightConversionCommonShares", -1))
                != 0.1
            ):
                raise ValueError("FMCIU unit composition changed")
            if fact.get("completeHolderValuationRepresentableByFrozenShareCashSchema") is not False:
                raise ValueError("FMCIU representation boundary changed")
        else:
            raise ValueError("unexpected multi-class identity")

        result[key] = fact

    if set(result) != set(EXPECTED_COUNTS):
        raise ValueError("multi-class evidence identity set changed")
    return result


def _resolution_for(
    row: dict[str, Any],
    fact: dict[str, Any],
) -> dict[str, Any]:
    decision = str(fact["resolutionDecision"])

    if decision == "SAME_SECURITY_CONTINUITY":
        effective = str(row["pivotDate"])
    else:
        effective = str(fact["effectiveDate"])
        if not str(row["entrySession"]) < effective <= str(row["targetExitSession"]):
            raise ValueError("resolution event falls outside frozen horizon")

    return {
        **base._key_object(row),
        "evidenceClass": "PRIMARY_SEC_MULTICLASS_REORG",
        "expectedSourceResolutionSource": "long_internal_gap",
        "effectiveDate": effective,
        "resolutionDecision": decision,
        "transformationKind": str(fact.get("transformationKind") or ""),
        "resultState": str(fact["resultState"]),
        "successorSymbol": str(fact.get("successorSymbol") or "").upper(),
        "successorIssuerCik": str(fact.get("successorIssuerCik") or ""),
        "successorSharesPerEntryShare": float(
            fact["successorSharesPerEntryShare"]
        ),
        "cashPerEntryShare": float(fact["cashPerEntryShare"]),
        "sourceActionIds": [],
        "primaryEvidenceAccessions": [
            str(item.get("accession") or item.get("source") or "")
            for item in fact["primaryEvidence"]
        ],
    }


def resolve(
    *,
    scope_path: Path,
    evidence_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    scope = _load_scope(scope_path)
    evidence = _load_evidence(evidence_path)

    target_rows = [
        row
        for row in scope
        if (str(row["issuerCik"]), str(row["ticker"]).upper())
        in EXPECTED_COUNTS
    ]
    if len(target_rows) != 12:
        raise ValueError("multi-class target row count changed")
    if base._key_digest(target_rows) != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("multi-class target key digest changed")

    actual_counts = Counter(
        (str(row["issuerCik"]), str(row["ticker"]).upper())
        for row in target_rows
    )
    if dict(actual_counts) != EXPECTED_COUNTS:
        raise ValueError("multi-class target composition changed")

    resolutions: list[dict[str, Any]] = []
    for row in target_rows:
        if str(row["resolutionSource"]) != "long_internal_gap":
            raise ValueError("multi-class row is not a long-gap row")
        if str(row.get("candidateActionIds") or ""):
            raise ValueError("multi-class row has provider action IDs")
        identity = (str(row["issuerCik"]), str(row["ticker"]).upper())
        resolutions.append(_resolution_for(row, evidence[identity]))

    if base._key_digest(resolutions) != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("multi-class resolution keys changed")

    decisions = Counter(str(row["resolutionDecision"]) for row in resolutions)
    states = Counter(str(row["resultState"]) for row in resolutions)

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_MULTICLASS_REORG_PRIMARY_RESOLUTION_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": 55,
        "resolvedRows": len(resolutions),
        "resolutionKeySha256": base._key_digest(resolutions),
        "resolutionDecisionCounts": dict(sorted(decisions.items())),
        "resultStateCounts": dict(sorted(states.items())),
        "resolutionRows": resolutions,
        "remainingResidualRowsBeforeOtherRules": 55 - len(resolutions),
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
