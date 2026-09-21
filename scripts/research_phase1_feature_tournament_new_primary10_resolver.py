"""Resolve the final ten Stage-B continuity rows from frozen primary SEC evidence."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_ROWS = 10
EXPECTED_TICKERS = {"AVGR": 3, "HMG": 2, "OAS": 3, "SNES": 2}
EXPECTED_EVIDENCE_CONTRACT = "phase1-feature-tournament-new-primary10-evidence-v1"

EXPECTED_GAPS = {
    ("1373", "AVGR", "63"): ("2016-05-03", "2016-05-04", "2016-05-31", "2016-06-01", 19),
    ("1373", "AVGR", "126"): ("2016-05-03", "2016-05-04", "2016-05-31", "2016-06-01", 19),
    ("1373", "AVGR", "252"): ("2016-05-03", "2016-05-04", "2016-05-31", "2016-06-01", 19),
    ("8974", "SNES", "126"): ("2018-04-18", "2018-04-19", "2018-05-04", "2018-05-07", 12),
    ("8974", "SNES", "252"): ("2018-04-18", "2018-04-19", "2018-05-04", "2018-05-07", 12),
    ("21896", "HMG", "126"): ("2020-09-21", "2020-09-22", "2020-10-07", "2020-10-08", 12),
    ("21896", "HMG", "252"): ("2021-05-20", "2021-05-21", "2021-06-10", "2021-06-11", 14),
    ("23221", "OAS", "63"): ("2020-10-09", "2020-10-12", "2020-11-19", "2020-11-20", 29),
    ("23221", "OAS", "126"): ("2020-10-09", "2020-10-12", "2020-11-19", "2020-11-20", 29),
    ("23221", "OAS", "252"): ("2020-10-09", "2020-10-12", "2020-11-19", "2020-11-20", 29),
}


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


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def _gap_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row["currentEventNumber"]), str(row["ticker"]), str(row["horizon"]))


def _validate_gap(row: dict[str, Any], gap: dict[str, str]) -> None:
    key = _gap_key(row)
    expected = EXPECTED_GAPS.get(key)
    if expected is None:
        raise ValueError(f"unexpected final10 gap key: {key}")
    observed = (
        gap["previousObservedSession"],
        gap["firstMissingSession"],
        gap["lastMissingSession"],
        gap["nextObservedSession"],
        int(gap["maxInternalGapSessions"]),
    )
    if observed != expected:
        raise ValueError(f"frozen gap tuple changed for {key}: {observed}")
    if int(row["maxInternalGapSessions"]) != expected[4]:
        raise ValueError(f"scope gap size changed for {key}")


def _identity_index(evidence: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    identities = evidence.get("identities")
    if not isinstance(identities, list) or len(identities) != 4:
        raise ValueError("primary evidence identity count changed")
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for item in identities:
        key = (str(item["issuerCik"]), str(item["ticker"]))
        if key in index:
            raise ValueError("duplicate primary evidence identity")
        index[key] = item
    return index


def _assert_accessions(item: dict[str, Any], expected: set[str]) -> None:
    accessions = {
        str(source.get("accession"))
        for source in item.get("primaryEvidence", [])
        if source.get("accession")
    }
    if accessions != expected:
        raise ValueError(
            f"primary evidence accession set changed for {item.get('ticker')}: {accessions}"
        )


def _same_security_resolution(
    row: dict[str, Any],
    gap: dict[str, str],
    item: dict[str, Any],
) -> dict[str, Any]:
    ticker = str(row["ticker"])
    issuer = str(row["issuerCik"])
    if item.get("resolutionDecision") != "SAME_SECURITY_CONTINUITY":
        raise ValueError(f"{ticker} evidence no longer says same-security")
    if item.get("resultState") != "PRICE_CONTINUOUS_ADJUSTED":
        raise ValueError(f"{ticker} result state changed")
    if str(item.get("successorIssuerCik")) != issuer:
        raise ValueError(f"{ticker} successor issuer changed")
    if str(item.get("successorSymbol")) != ticker:
        raise ValueError(f"{ticker} successor symbol changed")
    if float(item.get("successorSharesPerEntryShare")) != 1.0:
        raise ValueError(f"{ticker} quantity factor changed")
    if float(item.get("cashPerEntryShare")) != 0.0:
        raise ValueError(f"{ticker} cash term changed")

    return {
        "eventNumber": int(row["currentEventNumber"]),
        "issuerCik": issuer,
        "ticker": ticker,
        "evaluationSession": str(row["evaluationSession"]),
        "entrySession": str(row["entrySession"]),
        "horizon": int(row["horizon"]),
        "targetExitSession": str(row["targetExitSession"]),
        "expectedSourceResolutionSource": "long_internal_gap",
        "effectiveDate": str(gap["nextObservedSession"]),
        "resolutionDecision": "SAME_SECURITY_CONTINUITY",
        "transformationKind": "",
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "successorIssuerCik": issuer,
        "successorSymbol": ticker,
        "successorSharesPerEntryShare": "1",
        "cashPerEntryShare": "0",
        "sourceActionIds": [],
        "evidenceClass": str(item["evidenceClass"]),
        "evidenceContractId": EXPECTED_EVIDENCE_CONTRACT,
        "primaryEvidenceAccessions": [
            str(source["accession"])
            for source in item.get("primaryEvidence", [])
            if source.get("accession")
        ],
        "gapPreviousObservedSession": gap["previousObservedSession"],
        "gapFirstMissingSession": gap["firstMissingSession"],
        "gapLastMissingSession": gap["lastMissingSession"],
        "gapNextObservedSession": gap["nextObservedSession"],
        "maxInternalGapSessions": int(gap["maxInternalGapSessions"]),
    }


def _oas_resolution(
    row: dict[str, Any],
    gap: dict[str, str],
    item: dict[str, Any],
) -> dict[str, Any]:
    if str(item.get("effectiveDate")) != "2020-11-19":
        raise ValueError("OAS emergence effective date changed")
    if gap["lastMissingSession"] != "2020-11-19":
        raise ValueError("OAS cancellation date no longer aligns with gap end")
    required = {
        "resolutionDecision": "DISCONTINUOUS_NO_COMPLETE_VALUATION",
        "transformationKind": "BANKRUPTCY_REORG_UNVALUED_WARRANT",
        "resultState": "DISCONTINUOUS_NO_COMPLETE_VALUATION",
        "successorSymbol": "",
        "successorSharesPerEntryShare": 0,
        "cashPerEntryShare": 0,
    }
    for key, expected in required.items():
        if item.get(key) != expected:
            raise ValueError(f"OAS primary evidence contract changed: {key}")

    valuation = item.get("valuationPolicy")
    if not isinstance(valuation, dict):
        raise ValueError("OAS valuation policy missing")
    precedent = valuation.get("precedent")
    if not isinstance(precedent, dict):
        raise ValueError("OAS valuation precedent missing")
    if precedent.get("b3ResultState") != "DISCONTINUOUS_NO_COMPLETE_VALUATION":
        raise ValueError("OAS discontinuity precedent changed")
    if precedent.get("b3TransformationKind") != (
        "MULTI_LEG_UNIT_SEPARATION_UNVALUED_WARRANT"
    ):
        raise ValueError("OAS warrant precedent changed")

    return {
        "eventNumber": int(row["currentEventNumber"]),
        "issuerCik": "0001486159",
        "ticker": "OAS",
        "evaluationSession": str(row["evaluationSession"]),
        "entrySession": str(row["entrySession"]),
        "horizon": int(row["horizon"]),
        "targetExitSession": str(row["targetExitSession"]),
        "expectedSourceResolutionSource": "long_internal_gap",
        "effectiveDate": "2020-11-19",
        "resolutionDecision": "DISCONTINUOUS_NO_COMPLETE_VALUATION",
        "transformationKind": "BANKRUPTCY_REORG_UNVALUED_WARRANT",
        "resultState": "DISCONTINUOUS_NO_COMPLETE_VALUATION",
        "successorIssuerCik": "0001486159",
        "successorSymbol": "",
        "successorSharesPerEntryShare": "0",
        "cashPerEntryShare": "0",
        "sourceActionIds": [],
        "evidenceClass": str(item["evidenceClass"]),
        "evidenceContractId": EXPECTED_EVIDENCE_CONTRACT,
        "primaryEvidenceAccessions": sorted(
            {
                str(source["accession"])
                for source in item.get("primaryEvidence", [])
                if source.get("accession")
            }
        ),
        "holderConsideration": "PRO_RATA_REORGANIZATION_WARRANTS",
        "warrantAggregateIssued": 1621622,
        "warrantExerciseSharesPerWarrant": 1,
        "initialWarrantExercisePrice": 94.57,
        "gapPreviousObservedSession": gap["previousObservedSession"],
        "gapFirstMissingSession": gap["firstMissingSession"],
        "gapLastMissingSession": gap["lastMissingSession"],
        "gapNextObservedSession": gap["nextObservedSession"],
        "maxInternalGapSessions": int(gap["maxInternalGapSessions"]),
    }


def run(
    *,
    scope_path: Path,
    stage_gap_path: Path,
    evidence_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    _assert_boundary(scope, label="new-primary10 scope")
    _assert_boundary(evidence, label="new-primary10 evidence")

    required_scope = {
        "status": "PHASE1_FEATURE_TOURNAMENT_NEW_PRIMARY10_SCOPE_FROZEN",
        "sourceLongGapRows": 17,
        "longGapRowsResolved": 7,
        "residualRows": EXPECTED_ROWS,
        "tickerCounts": EXPECTED_TICKERS,
        "resolutionComplete": False,
        "featureDiscoveryOutcomesOpened": False,
    }
    for key, expected in required_scope.items():
        if scope.get(key) != expected:
            raise ValueError(f"new-primary10 scope mismatch: {key}")

    if evidence.get("contractId") != EXPECTED_EVIDENCE_CONTRACT:
        raise ValueError("unexpected primary evidence contract")
    source_scope = evidence.get("sourceScope")
    if not isinstance(source_scope, dict):
        raise ValueError("primary evidence source scope missing")
    if source_scope.get("sha256") != (
        "sha256:b508811617035eb569d359ee9f5cad97f403f8bd0e51e2413150eaf44630a936"
    ):
        raise ValueError("primary evidence source-scope digest changed")

    rows = scope.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_ROWS:
        raise ValueError("new-primary10 row count changed")
    counts = Counter(str(row["ticker"]) for row in rows)
    if dict(counts) != EXPECTED_TICKERS:
        raise ValueError("new-primary10 ticker partition changed")

    gaps = _load_csv(stage_gap_path)
    gap_index = {
        (row["eventNumber"], row["ticker"], row["horizon"]): row
        for row in gaps
    }
    if len(gap_index) != 155:
        raise ValueError("Stage-B gap diagnostic row count changed")

    identities = _identity_index(evidence)
    _assert_accessions(
        identities[("0001506928", "AVGR")],
        {
            "0001104659-16-119209",
            "0001104659-16-125911",
            "0001104659-16-137123",
        },
    )
    _assert_accessions(
        identities[("0001680378", "SNES")],
        {
            "0001615774-18-002215",
            "0001615774-18-003065",
            "0001615774-18-004225",
            "0001615774-18-008053",
        },
    )
    _assert_accessions(
        identities[("0000311817", "HMG")],
        {
            "0001575872-20-000224",
            "0001575872-20-000302",
            "0001575872-21-000083",
            "0001575872-21-000191",
        },
    )
    _assert_accessions(
        identities[("0001486159", "OAS")],
        {
            "0001486159-20-000089",
            "0001486159-20-000115",
            "0001486159-21-000017",
        },
    )

    resolved: list[dict[str, Any]] = []
    for row in rows:
        key = _gap_key(row)
        gap = gap_index.get(key)
        if gap is None:
            raise ValueError(f"exact Stage-B gap missing: {key}")
        _validate_gap(row, gap)

        identity_key = (str(row["issuerCik"]), str(row["ticker"]))
        item = identities.get(identity_key)
        if item is None:
            raise ValueError(f"primary evidence identity missing: {identity_key}")

        if row["ticker"] == "OAS":
            resolved.append(_oas_resolution(row, gap, item))
        else:
            resolved.append(_same_security_resolution(row, gap, item))

    resolved.sort(key=lambda row: (row["eventNumber"], row["horizon"]))
    result_counts = Counter(row["resultState"] for row in resolved)
    if dict(result_counts) != {
        "DISCONTINUOUS_NO_COMPLETE_VALUATION": 3,
        "PRICE_CONTINUOUS_ADJUSTED": 7,
    }:
        raise ValueError("final10 result-state partition changed")

    payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_NEW_PRIMARY10_RESOLVED",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceRows": EXPECTED_ROWS,
        "resolvedRows": len(resolved),
        "unresolvedRows": 0,
        "tickerCounts": dict(sorted(counts.items())),
        "resultStateCounts": dict(sorted(result_counts.items())),
        "rows": resolved,
        "resolutionComplete": True,
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
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--stage-gaps", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        scope_path=args.scope,
        stage_gap_path=args.stage_gaps,
        evidence_path=args.evidence,
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
