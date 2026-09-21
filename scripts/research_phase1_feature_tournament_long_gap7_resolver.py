"""Resolve seven long-gap rows from exact frozen gap/evidence equivalence."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_LONG_GAP_ROWS = 17
EXPECTED_RESOLVED_ROWS = 7
EXPECTED_NEW_PRIMARY_ROWS = 10
B1_CONTRACT_SHA256 = (
    "sha256:88325d71dd9da1f18bdc2c2695933860e087addd586def8b4271ed768d121430"
)


def _assert_boundary(payload: dict[str, Any], *, label: str) -> None:
    required = {
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
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
    return (
        str(row["currentEventNumber"]),
        str(row["ticker"]),
        str(row["horizon"]),
    )


def _gap_tuple(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(row["previousObservedSession"]),
        str(row["firstMissingSession"]),
        str(row["lastMissingSession"]),
        str(row["nextObservedSession"]),
        str(row["maxInternalGapSessions"]),
    )


def _audit_fp(row: dict[str, Any]) -> tuple[str, ...]:
    evidence = row.get("evidenceAudit")
    if not isinstance(evidence, dict):
        raise ValueError("long-gap row missing evidence audit")
    fp = evidence.get("economicFingerprint")
    if not isinstance(fp, list) or len(fp) != 6:
        raise ValueError("long-gap economic fingerprint malformed")
    return tuple(str(value) for value in fp)


def _same_security_resolution(
    row: dict[str, Any],
    *,
    effective_date: str,
    evidence_class: str,
    evidence_source: str,
    gap: dict[str, str],
    supporting_rows: int,
) -> dict[str, Any]:
    fp = _audit_fp(row)
    expected = (
        "SAME_SECURITY_CONTINUITY",
        "",
        "PRICE_CONTINUOUS_ADJUSTED",
        str(row["ticker"]),
        "1",
        "0",
    )
    if fp != expected:
        raise ValueError("same-security long-gap fingerprint changed")
    return {
        "eventNumber": int(row["currentEventNumber"]),
        "issuerCik": str(row["issuerCik"]),
        "ticker": str(row["ticker"]),
        "evaluationSession": str(row["evaluationSession"]),
        "entrySession": str(row["entrySession"]),
        "horizon": int(row["horizon"]),
        "targetExitSession": str(row["targetExitSession"]),
        "expectedSourceResolutionSource": "long_internal_gap",
        "effectiveDate": effective_date,
        "resolutionDecision": "SAME_SECURITY_CONTINUITY",
        "transformationKind": "",
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "successorSymbol": str(row["ticker"]),
        "successorSharesPerEntryShare": "1",
        "cashPerEntryShare": "0",
        "sourceActionIds": [],
        "evidenceClass": evidence_class,
        "evidenceSource": evidence_source,
        "supportingPriorRows": supporting_rows,
        "gapPreviousObservedSession": gap["previousObservedSession"],
        "gapFirstMissingSession": gap["firstMissingSession"],
        "gapLastMissingSession": gap["lastMissingSession"],
        "gapNextObservedSession": gap["nextObservedSession"],
        "maxInternalGapSessions": int(gap["maxInternalGapSessions"]),
    }


def _resolve_multisource(
    row: dict[str, Any],
    gap: dict[str, str],
    b3_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    issuer = str(row["issuerCik"])
    ticker = str(row["ticker"])
    pivot = str(gap["firstMissingSession"])
    matches = [
        item
        for item in b3_rows
        if str(item.get("issuerCik")) == issuer
        and str(item.get("ticker")) == ticker
        and str(item.get("effectiveDate")) == pivot
        and item.get("evidenceClass") == "SEC_MULTI_SOURCE_EXACT_CONTINUITY"
        and item.get("classificationSourceRelease")
        == "research-phase1-b3-residual-multisource-v1"
        and item.get("resolutionDecision") == "SAME_SECURITY_CONTINUITY"
        and item.get("resultState") == "PRICE_CONTINUOUS_ADJUSTED"
        and str(item.get("successorSymbol")) == ticker
        and float(item.get("successorSharesPerEntryShare")) == 1.0
        and float(item.get("cashPerEntryShare")) == 0.0
    ]
    if not matches:
        raise ValueError(
            f"no exact B3 multisource gap-pivot evidence for {ticker} {pivot}"
        )
    return _same_security_resolution(
        row,
        effective_date=pivot,
        evidence_class="CROSS_EVENT_B3_EXACT_GAP_PIVOT",
        evidence_source="research-phase1-b3-residual-multisource-v1",
        gap=gap,
        supporting_rows=len(matches),
    )


def _load_b1_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contractId") != "phase1-b1-security-continuity-resolution-v1":
        raise ValueError("unexpected B1 continuity contract")
    if payload.get("performanceRead") is not False:
        raise ValueError("B1 contract opened performance")
    if payload.get("oosOpened") is not False:
        raise ValueError("B1 contract opened OOS")
    columns = payload["resolutionColumns"]
    rows = [
        dict(zip(columns, values, strict=True))
        for values in payload["resolutions"]
    ]
    if len(rows) != 54:
        raise ValueError("B1 continuity row count changed")
    return rows


def _resolve_cmct(
    row: dict[str, Any],
    gap: dict[str, str],
    b1_rows: list[dict[str, Any]],
    b1_gap_rows: list[dict[str, str]],
) -> dict[str, Any]:
    if str(row["issuerCik"]) != "0000908311" or str(row["ticker"]) != "CMCT":
        raise ValueError("CMCT resolver called for wrong identity")

    stage_gap = _gap_tuple(gap)
    exact_gap_rows = [
        item
        for item in b1_gap_rows
        if item.get("issuerCik") == "0000908311"
        and item.get("ticker") == "CMCT"
        and _gap_tuple(item) == stage_gap
    ]
    if not exact_gap_rows:
        raise ValueError("CMCT Stage-B gap does not match frozen B1 gap")

    resolutions = [
        item
        for item in b1_rows
        if str(item.get("issuerCik")) == "0000908311"
        and str(item.get("ticker")) == "CMCT"
        and item.get("resolutionDecision") == "SAME_SECURITY_CONTINUITY"
        and item.get("resultState") == "PRICE_CONTINUOUS_ADJUSTED"
        and str(item.get("successorSymbol")) == "CMCT"
        and str(item.get("shareQuantityFactor")) in {"1", "1.0"}
        and int(item.get("maxInternalGapSessions") or 0)
        == int(gap["maxInternalGapSessions"])
    ]
    if not resolutions:
        raise ValueError("CMCT B1 same-security evidence missing")

    return _same_security_resolution(
        row,
        effective_date=str(gap["nextObservedSession"]),
        evidence_class="CROSS_EVENT_B1_EXACT_GAP_EQUIVALENCE",
        evidence_source=B1_CONTRACT_SHA256,
        gap=gap,
        supporting_rows=len(resolutions),
    )


def _load_one_sided(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contractId") != "phase1-b3-one-sided-primary-evidence-v1":
        raise ValueError("unexpected one-sided evidence contract")
    _assert_boundary(payload, label="one-sided evidence")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for item in payload.get("identities", []):
        key = (str(item["issuerCik"]), str(item["ticker"]))
        result[key] = item
    return result


def _resolve_lov(
    row: dict[str, Any],
    gap: dict[str, str],
    one_sided: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    fact = one_sided.get(("0001314475", "LOV"))
    if fact is None:
        raise ValueError("LOV primary evidence missing")

    effective = str(fact["effectiveDate"])
    if effective != str(gap["previousObservedSession"]):
        raise ValueError("LOV exchange date is not the final old-security bar")
    if not (
        str(row["entrySession"]) < effective <= str(row["targetExitSession"])
    ):
        raise ValueError("LOV exchange outside Stage-B event horizon")

    fp = _audit_fp(row)
    expected = (
        "TRANSFORMED_HOLDER_CONSIDERATION",
        "ADS_EXCHANGE",
        "TRANSFORMED_HOLDER_CONSIDERATION",
        "LOV",
        "0.1",
        "0",
    )
    if fp != expected:
        raise ValueError("LOV frozen economic fingerprint changed")

    accessions = [
        str(item["accession"])
        for item in fact.get("primaryEvidence", [])
    ]
    if sorted(accessions) != sorted(
        ["0001144204-17-057262", "0001144204-17-055907"]
    ):
        raise ValueError("LOV primary evidence accession set changed")

    return {
        "eventNumber": int(row["currentEventNumber"]),
        "issuerCik": "0001314475",
        "ticker": "LOV",
        "evaluationSession": str(row["evaluationSession"]),
        "entrySession": str(row["entrySession"]),
        "horizon": int(row["horizon"]),
        "targetExitSession": str(row["targetExitSession"]),
        "expectedSourceResolutionSource": "long_internal_gap",
        "effectiveDate": effective,
        "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
        "transformationKind": "ADS_EXCHANGE",
        "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol": "LOV",
        "successorIssuerCik": "0001705338",
        "successorSharesPerEntryShare": "0.1",
        "cashPerEntryShare": "0",
        "sourceActionIds": [],
        "primaryEvidenceAccessions": accessions,
        "evidenceClass": "PRIMARY_SEC_ONE_SIDED_IDENTITY_REUSED_ON_EXACT_BOUNDARY",
        "evidenceSource": "research/b3-one-sided-primary-evidence-v1.json",
        "gapPreviousObservedSession": gap["previousObservedSession"],
        "gapFirstMissingSession": gap["firstMissingSession"],
        "gapLastMissingSession": gap["lastMissingSession"],
        "gapNextObservedSession": gap["nextObservedSession"],
        "maxInternalGapSessions": int(gap["maxInternalGapSessions"]),
    }


def run(
    *,
    long_gap_scope_path: Path,
    stage_gap_path: Path,
    b3_contract_path: Path,
    b1_contract_path: Path,
    b1_gap_path: Path,
    one_sided_evidence_path: Path,
    resolution_output: Path,
    residual_output: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    scope = json.loads(long_gap_scope_path.read_text(encoding="utf-8"))
    _assert_boundary(scope, label="long-gap17")
    required = {
        "status": "PHASE1_FEATURE_TOURNAMENT_LONG_GAP17_SCOPE_FROZEN",
        "residualRows": EXPECTED_LONG_GAP_ROWS,
        "priorSecurityCandidateRows": EXPECTED_RESOLVED_ROWS,
        "newPrimaryEvidenceRows": EXPECTED_NEW_PRIMARY_ROWS,
        "resolutionComplete": False,
        "featureDiscoveryOutcomesOpened": False,
    }
    for key, expected in required.items():
        if scope.get(key) != expected:
            raise ValueError(f"long-gap17 contract mismatch: {key}")

    stage_gaps = _load_csv(stage_gap_path)
    stage_index = {
        (row["eventNumber"], row["ticker"], row["horizon"]): row
        for row in stage_gaps
    }
    if len(stage_index) != 155:
        raise ValueError("Stage-B exact gap diagnostic row count changed")

    b3 = json.loads(b3_contract_path.read_text(encoding="utf-8"))
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
            raise ValueError(f"B3 final contract mismatch: {key}")
    b3_rows = b3["resolutionRows"]

    b1_rows = _load_b1_rows(b1_contract_path)
    b1_gaps = _load_csv(b1_gap_path)
    one_sided = _load_one_sided(one_sided_evidence_path)

    candidates = [
        row
        for row in scope["rows"]
        if row["evidenceAudit"]["category"]
        == "LONG_GAP_PRIOR_SECURITY_CANDIDATE"
    ]
    residual = [
        row
        for row in scope["rows"]
        if row["evidenceAudit"]["category"]
        == "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED"
    ]
    if len(candidates) != EXPECTED_RESOLVED_ROWS:
        raise ValueError("long-gap candidate count changed")
    if len(residual) != EXPECTED_NEW_PRIMARY_ROWS:
        raise ValueError("new-primary residual count changed")

    resolutions: list[dict[str, Any]] = []
    for row in candidates:
        key = _gap_key(row)
        gap = stage_index.get(key)
        if gap is None:
            raise ValueError(f"Stage-B exact gap missing for {key}")
        if int(gap["maxInternalGapSessions"]) != int(
            row["maxInternalGapSessions"]
        ):
            raise ValueError("Stage-B exact gap size changed")

        ticker = str(row["ticker"])
        if ticker == "CKX":
            resolutions.append(_resolve_multisource(row, gap, b3_rows))
        elif ticker == "NSEC":
            resolutions.append(_resolve_multisource(row, gap, b3_rows))
        elif ticker == "CMCT":
            resolutions.append(
                _resolve_cmct(row, gap, b1_rows, b1_gaps)
            )
        elif ticker == "LOV":
            resolutions.append(_resolve_lov(row, gap, one_sided))
        else:
            raise ValueError(f"unexpected long-gap candidate ticker: {ticker}")

    resolutions.sort(key=lambda row: (row["eventNumber"], row["horizon"]))
    identity_counts = Counter(row["ticker"] for row in resolutions)
    if dict(identity_counts) != {
        "CKX": 4,
        "CMCT": 1,
        "LOV": 1,
        "NSEC": 1,
    }:
        raise ValueError("resolved long-gap identity partition changed")

    residual.sort(
        key=lambda row: (
            int(row["currentEventNumber"]),
            int(row["horizon"]),
        )
    )
    residual_counts = Counter(str(row["ticker"]) for row in residual)
    if dict(residual_counts) != {
        "AVGR": 3,
        "HMG": 2,
        "OAS": 3,
        "SNES": 2,
    }:
        raise ValueError("new-primary residual identity partition changed")

    resolution_payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_LONG_GAP7_RESOLVED",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceLongGapRows": EXPECTED_LONG_GAP_ROWS,
        "resolvedRows": len(resolutions),
        "remainingNewPrimaryRows": len(residual),
        "resolvedTickerCounts": dict(sorted(identity_counts.items())),
        "rows": resolutions,
        "resolutionApplied": True,
        "featureDiscoveryOutcomesOpened": False,
    }

    residual_payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_NEW_PRIMARY10_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceLongGapRows": EXPECTED_LONG_GAP_ROWS,
        "longGapRowsResolved": len(resolutions),
        "residualRows": len(residual),
        "tickerCounts": dict(sorted(residual_counts.items())),
        "rows": residual,
        "resolutionComplete": False,
        "featureDiscoveryOutcomesOpened": False,
    }

    resolution_output.parent.mkdir(parents=True, exist_ok=True)
    residual_output.parent.mkdir(parents=True, exist_ok=True)
    resolution_output.write_text(
        json.dumps(resolution_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    residual_output.write_text(
        json.dumps(residual_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return resolution_payload, residual_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--long-gap-scope", type=Path, required=True)
    parser.add_argument("--stage-gaps", type=Path, required=True)
    parser.add_argument("--b3-contract", type=Path, required=True)
    parser.add_argument("--b1-contract", type=Path, required=True)
    parser.add_argument("--b1-gaps", type=Path, required=True)
    parser.add_argument("--one-sided-evidence", type=Path, required=True)
    parser.add_argument("--resolution-output", type=Path, required=True)
    parser.add_argument("--residual-output", type=Path, required=True)
    args = parser.parse_args()

    resolution, residual = run(
        long_gap_scope_path=args.long_gap_scope,
        stage_gap_path=args.stage_gaps,
        b3_contract_path=args.b3_contract,
        b1_contract_path=args.b1_contract,
        b1_gap_path=args.b1_gaps,
        one_sided_evidence_path=args.one_sided_evidence,
        resolution_output=args.resolution_output,
        residual_output=args.residual_output,
    )
    print(
        json.dumps(
            {
                "resolution": {
                    key: value
                    for key, value in resolution.items()
                    if key != "rows"
                },
                "residual": {
                    key: value
                    for key, value in residual.items()
                    if key != "rows"
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
