"""Resolve the frozen B3 SPAC-unit continuity rows from primary SEC evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

SOURCE_SCOPE_KEY_SHA256 = (
    "sha256:c28829aa56204db04633546d91b06b938d06f897cd022d2c8147f488415d2742"
)
EXPECTED_RESOLUTION_KEY_SHA256 = (
    "sha256:2d93f63e9002ef10c913315a7a30bde9377bebf95a7e0442ade39b496e12beba"
)
EXPECTED_BUCKET = (
    "TICKER_CHANGED_AFTER_PIVOT|TITLE_SET_EXACT_MATCH|"
    "TICKER_CHANGED_AFTER_PIVOT"
)
EXPECTED_IDENTITIES = {
    ("0001705771", "DOTAU"),
    ("0001735041", "GLACU"),
}
SEALED_YEAR = 2023


def _load_scope(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "B3_RESIDUAL87_SCOPE_FROZEN":
        raise ValueError("unexpected residual-87 scope status")
    if payload.get("residualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-87 key digest changed")
    if payload.get("performanceRead") is not False:
        raise ValueError("residual-87 source is not performance-blind")
    if payload.get("priceFieldsRead") != []:
        raise ValueError("residual-87 source read price fields")
    if payload.get("oosOpened") is not False:
        raise ValueError("residual-87 source opened OOS")
    if payload.get("productionScoringChanged") is not False:
        raise ValueError("residual-87 source changed production scoring")

    columns = payload["scopeColumns"]
    rows = [
        dict(zip(columns, values, strict=True))
        for values in payload["scopeRows"]
    ]
    if len(rows) != 87 or base._key_digest(rows) != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-87 scope content changed")
    return rows


def _date_year(value: object) -> int:
    text = str(value or "")
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        raise ValueError("invalid ISO evidence date")
    return int(text[:4])


def _load_evidence(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contractId") != "phase1-b3-spac-unit-primary-evidence-v1":
        raise ValueError("unexpected SPAC-unit evidence contract")
    if payload.get("scopeResidualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("SPAC-unit evidence scope digest changed")
    if payload.get("expectedResolutionRows") != 4:
        raise ValueError("SPAC-unit expected resolution row count changed")
    if payload.get("expectedResolutionKeySha256") != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("SPAC-unit expected resolution digest changed")
    if payload.get("researchOnly") is not True:
        raise ValueError("SPAC-unit evidence is not research-only")
    if payload.get("performanceRead") is not False:
        raise ValueError("SPAC-unit evidence is not performance-blind")
    if payload.get("priceFieldsRead") != []:
        raise ValueError("SPAC-unit evidence read price fields")
    if payload.get("oosOpened") is not False:
        raise ValueError("SPAC-unit evidence opened OOS")
    if payload.get("productionScoringChanged") is not False:
        raise ValueError("SPAC-unit evidence changed production scoring")

    result: dict[tuple[str, str], dict[str, Any]] = {}
    for fact in payload.get("identities", []):
        for field in ("separationEventDate", "separationEffectiveDate"):
            if _date_year(fact[field]) >= SEALED_YEAR:
                raise ValueError("sealed OOS evidence date")
        for evidence in fact.get("postGapEvidence", []):
            if _date_year(evidence["evidenceDate"]) >= SEALED_YEAR:
                raise ValueError("sealed OOS post-gap evidence date")

        if fact.get("unitSecurityKind") != "SPAC_UNIT":
            raise ValueError("unexpected security kind")
        if fact.get("primaryConclusion") != (
            "ORIGINAL_UNIT_REMAINED_LISTED_UNDER_SAME_SYMBOL"
        ):
            raise ValueError("primary evidence does not establish unit continuity")
        if fact.get("resolutionDecision") != "SAME_SECURITY_CONTINUITY":
            raise ValueError("unexpected resolution decision")
        if fact.get("resultState") != "PRICE_CONTINUOUS_ADJUSTED":
            raise ValueError("unexpected result state")
        if float(fact.get("successorSharesPerEntryShare", 0)) != 1.0:
            raise ValueError("unit continuity is not one-to-one")
        if float(fact.get("cashPerEntryShare", -1)) != 0.0:
            raise ValueError("unit continuity unexpectedly includes cash")
        if fact.get("successorSymbol") != fact.get("unitSymbol"):
            raise ValueError("unit symbol changed in evidence contract")
        if fact.get("componentCommonSymbol") == fact.get("unitSymbol"):
            raise ValueError("unit/common symbols are not distinct")

        key = (str(fact["issuerCik"]), str(fact["unitSymbol"]).upper())
        if key in result:
            raise ValueError("duplicate SPAC-unit evidence identity")
        result[key] = fact

    if set(result) != EXPECTED_IDENTITIES:
        raise ValueError("SPAC-unit evidence identity set changed")
    return result


def _assert_target_bracket(row: dict[str, Any], fact: dict[str, Any]) -> None:
    target = str(row["targetExitSession"])
    entry = str(row["entrySession"])
    if not entry < target:
        raise ValueError("invalid event target ordering")
    if target > str(fact["scopedTargetExitMax"]):
        raise ValueError("row target exceeds frozen evidence maximum")

    post_dates = sorted(str(item["evidenceDate"]) for item in fact["postGapEvidence"])
    if not any(date >= target for date in post_dates):
        raise ValueError("no primary evidence at/after target exit")

    business_combination = fact.get("businessCombinationEffectiveDate")
    if business_combination and str(business_combination) <= target:
        raise ValueError("holder transformation occurred before target exit")


def resolve(
    *,
    scope_path: Path,
    evidence_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    scope = _load_scope(scope_path)
    evidence = _load_evidence(evidence_path)

    target_rows = [row for row in scope if row["evidenceBucket"] == EXPECTED_BUCKET]
    if len(target_rows) != 4:
        raise ValueError("exact-title ticker-change bucket count changed")
    if {(str(r["issuerCik"]), str(r["ticker"])) for r in target_rows} != (
        EXPECTED_IDENTITIES
    ):
        raise ValueError("exact-title ticker-change identities changed")
    if base._key_digest(target_rows) != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("exact-title ticker-change key digest changed")

    resolutions: list[dict[str, Any]] = []
    for row in target_rows:
        identity = (str(row["issuerCik"]), str(row["ticker"]).upper())
        fact = evidence[identity]
        _assert_target_bracket(row, fact)

        if str(row["resolutionSource"]) != "long_internal_gap":
            raise ValueError("scoped SPAC-unit row is not a long-gap row")
        if str(row.get("candidateActionIds") or ""):
            raise ValueError("scoped SPAC-unit row has provider action IDs")
        if str(row.get("candidateActionTypes") or ""):
            raise ValueError("scoped SPAC-unit row has provider action types")

        resolutions.append(
            {
                **base._key_object(row),
                "evidenceClass": "PRIMARY_SEC_SPAC_UNIT_CONTINUITY",
                "expectedSourceResolutionSource": "long_internal_gap",
                "effectiveDate": str(row["pivotDate"]),
                "resolutionDecision": "SAME_SECURITY_CONTINUITY",
                "transformationKind": "",
                "resultState": "PRICE_CONTINUOUS_ADJUSTED",
                "successorSymbol": str(row["ticker"]).upper(),
                "successorSharesPerEntryShare": 1.0,
                "cashPerEntryShare": 0.0,
                "sourceActionIds": [],
                "unitSecurityKind": "SPAC_UNIT",
                "componentCommonSymbol": str(fact["componentCommonSymbol"]),
                "separationAccession": str(fact["separationAccession"]),
                "primaryConclusion": str(fact["primaryConclusion"]),
            }
        )

    if base._key_digest(resolutions) != EXPECTED_RESOLUTION_KEY_SHA256:
        raise ValueError("SPAC-unit resolution keys changed")

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_SPAC_UNIT_PRIMARY_RESOLUTION_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": 87,
        "sourceEvidenceBucket": EXPECTED_BUCKET,
        "resolvedRows": len(resolutions),
        "resolutionKeySha256": base._key_digest(resolutions),
        "resolutionRows": resolutions,
        "remainingResidualRowsBeforeOtherRules": 87 - len(resolutions),
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
