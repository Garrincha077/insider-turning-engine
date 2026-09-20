"""Synthesize strict performance-blind B3 residual continuity candidates."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

SEALED_YEAR = 2023
EXPECTED_SOURCE_ROWS = 264
EXPECTED_PRIOR_CANDIDATES = 102
EXPECTED_RESIDUAL_ROWS = 162


def _key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(row[field])
        for field in (
            "eventNumber",
            "issuerCik",
            "ticker",
            "evaluationSession",
            "entrySession",
            "horizon",
            "targetExitSession",
        )
    )


def _assert_pre2023(value: object, field: str) -> None:
    text = str(value or "")
    if len(text) < 4 or not text[:4].isdigit():
        raise ValueError(f"missing or invalid date for {field}")
    if int(text[:4]) >= SEALED_YEAR:
        raise ValueError(f"sealed OOS boundary violated by {field}")


def _load_candidates(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "B3_CONTINUITY_RESOLUTION_CANDIDATES_COMPLETE":
        raise ValueError("unexpected B3 candidate source status")
    if payload.get("performanceRead") is not False:
        raise ValueError("candidate source is not performance-blind")
    if payload.get("priceFieldsRead") != []:
        raise ValueError("candidate source read price fields")
    if payload.get("oosOpened") is not False:
        raise ValueError("candidate source opened OOS")
    if payload.get("productionScoringChanged") is not False:
        raise ValueError("candidate source changed production scoring")
    if int(payload.get("sourceUnresolvedRows", -1)) != EXPECTED_SOURCE_ROWS:
        raise ValueError("unexpected frozen unresolved source count")
    if int(payload.get("candidateResolutionRows", -1)) != EXPECTED_PRIOR_CANDIDATES:
        raise ValueError("unexpected prior candidate count")
    if int(payload.get("residualUnresolvedRows", -1)) != EXPECTED_RESIDUAL_ROWS:
        raise ValueError("unexpected residual source count")
    return payload


def _load_evidence(path: Path) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or len(rows) != EXPECTED_RESIDUAL_ROWS:
        raise ValueError("unexpected residual evidence row count")
    for row in rows:
        if row.get("continuityStateChanged") is not False:
            raise ValueError("upstream evidence already changed continuity state")
        if row.get("finalResolutionAllowedFromThisStage") is not False:
            raise ValueError("upstream evidence improperly allowed final resolution")
        if row.get("form345DatePrecision") != "FILING_DATE_ONLY":
            raise ValueError("unexpected Form345 date precision")
        for field in (
            "evaluationSession",
            "entrySession",
            "targetExitSession",
            "pivotDate",
        ):
            _assert_pre2023(row[field], field)
        for side in (
            "beforeObservation",
            "afterObservation",
            "form345BeforeObservation",
            "form345AfterObservation",
        ):
            observation = row.get(side)
            if observation is None:
                continue
            date_value = observation.get("knowledgeAt") or observation.get("filingDate")
            _assert_pre2023(date_value, f"{side}.date")
    return rows


def _exact_observation(
    observation: dict[str, Any] | None,
    *,
    issuer: str,
    ticker: str,
) -> bool:
    return bool(
        observation
        and str(observation.get("issuerCik") or "") == issuer
        and str(observation.get("ticker") or "").upper() == ticker
    )


def _promotable(row: dict[str, Any]) -> bool:
    issuer = str(row["issuerCik"])
    ticker = str(row["ticker"]).upper()

    if row.get("resolutionSource") != "long_internal_gap":
        return False
    if str(row.get("candidateActionIds") or ""):
        return False
    if str(row.get("candidateActionTypes") or ""):
        return False
    if row.get("corroborationStatus") != "EXPECTED_TICKER_BOTH_SIDES":
        return False
    if row.get("securityTitleStatus") != "TITLE_SET_EXACT_MATCH":
        return False
    if row.get("form345CorroborationStatus") != "EXPECTED_TICKER_BOTH_SIDES":
        return False

    before_titles = row.get("beforeSecurityTitles") or []
    after_titles = row.get("afterSecurityTitles") or []
    if not before_titles or before_titles != after_titles:
        return False

    if not _exact_observation(row.get("beforeObservation"), issuer=issuer, ticker=ticker):
        return False
    if not _exact_observation(row.get("afterObservation"), issuer=issuer, ticker=ticker):
        return False
    if not _exact_observation(
        row.get("form345BeforeObservation"),
        issuer=issuer,
        ticker=ticker,
    ):
        return False
    if not _exact_observation(
        row.get("form345AfterObservation"),
        issuer=issuer,
        ticker=ticker,
    ):
        return False
    return True


def synthesize(
    *,
    candidate_path: Path,
    evidence_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    source = _load_candidates(candidate_path)
    evidence = _load_evidence(evidence_path)

    source_residual = source["residualRows"]
    source_keys = {_key(row) for row in source_residual}
    evidence_keys = {_key(row) for row in evidence}
    if len(source_keys) != EXPECTED_RESIDUAL_ROWS:
        raise ValueError("duplicate keys in residual candidate source")
    if len(evidence_keys) != EXPECTED_RESIDUAL_ROWS:
        raise ValueError("duplicate keys in residual evidence")
    if evidence_keys != source_keys:
        raise ValueError("residual evidence scope differs from frozen candidate scope")

    promoted: list[dict[str, Any]] = []
    residual: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()

    for row in evidence:
        if _promotable(row):
            candidate = {
                **base._key_object(row),
                "evidenceClass": "SEC_MULTI_SOURCE_EXACT_CONTINUITY",
                "expectedSourceResolutionSource": "long_internal_gap",
                "effectiveDate": str(row["pivotDate"]),
                "resolutionDecision": "SAME_SECURITY_CONTINUITY",
                "transformationKind": "",
                "resultState": "PRICE_CONTINUOUS_ADJUSTED",
                "successorSymbol": str(row["ticker"]).upper(),
                "successorSharesPerEntryShare": 1.0,
                "cashPerEntryShare": 0.0,
                "sourceActionIds": [],
                "securityTitles": list(row["beforeSecurityTitles"]),
                "psBeforeAccession": str(row["beforeObservation"]["accession"]),
                "psAfterAccession": str(row["afterObservation"]["accession"]),
                "form345BeforeAccession": str(
                    row["form345BeforeObservation"]["accession"]
                ),
                "form345AfterAccession": str(
                    row["form345AfterObservation"]["accession"]
                ),
            }
            promoted.append(candidate)
            reasons["PROMOTED_MULTI_SOURCE_EXACT_CONTINUITY"] += 1
        else:
            residual.append(row)
            reasons["REMAINS_UNRESOLVED_FAIL_CLOSED"] += 1

    combined = list(source["candidateRows"]) + promoted
    combined_keys = {_key(row) for row in combined}
    if len(combined_keys) != len(combined):
        raise ValueError("duplicate resolution candidate keys after synthesis")
    if len(combined) + len(residual) != EXPECTED_SOURCE_ROWS:
        raise ValueError("candidate/residual partition no longer covers frozen scope")

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_RESIDUAL_MULTISOURCE_SYNTHESIS_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": EXPECTED_SOURCE_ROWS,
        "priorCandidateRows": len(source["candidateRows"]),
        "sourceResidualRows": len(evidence),
        "newCandidateRows": len(promoted),
        "combinedCandidateRows": len(combined),
        "residualUnresolvedRows": len(residual),
        "reasonCounts": dict(sorted(reasons.items())),
        "frozenScopeKeySha256": source["frozenScopeKeySha256"],
        "newCandidateKeySha256": base._key_digest(promoted),
        "combinedCandidateKeySha256": base._key_digest(combined),
        "residualKeySha256": base._key_digest(residual),
        "newCandidateRowsData": promoted,
        "combinedCandidateRowsData": combined,
        "residualRows": residual,
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
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            synthesize(
                candidate_path=args.candidates,
                evidence_path=args.evidence,
                output_path=args.output,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
