"""Audit reusable frozen continuity evidence for the 34-row post-POPE residual."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

EXPECTED_RESIDUAL_ROWS = 34
EXPECTED_PROVIDER_ROWS = 17
EXPECTED_PROVIDER_REUSABLE_ROWS = 17
EXPECTED_LONG_GAP_ROWS = 17
EXPECTED_LONG_GAP_PRIOR_CANDIDATES = 7
EXPECTED_NEW_PRIMARY_ROWS = 10

KEY_FIELDS = (
    "issuerCik",
    "ticker",
    "evaluationSession",
    "entrySession",
    "horizon",
    "targetExitSession",
)


def _assert_boundary(payload: dict[str, Any], *, label: str) -> None:
    required = {
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"{label} boundary mismatch: {key}")


def _key(row: dict[str, Any], *, event_field: str) -> tuple[str, ...]:
    return (
        str(row[event_field]),
        str(row["horizon"]),
    )


def _semantic_key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row[field]) for field in KEY_FIELDS)


def _action_ids(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(sorted(str(item) for item in value if item))
    return tuple(
        sorted(
            item.strip()
            for item in str(value or "").split(";")
            if item.strip()
        )
    )


def _number(value: Any) -> str:
    number = Decimal(str(0 if value in (None, "") else value))
    text = format(number.normalize(), "f")
    return "0" if text in {"", "-0"} else text


def _b3_fingerprint(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(row.get("resolutionDecision") or ""),
        str(row.get("transformationKind") or ""),
        str(row.get("resultState") or ""),
        str(row.get("successorSymbol") or ""),
        _number(row.get("successorSharesPerEntryShare", 1)),
        _number(row.get("cashPerEntryShare", 0)),
    )


def _b1_fingerprint(row: dict[str, Any]) -> tuple[str, ...]:
    if row.get("transformationKind") != "STOCK_DIVIDEND_QUANTITY":
        raise ValueError("B1 action-level fallback is restricted to stock dividends")
    return (
        str(row.get("resolutionDecision") or ""),
        str(row.get("transformationKind") or ""),
        str(row.get("resultState") or ""),
        str(row.get("successorSymbol") or ""),
        _number(row.get("shareQuantityFactor", 1)),
        "0",
    )


def _load_b1(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contractId") != "phase1-b1-security-continuity-resolution-v1":
        raise ValueError("unexpected B1 continuity contract")
    if payload.get("performanceRead") is not False:
        raise ValueError("B1 continuity contract opened performance")
    columns = payload["resolutionColumns"]
    rows = [
        dict(zip(columns, values, strict=True))
        for values in payload["resolutions"]
    ]
    if len(rows) != 54:
        raise ValueError("B1 continuity row count changed")
    return rows


def _provider_match(
    row: dict[str, Any],
    unresolved_row: dict[str, Any],
    b3_rows: list[dict[str, Any]],
    b1_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    action_ids = _action_ids(unresolved_row.get("candidateActionIds"))
    if not action_ids:
        raise ValueError("provider residual row has no candidate action IDs")

    issuer = str(row["issuerCik"])
    ticker = str(row["ticker"])

    b3_matches = [
        item
        for item in b3_rows
        if str(item.get("issuerCik")) == issuer
        and str(item.get("ticker")) == ticker
        and _action_ids(item.get("sourceActionIds")) == action_ids
    ]
    if b3_matches:
        fingerprints = {_b3_fingerprint(item) for item in b3_matches}
        if len(fingerprints) != 1:
            raise ValueError("B3 action-level evidence is economically inconsistent")
        example = b3_matches[0]
        return {
            "category": "PROVIDER_ACTION_REUSE_B3",
            "actionIds": list(action_ids),
            "priorMatchCount": len(b3_matches),
            "economicFingerprint": list(next(iter(fingerprints))),
            "effectiveDate": str(example.get("effectiveDate") or ""),
            "evidenceClass": str(example.get("evidenceClass") or ""),
            "sourceRelease": str(
                example.get("classificationSourceRelease") or ""
            ),
        }

    b1_matches = [
        item
        for item in b1_rows
        if str(item.get("issuerCik")) == issuer
        and str(item.get("ticker")) == ticker
        and _action_ids(item.get("sourceActionIds")) == action_ids
    ]
    if b1_matches:
        fingerprints = {_b1_fingerprint(item) for item in b1_matches}
        if len(fingerprints) != 1:
            raise ValueError("B1 action-level evidence is economically inconsistent")
        example = b1_matches[0]
        return {
            "category": "PROVIDER_ACTION_REUSE_B1_STOCK_DIVIDEND",
            "actionIds": list(action_ids),
            "priorMatchCount": len(b1_matches),
            "economicFingerprint": list(next(iter(fingerprints))),
            "effectiveDate": str(example.get("effectiveDate") or ""),
            "evidenceClass": "PRIOR_FROZEN_B1_STOCK_DIVIDEND_TERMS",
            "sourceRelease": "research/b1-security-continuity-resolution-v1.json",
        }

    return {
        "category": "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED",
        "actionIds": list(action_ids),
        "priorMatchCount": 0,
    }


def _long_gap_match(
    row: dict[str, Any],
    b3_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    issuer = str(row["issuerCik"])
    ticker = str(row["ticker"])
    matches = [
        item
        for item in b3_rows
        if str(item.get("issuerCik")) == issuer
        and str(item.get("ticker")) == ticker
    ]
    if not matches:
        return {
            "category": "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED",
            "priorMatchCount": 0,
        }

    fingerprints = {_b3_fingerprint(item) for item in matches}
    if len(fingerprints) != 1:
        return {
            "category": "LONG_GAP_PRIOR_SECURITY_CONFLICT",
            "priorMatchCount": len(matches),
            "economicFingerprints": [
                list(item)
                for item in sorted(fingerprints)
            ],
        }

    return {
        "category": "LONG_GAP_PRIOR_SECURITY_CANDIDATE",
        "priorMatchCount": len(matches),
        "economicFingerprint": list(next(iter(fingerprints))),
        "effectiveDates": sorted(
            {
                str(item.get("effectiveDate") or "")
                for item in matches
                if item.get("effectiveDate")
            }
        ),
        "evidenceClasses": sorted(
            {
                str(item.get("evidenceClass") or "")
                for item in matches
                if item.get("evidenceClass")
            }
        ),
        "sourceReleases": sorted(
            {
                str(item.get("classificationSourceRelease") or "")
                for item in matches
                if item.get("classificationSourceRelease")
            }
        ),
    }


def run(
    *,
    residual34_path: Path,
    unresolved_path: Path,
    b3_contract_path: Path,
    b1_contract_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    residual = json.loads(residual34_path.read_text(encoding="utf-8"))
    unresolved = json.loads(unresolved_path.read_text(encoding="utf-8"))
    b3 = json.loads(b3_contract_path.read_text(encoding="utf-8"))
    b1_rows = _load_b1(b1_contract_path)

    _assert_boundary(residual, label="residual34")
    _assert_boundary(unresolved, label="unresolved")

    b3_required = {
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "classifiedRows": 264,
        "finalResolutionContractCreated": True,
        "correctedPerformanceOpened": False,
    }
    for key, expected in b3_required.items():
        if b3.get(key) != expected:
            raise ValueError(f"B3 final continuity contract mismatch: {key}")

    residual_required = {
        "status": "PHASE1_FEATURE_TOURNAMENT_RESIDUAL34_SCOPE_FROZEN",
        "sourceResidual35Rows": 35,
        "safePriorEvidenceRows": 175,
        "popeAdjudicatedRows": 1,
        "residualRows": EXPECTED_RESIDUAL_ROWS,
        "resolutionComplete": False,
        "featureDiscoveryOutcomesOpened": False,
    }
    for key, expected in residual_required.items():
        if residual.get(key) != expected:
            raise ValueError(f"residual34 contract mismatch: {key}")

    if unresolved.get("unresolvedRows") != 210:
        raise ValueError("Stage-B unresolved scope row count changed")
    unresolved_index = {
        _key(item, event_field="eventNumber"): item
        for item in unresolved["rows"]
    }
    if len(unresolved_index) != 210:
        raise ValueError("Stage-B unresolved scope key is not unique")

    b3_rows = b3.get("resolutionRows")
    if not isinstance(b3_rows, list) or len(b3_rows) != 264:
        raise ValueError("B3 final continuity contract changed")

    source_rows = list(residual["rows"])
    if len(source_rows) != EXPECTED_RESIDUAL_ROWS:
        raise ValueError("residual34 row count changed")
    if any(
        item.get("matchStatus") != "NO_PRIOR_EVIDENCE_MATCH"
        for item in source_rows
    ):
        raise ValueError("residual34 contains a non-unmatched row")

    audited: list[dict[str, Any]] = []
    for row in source_rows:
        unresolved_row = unresolved_index[
            _key(row, event_field="currentEventNumber")
        ]
        if str(unresolved_row["issuerCik"]) != str(row["issuerCik"]):
            raise ValueError("residual/unresolved issuer mismatch")
        if str(unresolved_row["ticker"]) != str(row["ticker"]):
            raise ValueError("residual/unresolved ticker mismatch")

        source = str(row["currentResolutionSource"])
        if source == "provider":
            evidence = _provider_match(
                row,
                unresolved_row,
                b3_rows,
                b1_rows,
            )
        elif source == "long_internal_gap":
            evidence = _long_gap_match(row, b3_rows)
        else:
            raise ValueError(f"unexpected residual source: {source}")

        audited.append(
            {
                **row,
                "candidateActionIds": list(
                    _action_ids(unresolved_row.get("candidateActionIds"))
                ),
                "candidateActionTypes": sorted(
                    item.strip()
                    for item in str(
                        unresolved_row.get("candidateActionTypes") or ""
                    ).split(";")
                    if item.strip()
                ),
                "maxInternalGapSessions": int(
                    unresolved_row.get("maxInternalGapSessions") or 0
                ),
                "evidenceAudit": evidence,
            }
        )

    categories = Counter(
        item["evidenceAudit"]["category"]
        for item in audited
    )
    provider_rows = sum(
        1
        for item in audited
        if item["currentResolutionSource"] == "provider"
    )
    long_gap_rows = len(audited) - provider_rows

    expected_categories = {
        "PROVIDER_ACTION_REUSE_B3": 16,
        "PROVIDER_ACTION_REUSE_B1_STOCK_DIVIDEND": 1,
        "LONG_GAP_PRIOR_SECURITY_CANDIDATE": 7,
        "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED": 10,
    }
    if dict(categories) != expected_categories:
        raise ValueError(
            f"residual evidence partition changed: {dict(categories)}"
        )
    if provider_rows != EXPECTED_PROVIDER_ROWS:
        raise ValueError("provider residual count changed")
    if long_gap_rows != EXPECTED_LONG_GAP_ROWS:
        raise ValueError("long-gap residual count changed")

    new_primary = [
        item
        for item in audited
        if item["evidenceAudit"]["category"].endswith(
            "NEW_PRIMARY_EVIDENCE_REQUIRED"
        )
    ]
    new_primary_tickers = Counter(item["ticker"] for item in new_primary)
    if dict(new_primary_tickers) != {
        "HMG": 2,
        "OAS": 3,
        "AVGR": 3,
        "SNES": 2,
    }:
        raise ValueError("new-primary ticker partition changed")

    payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_RESIDUAL_EVIDENCE_AUDIT_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": EXPECTED_RESIDUAL_ROWS,
        "auditedRows": len(audited),
        "providerRows": provider_rows,
        "providerActionReusableRows": (
            categories["PROVIDER_ACTION_REUSE_B3"]
            + categories["PROVIDER_ACTION_REUSE_B1_STOCK_DIVIDEND"]
        ),
        "longGapRows": long_gap_rows,
        "longGapPriorSecurityCandidateRows": categories[
            "LONG_GAP_PRIOR_SECURITY_CANDIDATE"
        ],
        "newPrimaryEvidenceRows": len(new_primary),
        "categoryCounts": dict(sorted(categories.items())),
        "newPrimaryEvidenceTickerCounts": dict(
            sorted(new_primary_tickers.items())
        ),
        "rows": sorted(
            audited,
            key=lambda item: (
                int(item["currentEventNumber"]),
                int(item["horizon"]),
            ),
        ),
        "auditOnly": True,
        "resolutionApplied": False,
        "featureDiscoveryOutcomesOpened": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--residual34", type=Path, required=True)
    parser.add_argument("--unresolved", type=Path, required=True)
    parser.add_argument("--b3-contract", type=Path, required=True)
    parser.add_argument("--b1-contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = run(
        residual34_path=args.residual34,
        unresolved_path=args.unresolved,
        b3_contract_path=args.b3_contract,
        b1_contract_path=args.b1_contract,
        output_path=args.output,
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "rows"},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
