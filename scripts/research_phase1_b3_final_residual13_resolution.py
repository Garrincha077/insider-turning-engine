"""Resolve the final frozen B3 residual-13 scope from primary evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

SOURCE_SCOPE_KEY_SHA256 = (
    "sha256:0183d2bb7d158cfa642cb02106eb1937d7e0a327db9e23efb4423188b13c5a18"
)
EXPECTED_RESOLUTION_KEY_SHA256 = SOURCE_SCOPE_KEY_SHA256
EXPECTED_COUNTS = {
    ("0001622577", "ARWA"): 3,
    ("0001630940", "AAPC"): 3,
    ("0001641398", "WYIG"): 3,
    ("0001680873", "ATACU"): 2,
    ("0001698990", "TPGE"): 1,
    ("0001823882", "NBA.U"): 1,
}
SEALED_YEAR = 2023


def _year(value: object) -> int:
    text = str(value or "")
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        raise ValueError("invalid ISO evidence date")
    return int(text[:4])


def _load_scope(path: Path) -> list[dict[str, Any]]:
    p = json.loads(path.read_text(encoding="utf-8"))
    if p.get("status") != "B3_RESIDUAL13_SCOPE_FROZEN":
        raise ValueError("unexpected residual-13 scope status")
    if p.get("residualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-13 key digest changed")
    if p.get("performanceRead") is not False:
        raise ValueError("residual-13 scope is not performance-blind")
    if p.get("priceFieldsRead") != []:
        raise ValueError("residual-13 scope read price fields")
    if p.get("oosOpened") is not False:
        raise ValueError("residual-13 scope opened OOS")
    if p.get("productionScoringChanged") is not False:
        raise ValueError("residual-13 scope changed production scoring")

    columns = p["scopeColumns"]
    rows = [
        dict(zip(columns, values, strict=True))
        for values in p["scopeRows"]
    ]
    if len(rows) != 13 or base._key_digest(rows) != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-13 scope content changed")
    return rows


def _validate_standard_terms(
    key: tuple[str, str],
    fact: dict[str, Any],
) -> None:
    quantity = float(fact["successorSharesPerEntryShare"])
    cash = float(fact["cashPerEntryShare"])
    successor = str(fact["successorSymbol"]).upper()
    successor_cik = str(fact["successorIssuerCik"])
    mode = str(fact["mode"])

    if mode in {"UNCHANGED_COMMON", "UNCHANGED_COMMON_DELISTED"}:
        if successor != key[1] or successor_cik != key[0]:
            raise ValueError("same-common successor identity changed")
        if quantity != 1.0 or cash != 0.0:
            raise ValueError("same-common holder terms changed")
    elif mode == "COMMON_SYMBOL_CHANGE":
        if quantity != 1.0 or cash != 0.0:
            raise ValueError("common symbol-change holder terms changed")
        if successor_cik != key[0] or not successor:
            raise ValueError("common symbol-change identity changed")
    elif mode == "COMMON_TO_SUCCESSOR_COMMON":
        if quantity <= 0 or cash != 0.0 or not successor:
            raise ValueError("common successor terms changed")
        if not successor_cik:
            raise ValueError("common successor issuer missing")
    elif mode == "UNIT_TO_COMMON_PLUS_RIGHT":
        if quantity <= 1.0 or cash != 0.0 or not successor:
            raise ValueError("unit conversion terms changed")
        if not successor_cik:
            raise ValueError("unit conversion successor issuer missing")
    else:
        raise ValueError("unsupported standard identity mode")


def _load_evidence(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    p = json.loads(path.read_text(encoding="utf-8"))
    if p.get("contractId") != "phase1-b3-final-residual13-primary-evidence-v1":
        raise ValueError("unexpected final residual-13 evidence contract")
    if p.get("scopeResidualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("final residual-13 evidence scope digest changed")
    if p.get("expectedResolutionRows") != 13:
        raise ValueError("final residual-13 expected row count changed")
    if p.get("expectedResolutionKeySha256") != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("final residual-13 expected key digest changed")
    if p.get("researchOnly") is not True:
        raise ValueError("final evidence is not research-only")
    if p.get("performanceRead") is not False:
        raise ValueError("final evidence is not performance-blind")
    if p.get("priceFieldsRead") != []:
        raise ValueError("final evidence read price fields")
    if p.get("oosOpened") is not False:
        raise ValueError("final evidence opened OOS")
    if p.get("productionScoringChanged") is not False:
        raise ValueError("final evidence changed production scoring")

    out: dict[tuple[str, str], dict[str, Any]] = {}
    for fact in p.get("identities", []):
        key = (str(fact["issuerCik"]), str(fact["ticker"]).upper())
        if int(fact.get("expectedRows", -1)) != EXPECTED_COUNTS.get(key):
            raise ValueError("final residual identity row count changed")
        if key in out:
            raise ValueError("duplicate final residual evidence identity")
        for item in fact.get("primaryEvidence", []):
            if _year(item["evidenceDate"]) >= SEALED_YEAR:
                raise ValueError("sealed OOS primary evidence date")
            filing_date = item.get("filingDate")
            if filing_date and _year(filing_date) >= SEALED_YEAR:
                raise ValueError("sealed OOS filing date")

        mode = str(fact["mode"])
        if mode == "UNIT_TO_MULTI_COMPONENT_BASKET":
            if key != ("0001823882", "NBA.U"):
                raise ValueError("multi-component basket attached to wrong identity")
            if _year(fact["effectiveDate"]) >= SEALED_YEAR:
                raise ValueError("sealed basket effective date")
            basket = fact.get("basket")
            if not isinstance(basket, list) or len(basket) != 2:
                raise ValueError("NBA.U basket must contain exactly two components")
            expected = {
                ("MIMO", "COMMON_STOCK", 1.0),
                ("MIMO WS", "PUBLIC_WARRANT", 1.0),
            }
            actual = {
                (
                    str(x["symbol"]).upper(),
                    str(x["securityClass"]),
                    float(x["quantityPerEntryUnit"]),
                )
                for x in basket
            }
            if actual != expected:
                raise ValueError("NBA.U basket terms changed")
            if float(fact["cashPerEntryShare"]) != 0.0:
                raise ValueError("NBA.U basket unexpectedly includes cash")
        else:
            if "effectiveDate" in fact and _year(fact["effectiveDate"]) >= SEALED_YEAR:
                raise ValueError("sealed transformation effective date")
            _validate_standard_terms(key, fact)
        out[key] = fact

    if set(out) != set(EXPECTED_COUNTS):
        raise ValueError("final residual evidence identity set changed")
    return out


def _same_security(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **base._key_object(row),
        "evidenceClass": "PRIMARY_SEC_FINAL_RESIDUAL13",
        "expectedSourceResolutionSource": "long_internal_gap",
        "effectiveDate": str(row["pivotDate"]),
        "resolutionDecision": "SAME_SECURITY_CONTINUITY",
        "transformationKind": "",
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "successorSymbol": str(row["ticker"]).upper(),
        "successorSharesPerEntryShare": 1.0,
        "cashPerEntryShare": 0.0,
        "sourceActionIds": [],
    }


def _resolve_row(row: dict[str, Any], fact: dict[str, Any]) -> dict[str, Any]:
    mode = str(fact["mode"])
    target = str(row["targetExitSession"])

    if mode in {"UNCHANGED_COMMON", "UNCHANGED_COMMON_DELISTED"}:
        return _same_security(row)

    effective = str(fact["effectiveDate"])
    if target < effective:
        return _same_security(row)

    if mode == "COMMON_SYMBOL_CHANGE":
        return {
            **base._key_object(row),
            "evidenceClass": "PRIMARY_SEC_FINAL_RESIDUAL13",
            "expectedSourceResolutionSource": "long_internal_gap",
            "effectiveDate": effective,
            "resolutionDecision": "SYMBOL_CHANGED_SAME_SECURITY",
            "transformationKind": "SAME_SECURITY_SYMBOL_CHANGE",
            "resultState": "SYMBOL_CHANGED_SAME_SECURITY",
            "successorSymbol": str(fact["successorSymbol"]).upper(),
            "successorSharesPerEntryShare": 1.0,
            "cashPerEntryShare": 0.0,
            "sourceActionIds": [],
        }

    if mode in {"COMMON_TO_SUCCESSOR_COMMON", "UNIT_TO_COMMON_PLUS_RIGHT"}:
        return {
            **base._key_object(row),
            "evidenceClass": "PRIMARY_SEC_FINAL_RESIDUAL13",
            "expectedSourceResolutionSource": "long_internal_gap",
            "effectiveDate": effective,
            "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
            "transformationKind": (
                "COMMON_TO_SUCCESSOR_COMMON"
                if mode == "COMMON_TO_SUCCESSOR_COMMON"
                else "UNIT_COMPONENT_CONVERSION"
            ),
            "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
            "successorSymbol": str(fact["successorSymbol"]).upper(),
            "successorIssuerCik": str(fact["successorIssuerCik"]),
            "successorSharesPerEntryShare": float(
                fact["successorSharesPerEntryShare"]
            ),
            "cashPerEntryShare": float(fact["cashPerEntryShare"]),
            "sourceActionIds": [],
        }

    if mode == "UNIT_TO_MULTI_COMPONENT_BASKET":
        return {
            **base._key_object(row),
            "evidenceClass": "PRIMARY_SEC_FINAL_RESIDUAL13",
            "expectedSourceResolutionSource": "long_internal_gap",
            "effectiveDate": effective,
            "resolutionDecision": "TRANSFORMED_MULTI_COMPONENT_CONSIDERATION",
            "transformationKind": "UNIT_COMPONENT_BASKET",
            "resultState": "TRANSFORMED_MULTI_COMPONENT_CONSIDERATION",
            "successorSymbol": "",
            "successorSharesPerEntryShare": 0.0,
            "cashPerEntryShare": float(fact["cashPerEntryShare"]),
            "basket": fact["basket"],
            "basketValuationRule": "EXACT_TARGET_SESSION_SUM_OR_FAIL_CLOSED",
            "sourceActionIds": [],
        }
    raise ValueError("unsupported final residual mode")


def resolve(
    *,
    scope_path: Path,
    evidence_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    scope = _load_scope(scope_path)
    evidence = _load_evidence(evidence_path)

    counts = Counter(
        (str(row["issuerCik"]), str(row["ticker"]).upper())
        for row in scope
    )
    if dict(counts) != EXPECTED_COUNTS:
        raise ValueError("final residual scope composition changed")

    resolutions: list[dict[str, Any]] = []
    for row in scope:
        if str(row["resolutionSource"]) != "long_internal_gap":
            raise ValueError("final residual row is not a long-gap row")
        if str(row.get("candidateActionIds") or ""):
            raise ValueError("final residual row has provider action IDs")
        key = (str(row["issuerCik"]), str(row["ticker"]).upper())
        resolutions.append(_resolve_row(row, evidence[key]))

    if base._key_digest(resolutions) != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("final residual resolution keys changed")

    decisions = Counter(str(row["resolutionDecision"]) for row in resolutions)
    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_FINAL_RESIDUAL13_PRIMARY_RESOLUTION_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": 13,
        "resolvedRows": 13,
        "unresolvedRowsAfterThisGate": 0,
        "resolutionKeySha256": EXPECTED_RESOLUTION_KEY_SHA256,
        "resolutionDecisionCounts": dict(sorted(decisions.items())),
        "resolutionRows": resolutions,
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
    result = resolve(
        scope_path=args.scope,
        evidence_path=args.evidence,
        output_path=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
