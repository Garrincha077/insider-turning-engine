"""Resolve the frozen B3 provider-ambiguity rows from pinned SEC evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

EXPECTED_SCOPE_DIGEST = (
    "sha256:46eeaa05a83960c1ef9537dd88972351b8c984c996ccddffa23f7da8d294ab58"
)
EXPECTED_PROVIDER_ROWS = 4
SEALED_YEAR = 2023


def _scope_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "B3_RESIDUAL91_SCOPE_FROZEN":
        raise ValueError("unexpected residual-91 scope status")
    if payload.get("residualKeySha256") != EXPECTED_SCOPE_DIGEST:
        raise ValueError("residual-91 scope digest changed")
    if payload.get("performanceRead") is not False or payload.get("oosOpened") is not False:
        raise ValueError("residual-91 scope violates research boundaries")
    columns = payload["scopeColumns"]
    rows = [
        dict(zip(columns, values, strict=True))
        for values in payload["scopeRows"]
    ]
    if len(rows) != 91 or base._key_digest(rows) != EXPECTED_SCOPE_DIGEST:
        raise ValueError("residual-91 scope keys changed")
    return rows


def _evidence(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contractId") != "phase1-b3-provider-primary-resolution-evidence-v1":
        raise ValueError("unexpected primary evidence contract")
    if payload.get("scopeResidualKeySha256") != EXPECTED_SCOPE_DIGEST:
        raise ValueError("evidence contract scope digest mismatch")
    if payload.get("researchOnly") is not True:
        raise ValueError("evidence contract is not research-only")
    if payload.get("performanceRead") is not False:
        raise ValueError("evidence contract is not performance-blind")
    if payload.get("priceFieldsRead") != []:
        raise ValueError("evidence contract read price fields")
    if payload.get("oosOpened") is not False:
        raise ValueError("evidence contract opened OOS")
    if payload.get("productionScoringChanged") is not False:
        raise ValueError("evidence contract changed production scoring")

    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in payload.get("evidence", []):
        for date_field in ("effectiveSymbolDate", "secEventDate"):
            value = str(row[date_field])
            if int(value[:4]) >= SEALED_YEAR:
                raise ValueError("sealed OOS evidence date")
        if row.get("securityClass") != "CLASS A COMMON STOCK":
            raise ValueError("primary evidence does not identify Class A common stock")
        if row.get("resolutionDecision") != "SYMBOL_CHANGED_SAME_SECURITY":
            raise ValueError("unexpected primary resolution decision")
        if row.get("transformationKind") != "SAME_SECURITY_SYMBOL_CHANGE":
            raise ValueError("unexpected primary transformation kind")
        if row.get("resultState") != "SYMBOL_CHANGED_SAME_SECURITY":
            raise ValueError("unexpected primary result state")
        if float(row.get("successorSharesPerEntryShare", 0)) != 1.0:
            raise ValueError("primary evidence implies non-1:1 holder transformation")
        if float(row.get("cashPerEntryShare", -1)) != 0.0:
            raise ValueError("primary evidence implies cash consideration")
        key = (str(row["issuerCik"]), str(row["oldSymbol"]).upper())
        if key in result:
            raise ValueError("duplicate primary evidence identity")
        result[key] = row

    if set(result) != {("0001679688", "CLNY"), ("0001717547", "CLNC")}:
        raise ValueError("primary evidence identity set changed")
    return result


def resolve(
    *,
    scope_path: Path,
    evidence_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    rows = _scope_rows(scope_path)
    evidence = _evidence(evidence_path)

    provider_rows = [
        row for row in rows
        if row["resolutionSource"] == "provider"
    ]
    if len(provider_rows) != EXPECTED_PROVIDER_ROWS:
        raise ValueError("provider residual row count changed")
    if any(
        row["residualReason"] != "PROVIDER_AMBIGUOUS_REQUIRES_PRIMARY_EVIDENCE"
        for row in provider_rows
    ):
        raise ValueError("unexpected provider residual reason")

    resolutions: list[dict[str, Any]] = []
    for row in provider_rows:
        identity = (str(row["issuerCik"]), str(row["ticker"]).upper())
        fact = evidence.get(identity)
        if fact is None:
            raise ValueError("provider row lacks pinned primary evidence")
        if str(row.get("candidateActionTypes") or "") != "name_changes":
            raise ValueError("provider residual is not a name-change case")
        if str(row["pivotDate"]) != str(fact["effectiveSymbolDate"]):
            raise ValueError("provider pivot differs from official symbol-change date")
        if not str(row["entrySession"]) < str(fact["effectiveSymbolDate"]) <= str(row["targetExitSession"]):
            raise ValueError("official symbol-change date outside event horizon")

        resolutions.append(
            {
                **base._key_object(row),
                "evidenceClass": "PRIMARY_SEC_NAME_CHANGE",
                "expectedSourceResolutionSource": "provider",
                "effectiveDate": str(fact["effectiveSymbolDate"]),
                "resolutionDecision": "SYMBOL_CHANGED_SAME_SECURITY",
                "transformationKind": "SAME_SECURITY_SYMBOL_CHANGE",
                "resultState": "SYMBOL_CHANGED_SAME_SECURITY",
                "successorSymbol": str(fact["successorSymbol"]).upper(),
                "successorSharesPerEntryShare": 1.0,
                "cashPerEntryShare": 0.0,
                "sourceActionIds": [
                    value
                    for value in str(row.get("candidateActionIds") or "").split(";")
                    if value
                ],
                "primarySecAccession": str(fact["secAccession"]),
                "officialOldCusip": str(fact["oldCusip"]),
                "officialNewCusip": str(fact["officialNewCusip"]),
                "providerCusipConflict": bool(fact["providerCusipConflict"]),
            }
        )

    if len({_key for _key in (base._row_key(row) for row in resolutions)}) != 4:
        raise ValueError("duplicate provider resolution keys")

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_PROVIDER_PRIMARY_RESOLUTION_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": 91,
        "sourceProviderAmbiguityRows": len(provider_rows),
        "resolvedProviderRows": len(resolutions),
        "resolutionKeySha256": base._key_digest(resolutions),
        "resolutionRows": resolutions,
        "remainingResidualRowsBeforeOtherRules": 91 - len(resolutions),
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
    print(json.dumps(resolve(
        scope_path=args.scope,
        evidence_path=args.evidence,
        output_path=args.output,
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
