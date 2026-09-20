"""Resolve frozen B3 one-sided identity rows from primary SEC evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

SOURCE_SCOPE_KEY_SHA256 = (
    "sha256:d1758905bedc027e7f7448cbffed1bf9a35506b947bd8bdec77e48096f28adcd"
)
EXPECTED_RESOLUTION_KEY_SHA256 = (
    "sha256:6380297ba23e117849914bb4e2f9e1956a53c22c65a6514d99e992537294861f"
)
EXPECTED_BUCKET = (
    "BEFORE_ONLY_EXPECTED_TICKER|ONE_SIDED_ACCESSION_ONLY|"
    "EXPECTED_TICKER_BOTH_SIDES"
)
EXPECTED_COUNTS = {
    ("0000865058", "NSEC"): 7,
    ("0001122063", "FTNW"): 5,
    ("0001314475", "LOV"): 7,
    ("0001330421", "BV"): 1,
}
SEALED_YEAR = 2023


def _load_scope(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "B3_RESIDUAL83_SCOPE_FROZEN":
        raise ValueError("unexpected residual-83 scope status")
    if payload.get("residualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-83 key digest changed")
    if payload.get("performanceRead") is not False:
        raise ValueError("residual-83 scope is not performance-blind")
    if payload.get("priceFieldsRead") != []:
        raise ValueError("residual-83 scope read price fields")
    if payload.get("oosOpened") is not False:
        raise ValueError("residual-83 scope opened OOS")
    if payload.get("productionScoringChanged") is not False:
        raise ValueError("residual-83 scope changed production scoring")

    columns = payload["scopeColumns"]
    rows = [
        dict(zip(columns, values, strict=True))
        for values in payload["scopeRows"]
    ]
    if len(rows) != 83 or base._key_digest(rows) != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-83 scope content changed")
    return rows


def _year(value: object) -> int:
    text = str(value or "")
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        raise ValueError("invalid evidence date")
    return int(text[:4])


def _load_evidence(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contractId") != "phase1-b3-one-sided-primary-evidence-v1":
        raise ValueError("unexpected one-sided evidence contract")
    if payload.get("scopeResidualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("one-sided evidence scope digest changed")
    if payload.get("expectedResolutionRows") != 20:
        raise ValueError("one-sided expected resolution count changed")
    if payload.get("expectedResolutionKeySha256") != (
        EXPECTED_RESOLUTION_KEY_SHA256
    ):
        raise ValueError("one-sided expected resolution digest changed")
    if payload.get("researchOnly") is not True:
        raise ValueError("one-sided evidence is not research-only")
    if payload.get("performanceRead") is not False:
        raise ValueError("one-sided evidence is not performance-blind")
    if payload.get("priceFieldsRead") != []:
        raise ValueError("one-sided evidence read price fields")
    if payload.get("oosOpened") is not False:
        raise ValueError("one-sided evidence opened OOS")
    if payload.get("productionScoringChanged") is not False:
        raise ValueError("one-sided evidence changed production scoring")

    result: dict[tuple[str, str], dict[str, Any]] = {}
    for fact in payload.get("identities", []):
        for evidence in fact.get("primaryEvidence", []):
            if _year(evidence["evidenceDate"]) >= SEALED_YEAR:
                raise ValueError("sealed OOS evidence date")

        key = (str(fact["issuerCik"]), str(fact["ticker"]).upper())
        if key in result:
            raise ValueError("duplicate one-sided evidence identity")
        if int(fact.get("expectedRows", -1)) != EXPECTED_COUNTS.get(key):
            raise ValueError("one-sided identity row count changed")

        decision = str(fact["resolutionDecision"])
        state = str(fact["resultState"])
        quantity = float(fact["successorSharesPerEntryShare"])
        cash = float(fact["cashPerEntryShare"])
        successor = str(fact.get("successorSymbol") or "").upper()

        if decision == "SAME_SECURITY_CONTINUITY":
            if state != "PRICE_CONTINUOUS_ADJUSTED":
                raise ValueError("same-security evidence has wrong state")
            if successor != key[1] or quantity != 1.0 or cash != 0.0:
                raise ValueError("same-security terms changed")
            if str(fact.get("successorIssuerCik")) != key[0]:
                raise ValueError("same-security issuer changed")
        elif decision == "TRANSFORMED_HOLDER_CONSIDERATION":
            if state != "TRANSFORMED_HOLDER_CONSIDERATION":
                raise ValueError("holder transformation has wrong state")
            kind = str(fact.get("transformationKind") or "")
            if kind == "ADS_EXCHANGE":
                if key != ("0001314475", "LOV"):
                    raise ValueError("ADS exchange attached to wrong identity")
                if successor != "LOV" or quantity != 0.1 or cash != 0.0:
                    raise ValueError("LOV ADS exchange terms changed")
                if str(fact.get("successorIssuerCik")) != "0001705338":
                    raise ValueError("LOV successor issuer changed")
            elif kind == "CASH_MERGER":
                if key != ("0001330421", "BV"):
                    raise ValueError("cash merger attached to wrong identity")
                if successor or quantity != 0.0 or cash != 5.5:
                    raise ValueError("BV cash merger terms changed")
            else:
                raise ValueError("unsupported one-sided transformation kind")
            if _year(fact["effectiveDate"]) >= SEALED_YEAR:
                raise ValueError("sealed transformation effective date")
        else:
            raise ValueError("unsupported one-sided resolution decision")

        result[key] = fact

    if set(result) != set(EXPECTED_COUNTS):
        raise ValueError("one-sided evidence identity set changed")
    return result


def _resolution_for(
    row: dict[str, Any],
    fact: dict[str, Any],
) -> dict[str, Any]:
    decision = str(fact["resolutionDecision"])
    if decision == "SAME_SECURITY_CONTINUITY":
        effective = str(row["pivotDate"])
        transformation_kind = ""
    else:
        effective = str(fact["effectiveDate"])
        transformation_kind = str(fact["transformationKind"])
        if not str(row["entrySession"]) < effective <= str(row["targetExitSession"]):
            raise ValueError("holder transformation outside event horizon")

    return {
        **base._key_object(row),
        "evidenceClass": "PRIMARY_SEC_ONE_SIDED_IDENTITY",
        "expectedSourceResolutionSource": "long_internal_gap",
        "effectiveDate": effective,
        "resolutionDecision": decision,
        "transformationKind": transformation_kind,
        "resultState": str(fact["resultState"]),
        "successorSymbol": str(fact.get("successorSymbol") or "").upper(),
        "successorIssuerCik": str(fact.get("successorIssuerCik") or ""),
        "successorSharesPerEntryShare": float(
            fact["successorSharesPerEntryShare"]
        ),
        "cashPerEntryShare": float(fact["cashPerEntryShare"]),
        "sourceActionIds": [],
        "primaryEvidenceAccessions": [
            str(item["accession"]) for item in fact["primaryEvidence"]
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

    target_rows = [row for row in scope if row["evidenceBucket"] == EXPECTED_BUCKET]
    if len(target_rows) != 20:
        raise ValueError("one-sided evidence bucket count changed")
    if base._key_digest(target_rows) != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("one-sided evidence bucket key digest changed")

    actual_counts = Counter(
        (str(row["issuerCik"]), str(row["ticker"]).upper())
        for row in target_rows
    )
    if dict(actual_counts) != EXPECTED_COUNTS:
        raise ValueError("one-sided identity composition changed")

    resolutions: list[dict[str, Any]] = []
    for row in target_rows:
        if str(row["resolutionSource"]) != "long_internal_gap":
            raise ValueError("one-sided row is not a long-gap row")
        if str(row.get("candidateActionIds") or ""):
            raise ValueError("one-sided row has provider action IDs")
        if str(row.get("candidateActionTypes") or ""):
            raise ValueError("one-sided row has provider action types")
        identity = (str(row["issuerCik"]), str(row["ticker"]).upper())
        resolutions.append(_resolution_for(row, evidence[identity]))

    if base._key_digest(resolutions) != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("one-sided resolution keys changed")

    state_counts = Counter(str(row["resultState"]) for row in resolutions)
    decision_counts = Counter(str(row["resolutionDecision"]) for row in resolutions)

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_ONE_SIDED_PRIMARY_RESOLUTION_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": 83,
        "sourceEvidenceBucket": EXPECTED_BUCKET,
        "resolvedRows": len(resolutions),
        "resolutionKeySha256": base._key_digest(resolutions),
        "resolutionDecisionCounts": dict(sorted(decision_counts.items())),
        "resultStateCounts": dict(sorted(state_counts.items())),
        "resolutionRows": resolutions,
        "remainingResidualRowsBeforeOtherRules": 83 - len(resolutions),
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
