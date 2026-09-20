"""Freeze the exact performance-blind B3 residual-91 continuity scope."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

EXPECTED_SOURCE_ROWS = 264
EXPECTED_COMBINED_CANDIDATES = 173
EXPECTED_RESIDUAL_ROWS = 91
EXPECTED_RESIDUAL_DIGEST = (
    "sha256:46eeaa05a83960c1ef9537dd88972351b8c984c996ccddffa23f7da8d294ab58"
)
SEALED_YEAR = 2023

KEY_FIELDS = (
    "eventNumber",
    "issuerCik",
    "ticker",
    "evaluationSession",
    "entrySession",
    "horizon",
    "targetExitSession",
)

SCOPE_COLUMNS = (
    *KEY_FIELDS,
    "resolutionSource",
    "residualReason",
    "pivotDate",
    "pivotKind",
    "corroborationStatus",
    "securityTitleStatus",
    "form345CorroborationStatus",
    "candidateActionTypes",
    "candidateActionIds",
    "maxInternalGapSessions",
    "evidenceBucket",
)


def _assert_pre2023(value: object, field: str) -> None:
    text = str(value or "")
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        raise ValueError(f"invalid ISO date for {field}")
    if int(text[:4]) >= SEALED_YEAR:
        raise ValueError(f"sealed OOS boundary violated by {field}")


def _load_source(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "B3_RESIDUAL_MULTISOURCE_SYNTHESIS_COMPLETE":
        raise ValueError("unexpected residual synthesis source status")
    if payload.get("researchOnly") is not True:
        raise ValueError("source is not research-only")
    if payload.get("performanceRead") is not False:
        raise ValueError("source is not performance-blind")
    if payload.get("priceFieldsRead") != []:
        raise ValueError("source read price fields")
    if payload.get("oosOpened") is not False:
        raise ValueError("source opened OOS")
    if payload.get("productionScoringChanged") is not False:
        raise ValueError("source changed production scoring")
    if payload.get("finalResolutionContractCreated") is not False:
        raise ValueError("source already created a final resolution contract")
    if payload.get("correctedPerformanceOpened") is not False:
        raise ValueError("source opened corrected performance")
    if int(payload.get("sourceUnresolvedRows", -1)) != EXPECTED_SOURCE_ROWS:
        raise ValueError("unexpected source unresolved count")
    if int(payload.get("combinedCandidateRows", -1)) != EXPECTED_COMBINED_CANDIDATES:
        raise ValueError("unexpected combined candidate count")
    if int(payload.get("residualUnresolvedRows", -1)) != EXPECTED_RESIDUAL_ROWS:
        raise ValueError("unexpected residual count")
    if payload.get("residualKeySha256") != EXPECTED_RESIDUAL_DIGEST:
        raise ValueError("unexpected residual key digest")
    rows = payload.get("residualRows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_RESIDUAL_ROWS:
        raise ValueError("invalid residual row payload")
    if base._key_digest(rows) != EXPECTED_RESIDUAL_DIGEST:
        raise ValueError("residual rows do not match frozen key digest")
    return payload


def _evidence_bucket(row: dict[str, Any]) -> str:
    return "|".join(
        (
            str(row.get("corroborationStatus") or ""),
            str(row.get("securityTitleStatus") or ""),
            str(row.get("form345CorroborationStatus") or ""),
        )
    )


def _scope_row(row: dict[str, Any]) -> dict[str, Any]:
    for field in ("evaluationSession", "entrySession", "targetExitSession", "pivotDate"):
        _assert_pre2023(row[field], field)
    return {
        "eventNumber": int(row["eventNumber"]),
        "issuerCik": str(row["issuerCik"]),
        "ticker": str(row["ticker"]).upper(),
        "evaluationSession": str(row["evaluationSession"]),
        "entrySession": str(row["entrySession"]),
        "horizon": int(row["horizon"]),
        "targetExitSession": str(row["targetExitSession"]),
        "resolutionSource": str(row.get("resolutionSource") or ""),
        "residualReason": str(row.get("residualReason") or ""),
        "pivotDate": str(row.get("pivotDate") or ""),
        "pivotKind": str(row.get("pivotKind") or ""),
        "corroborationStatus": str(row.get("corroborationStatus") or ""),
        "securityTitleStatus": str(row.get("securityTitleStatus") or ""),
        "form345CorroborationStatus": str(
            row.get("form345CorroborationStatus") or ""
        ),
        "candidateActionTypes": str(row.get("candidateActionTypes") or ""),
        "candidateActionIds": str(row.get("candidateActionIds") or ""),
        "maxInternalGapSessions": str(row.get("maxInternalGapSessions") or ""),
        "evidenceBucket": _evidence_bucket(row),
    }


def freeze(*, source_path: Path, output_path: Path) -> dict[str, Any]:
    source = _load_source(source_path)
    scope = [_scope_row(row) for row in source["residualRows"]]

    if base._key_digest(scope) != EXPECTED_RESIDUAL_DIGEST:
        raise ValueError("normalized residual scope changed frozen keys")

    source_counts = Counter(row["resolutionSource"] for row in scope)
    reason_counts = Counter(row["residualReason"] for row in scope)
    bucket_counts = Counter(row["evidenceBucket"] for row in scope)

    pairs = sorted(
        {
            (str(row["issuerCik"]), str(row["ticker"]))
            for row in scope
        }
    )
    if len(pairs) != 35:
        raise ValueError("unexpected residual issuer/ticker pair count")

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_RESIDUAL91_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "developmentCohortYears": [2016, 2017, 2018, 2019, 2020],
        "outcomeEnd": "2022-12-31",
        "sealedYear": 2023,
        "horizons": [21, 63, 126, 252],
        "primaryHorizon": 126,
        "sourceRelease": "research-phase1-b3-residual-multisource-v1",
        "sourceAsset": "b3-residual-multisource-synthesis.json",
        "sourceResidualRows": EXPECTED_RESIDUAL_ROWS,
        "residualKeySha256": EXPECTED_RESIDUAL_DIGEST,
        "uniqueIssuerTickerPairs": len(pairs),
        "issuerTickerPairs": [
            {"issuerCik": cik, "ticker": ticker}
            for cik, ticker in pairs
        ],
        "resolutionSourceCounts": dict(sorted(source_counts.items())),
        "residualReasonCounts": dict(sorted(reason_counts.items())),
        "evidenceBucketCounts": dict(sorted(bucket_counts.items())),
        "scopeColumns": list(SCOPE_COLUMNS),
        "scopeRows": [
            [row[column] for column in SCOPE_COLUMNS]
            for row in scope
        ],
        "autoExpansionAllowed": False,
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
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            freeze(source_path=args.source, output_path=args.output),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
