"""Resolve the final ten F2 validation long-gap rows from primary SEC evidence."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_ROWS = 10
EXPECTED_SCOPE_KEY = (
    "sha256:bba1bd1512a8ab6b8009e477689e189c2bd5ebf3033801f50753b023d5d6a426"
)
EXPECTED_SCOPE_ASSET_DIGEST = (
    "sha256:a1db8f513116f57d30a4ab07c32ccbc66a6868c52cd58250f240703011832f22"
)
EXPECTED_GAP_ASSET_DIGEST = (
    "sha256:1e7d783cee4bdd3a5c64fc42cb0cc7a8e1a41e14f36220809aa0ba5d80af75b7"
)
EXPECTED_EVIDENCE_CONTRACT = (
    "phase1-feature-tournament-validation-long-gap10-primary-evidence-v1"
)
EXPECTED_TICKERS = {
    "ACON": 1,
    "APMIU": 1,
    "GRCY": 1,
    "JAGX": 1,
    "KACLU": 1,
    "MCAGU": 1,
    "NETC.U": 1,
    "NVVE": 1,
    "ROCGU": 1,
    "UPTD": 1,
}
UNIT_TICKERS = {"ROCGU", "APMIU", "MCAGU", "NETC.U", "KACLU"}
EXPECTED_GAPS = {
    ("2452", "ROCGU", "126"): (
        "2022-01-12",
        "2022-01-13",
        "2022-02-04",
        "2022-02-07",
        16,
    ),
    ("2694", "APMIU", "126"): (
        "2021-11-29",
        "2021-11-30",
        "2021-12-14",
        "2021-12-15",
        11,
    ),
    ("3444", "GRCY", "126"): (
        "2021-12-27",
        "2021-12-28",
        "2022-01-10",
        "2022-01-11",
        10,
    ),
    ("3744", "MCAGU", "126"): (
        "2022-03-04",
        "2022-03-07",
        "2022-03-21",
        "2022-03-22",
        11,
    ),
    ("3928", "NETC.U", "126"): (
        "2022-03-15",
        "2022-03-16",
        "2022-04-11",
        "2022-04-12",
        19,
    ),
    ("4503", "KACLU", "126"): (
        "2022-03-16",
        "2022-03-17",
        "2022-04-05",
        "2022-04-06",
        14,
    ),
    ("5728", "UPTD", "126"): (
        "2022-08-01",
        "2022-08-02",
        "2022-08-19",
        "2022-08-22",
        14,
    ),
    ("5897", "JAGX", "126"): (
        "2022-04-04",
        "2022-04-05",
        "2022-06-08",
        "2022-06-09",
        45,
    ),
    ("6091", "ACON", "126"): (
        "2022-05-19",
        "2022-05-20",
        "2022-06-14",
        "2022-06-15",
        17,
    ),
    ("7274", "NVVE", "126"): (
        "2022-07-05",
        "2022-07-06",
        "2022-07-26",
        "2022-07-27",
        15,
    ),
}
EXPECTED_ACCESSIONS = {
    "ROCGU": {"0001410578-22-000842", "0001410578-22-002450"},
    "APMIU": {"0001140361-21-033289", "0001140361-22-012282"},
    "GRCY": {"0001410578-22-000763", "0001104659-22-047927"},
    "MCAGU": {"0001829126-21-015085", "0001829126-22-010980"},
    "NETC.U": {"0001104659-22-001979", "0001558370-22-008586"},
    "KACLU": {"0001493152-22-014800", "0001493152-22-028332"},
    "UPTD": {"0001104659-22-083036", "0001575872-22-000912"},
    "JAGX": {"0001558370-22-007961", "0001558370-22-013831"},
    "ACON": {"0001683168-22-002903", "0001654954-22-011263"},
    "NVVE": {
        "0001836875-22-000020",
        "0001836875-22-000062",
        "0001836875-22-000115",
    },
}


def _assert_boundary(payload: dict[str, Any], *, label: str) -> None:
    required = {
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"{label} boundary mismatch: {key}")


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def _gap_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row["eventNumber"]), str(row["ticker"]), str(row["horizon"]))


def _identity_index(evidence: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    identities = evidence.get("identities")
    if not isinstance(identities, list) or len(identities) != EXPECTED_ROWS:
        raise ValueError("primary-evidence identity count changed")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for item in identities:
        key = (str(item["issuerCik"]), str(item["ticker"]))
        if key in result:
            raise ValueError(f"duplicate primary-evidence identity: {key}")
        result[key] = item
    return result


def _validate_gap(row: dict[str, Any], gap: dict[str, str]) -> None:
    key = _gap_key(row)
    expected = EXPECTED_GAPS.get(key)
    if expected is None:
        raise ValueError(f"unexpected residual-10 gap key: {key}")
    observed = (
        gap["previousObservedSession"],
        gap["firstMissingSession"],
        gap["lastMissingSession"],
        gap["nextObservedSession"],
        int(gap["maxInternalGapSessions"]),
    )
    if observed != expected:
        raise ValueError(f"frozen gap tuple changed for {key}: {observed}")
    if str(gap["issuerCik"]) != str(row["issuerCik"]):
        raise ValueError(f"gap issuer changed for {key}")
    if int(row["maxInternalGapSessions"]) != expected[4]:
        raise ValueError(f"scope gap size changed for {key}")


def _validate_identity(row: dict[str, Any], item: dict[str, Any]) -> None:
    ticker = str(row["ticker"])
    issuer = str(row["issuerCik"])
    required = {
        "resolutionDecision": "SAME_SECURITY_CONTINUITY",
        "transformationKind": "",
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "successorIssuerCik": issuer,
        "successorSymbol": ticker,
        "successorSharesPerEntryShare": 1,
        "cashPerEntryShare": 0,
        "effectiveDatePolicy": "NEXT_OBSERVED_SESSION_AFTER_FROZEN_GAP",
    }
    for key, expected in required.items():
        if item.get(key) != expected:
            raise ValueError(f"{ticker} primary-evidence contract changed: {key}")

    security_kind = str(item.get("securityKind"))
    if ticker in UNIT_TICKERS:
        if security_kind != "SPAC_UNIT":
            raise ValueError(f"{ticker} no longer classified as the original SPAC unit")
        if not item.get("unitComposition"):
            raise ValueError(f"{ticker} unit composition missing")
    elif security_kind not in {"COMMON_STOCK", "ORDINARY_SHARE"}:
        raise ValueError(f"{ticker} common-security kind changed")

    accessions = {
        str(source.get("accession"))
        for source in item.get("primaryEvidence", [])
        if source.get("accession")
    }
    if accessions != EXPECTED_ACCESSIONS[ticker]:
        raise ValueError(f"{ticker} primary-evidence accession set changed")


def _resolution(
    row: dict[str, Any],
    gap: dict[str, str],
    item: dict[str, Any],
) -> dict[str, Any]:
    return {
        "eventNumber": int(row["eventNumber"]),
        "issuerCik": str(row["issuerCik"]),
        "ticker": str(row["ticker"]),
        "evaluationSession": str(row["evaluationSession"]),
        "entrySession": str(row["entrySession"]),
        "horizon": int(row["horizon"]),
        "targetExitSession": str(row["targetExitSession"]),
        "expectedSourceResolutionSource": "long_internal_gap",
        "effectiveDate": str(gap["nextObservedSession"]),
        "resolutionDecision": "SAME_SECURITY_CONTINUITY",
        "transformationKind": "",
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "successorIssuerCik": str(row["issuerCik"]),
        "successorSymbol": str(row["ticker"]),
        "successorSharesPerEntryShare": "1",
        "cashPerEntryShare": "0",
        "sourceActionIds": [],
        "evidenceClass": str(item["evidenceClass"]),
        "evidenceContractId": EXPECTED_EVIDENCE_CONTRACT,
        "classificationSource": "VALIDATION_PRIMARY_SEC_EXACT_GAP_BRACKETING",
        "primaryEvidenceAccessions": sorted(EXPECTED_ACCESSIONS[str(row["ticker"])]),
        "gapPreviousObservedSession": gap["previousObservedSession"],
        "gapFirstMissingSession": gap["firstMissingSession"],
        "gapLastMissingSession": gap["lastMissingSession"],
        "gapNextObservedSession": gap["nextObservedSession"],
        "maxInternalGapSessions": int(gap["maxInternalGapSessions"]),
    }


def run(
    *,
    scope_path: Path,
    gap_path: Path,
    evidence_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    _assert_boundary(scope, label="residual-10 scope")
    _assert_boundary(evidence, label="long-gap10 evidence")

    expected_scope = {
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "RESIDUAL10_LONG_GAP_SCOPE_FROZEN"
        ),
        "residualRows": EXPECTED_ROWS,
        "scopeKeySha256": EXPECTED_SCOPE_KEY,
        "resolutionComplete": False,
    }
    for key, expected in expected_scope.items():
        if scope.get(key) != expected:
            raise ValueError(f"residual-10 scope mismatch: {key}")

    if set(scope.get("tickers") or []) != set(EXPECTED_TICKERS):
        raise ValueError("residual-10 ticker set changed")

    rows = scope.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_ROWS:
        raise ValueError("residual-10 row count changed")
    ticker_counts = Counter(str(row["ticker"]) for row in rows)
    if dict(sorted(ticker_counts.items())) != EXPECTED_TICKERS:
        raise ValueError("residual-10 ticker partition changed")

    for row in rows:
        audit = row.get("evidenceAudit") or {}
        if audit.get("category") != "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED":
            raise ValueError("residual-10 contains a non-long-gap row")
        if row.get("candidateActionIds") or row.get("candidateActionTypes"):
            raise ValueError("residual-10 unexpectedly contains provider action")

    if evidence.get("contractId") != EXPECTED_EVIDENCE_CONTRACT:
        raise ValueError("unexpected primary-evidence contract")
    source = evidence.get("sourceScope")
    gap_source = evidence.get("gapSource")
    if not isinstance(source, dict) or not isinstance(gap_source, dict):
        raise ValueError("primary-evidence source metadata missing")
    if source.get("sha256") != EXPECTED_SCOPE_ASSET_DIGEST:
        raise ValueError("primary-evidence scope asset digest changed")
    if source.get("scopeKeySha256") != EXPECTED_SCOPE_KEY:
        raise ValueError("primary-evidence scope-key digest changed")
    if gap_source.get("sha256") != EXPECTED_GAP_ASSET_DIGEST:
        raise ValueError("primary-evidence gap asset digest changed")

    gaps = _load_csv(gap_path)
    if len(gaps) != 11:
        raise ValueError("validation gap diagnostic row count changed")
    gap_index = {_gap_key(row): row for row in gaps}

    identities = _identity_index(evidence)
    resolved: list[dict[str, Any]] = []
    for row in rows:
        key = _gap_key(row)
        gap = gap_index.get(key)
        if gap is None:
            raise ValueError(f"exact validation gap missing: {key}")
        _validate_gap(row, gap)

        identity_key = (str(row["issuerCik"]), str(row["ticker"]))
        item = identities.get(identity_key)
        if item is None:
            raise ValueError(f"primary-evidence identity missing: {identity_key}")
        _validate_identity(row, item)
        resolved.append(_resolution(row, gap, item))

    resolved.sort(key=lambda item: int(item["eventNumber"]))
    result_counts = Counter(str(item["resultState"]) for item in resolved)
    if dict(result_counts) != {"PRICE_CONTINUOUS_ADJUSTED": EXPECTED_ROWS}:
        raise ValueError("long-gap10 result-state partition changed")

    payload = {
        "schemaVersion": "1.0.0",
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "LONG_GAP10_PRIMARY_RESOLUTION_COMPLETE"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": EXPECTED_ROWS,
        "resolvedRows": len(resolved),
        "remainingUnresolvedRows": 0,
        "tickerCounts": dict(sorted(ticker_counts.items())),
        "resultStateCounts": dict(sorted(result_counts.items())),
        "resolutionRows": resolved,
        "resolutionComplete": True,
        "finalValidationContinuityContractCreated": False,
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
    parser.add_argument("--gaps", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        scope_path=args.scope,
        gap_path=args.gaps,
        evidence_path=args.evidence,
        output_path=args.output,
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "resolutionRows"},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
