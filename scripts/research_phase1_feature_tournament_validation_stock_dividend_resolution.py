"""Resolve the five frozen F2 validation stock-dividend rows."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_ROWS = 32
EXPECTED_TARGET_ROWS = 5
EXPECTED_REMAINING_ROWS = 27
EXPECTED_SOURCE_DIGEST = (
    "sha256:4b8d0df8ff1d06f018fdcbdf281b9fa2be05f21e77b57682012b36b419049e34"
)
EXPECTED_TARGET_DIGEST = (
    "sha256:7dd0615edd13ae996379d9c49194a45edbeda6e5bcf418e1b47c948540a562a3"
)

KEY_FIELDS = (
    "eventNumber",
    "issuerCik",
    "ticker",
    "evaluationSession",
    "entrySession",
    "horizon",
    "targetExitSession",
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


def _key_digest(rows: list[dict[str, Any]]) -> str:
    lines = sorted(
        json.dumps(_key_object(row), sort_keys=True, separators=(",", ":"))
        for row in rows
    )
    return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _number(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"invalid numeric value: {value}") from None
    if not result.is_finite():
        raise ValueError("non-finite numeric value")
    return result


def _format(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _load_scope(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "RESIDUAL32_SCOPE_FROZEN"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "residualRows": EXPECTED_SOURCE_ROWS,
        "scopeKeySha256": EXPECTED_SOURCE_DIGEST,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"residual-32 mismatch: {key}")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_SOURCE_ROWS:
        raise ValueError("residual-32 rows changed")
    return [dict(row) for row in rows]


def _load_evidence(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "contractId": (
            "phase1-f2-validation-stock-dividend-primary-evidence-v1"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "targetKeySha256": EXPECTED_TARGET_DIGEST,
        "resolutionApplied": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"stock-dividend evidence mismatch: {key}")
    rows = payload.get("evidence")
    if not isinstance(rows, list) or len(rows) != EXPECTED_TARGET_ROWS:
        raise ValueError("stock-dividend evidence count changed")
    if _key_digest(rows) != EXPECTED_TARGET_DIGEST:
        raise ValueError("stock-dividend evidence key digest changed")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        action_id = str(row["actionId"])
        if action_id in result:
            raise ValueError("duplicate stock-dividend evidence action")
        result[action_id] = dict(row)
    return result


def _load_provider(path: Path, action_ids: set[str]) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "researchOnly": True,
        "performanceRead": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "period": ["2016-01-01", "2022-12-31"],
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"provider inventory mismatch: {key}")
    found: dict[str, dict[str, Any]] = {}
    for row in payload.get("actions", []):
        action_id = str(row.get("id") or "")
        if action_id not in action_ids:
            continue
        if action_id in found:
            raise ValueError("duplicate provider action")
        found[action_id] = dict(row)
    if set(found) != action_ids:
        raise ValueError("provider stock-dividend action set changed")
    return found


def _resolution(
    row: dict[str, Any],
    fact: dict[str, Any],
    provider: dict[str, Any],
) -> dict[str, Any]:
    ids = [str(item) for item in row.get("candidateActionIds") or []]
    if ids != [str(fact["actionId"])]:
        raise ValueError("stock-dividend source action identity changed")
    if row.get("candidateActionTypes") != ["stock_dividends"]:
        raise ValueError("stock-dividend source action type changed")
    if str(row.get("resolutionSource") or "") != "provider":
        raise ValueError("stock-dividend source is not provider-classified")

    if str(provider.get("id")) != str(fact["actionId"]):
        raise ValueError("provider action ID mismatch")
    if str(provider.get("bucket")) != "stock_dividends":
        raise ValueError("provider bucket changed")
    if str(provider.get("symbol") or "").upper() != str(fact["ticker"]):
        raise ValueError("provider symbol changed")
    if str(provider.get("ex_date") or "") != str(fact["exDate"]):
        raise ValueError("provider ex date changed")
    if str(provider.get("record_date") or "") != str(fact["recordDate"]):
        raise ValueError("provider record date changed")
    if str(provider.get("payable_date") or "") != str(fact["payableDate"]):
        raise ValueError("provider payable date changed")

    provider_rate = _number(provider.get("rate"))
    evidence_rate = _number(fact["providerRate"])
    quantity = _number(fact["successorSharesPerEntryShare"])
    if provider_rate != evidence_rate or quantity != evidence_rate:
        raise ValueError("stock-dividend quantity factor changed")
    if quantity <= 1:
        raise ValueError("stock-dividend factor must exceed one")

    effective = str(fact["exDate"])
    if not str(row["entrySession"]) < effective <= str(row["targetExitSession"]):
        raise ValueError("stock-dividend ex date outside event horizon")

    if fact["resolutionDecision"] != "TRANSFORMED_HOLDER_CONSIDERATION":
        raise ValueError("stock-dividend decision changed")
    if fact["transformationKind"] != "STOCK_DIVIDEND_QUANTITY":
        raise ValueError("stock-dividend transformation kind changed")
    if fact["resultState"] != "TRANSFORMED_HOLDER_CONSIDERATION":
        raise ValueError("stock-dividend result state changed")
    if str(fact["successorSymbol"]).upper() != str(row["ticker"]).upper():
        raise ValueError("stock-dividend successor symbol changed")
    if _number(fact["cashPerEntryShare"]) != 0:
        raise ValueError("stock-dividend cash term must be zero")
    if not fact.get("primaryEvidence"):
        raise ValueError("stock-dividend primary evidence missing")

    return {
        **_key_object(row),
        "expectedSourceResolutionSource": "provider",
        "effectiveDate": effective,
        "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
        "transformationKind": "STOCK_DIVIDEND_QUANTITY",
        "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol": str(row["ticker"]).upper(),
        "successorSharesPerEntryShare": _format(quantity),
        "cashPerEntryShare": "0",
        "sourceActionIds": [str(fact["actionId"])],
        "basket": [],
        "classificationSource": "VALIDATION_PRIMARY_STOCK_DIVIDEND_TERMS",
        "evidenceClass": "PRIMARY_SEC_STOCK_DIVIDEND_TERMS_MATCH_PROVIDER",
        "primaryEvidenceAccessions": [
            str(item["accession"]) for item in fact["primaryEvidence"]
        ],
        "providerExDate": str(provider["ex_date"]),
        "providerRecordDate": str(provider["record_date"]),
        "providerPayableDate": str(provider["payable_date"]),
    }


def run(
    *,
    scope_path: Path,
    provider_path: Path,
    evidence_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    scope = _load_scope(scope_path)
    evidence = _load_evidence(evidence_path)
    provider = _load_provider(provider_path, set(evidence))

    targets = []
    for row in scope:
        ids = [str(item) for item in row.get("candidateActionIds") or []]
        if len(ids) == 1 and ids[0] in evidence:
            targets.append(row)
    if len(targets) != EXPECTED_TARGET_ROWS:
        raise ValueError("stock-dividend target row count changed")
    if _key_digest(targets) != EXPECTED_TARGET_DIGEST:
        raise ValueError("stock-dividend target key digest changed")

    resolutions = []
    for row in targets:
        action_id = str(row["candidateActionIds"][0])
        resolutions.append(
            _resolution(
                row,
                evidence[action_id],
                provider[action_id],
            )
        )
    resolutions.sort(key=lambda row: (int(row["eventNumber"]), int(row["horizon"])))

    result = {
        "schemaVersion": "1.0.0",
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "STOCK_DIVIDEND_PRIMARY_RESOLUTION_COMPLETE"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": EXPECTED_SOURCE_ROWS,
        "resolvedRows": len(resolutions),
        "remainingUnresolvedRows": EXPECTED_REMAINING_ROWS,
        "resolvedKeySha256": EXPECTED_TARGET_DIGEST,
        "resolutionRows": resolutions,
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
    parser.add_argument("--provider", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        scope_path=args.scope,
        provider_path=args.provider,
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
