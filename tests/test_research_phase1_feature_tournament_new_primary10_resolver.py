from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_new_primary10_resolver"
)


def _oas_row() -> dict[str, object]:
    return {
        "currentEventNumber": 23221,
        "issuerCik": "0001486159",
        "ticker": "OAS",
        "evaluationSession": "2020-10-07",
        "entrySession": "2020-10-08",
        "horizon": 63,
        "targetExitSession": "2021-01-08",
        "maxInternalGapSessions": 29,
    }


def _oas_gap() -> dict[str, str]:
    return {
        "eventNumber": "23221",
        "ticker": "OAS",
        "horizon": "63",
        "previousObservedSession": "2020-10-09",
        "firstMissingSession": "2020-10-12",
        "lastMissingSession": "2020-11-19",
        "nextObservedSession": "2020-11-20",
        "maxInternalGapSessions": "29",
    }


def _oas_evidence() -> dict[str, object]:
    return {
        "effectiveDate": "2020-11-19",
        "resolutionDecision": "DISCONTINUOUS_NO_COMPLETE_VALUATION",
        "transformationKind": "BANKRUPTCY_REORG_UNVALUED_WARRANT",
        "resultState": "DISCONTINUOUS_NO_COMPLETE_VALUATION",
        "successorSymbol": "",
        "successorSharesPerEntryShare": 0,
        "cashPerEntryShare": 0,
        "evidenceClass": "PRIMARY_SEC_BANKRUPTCY_REORG_UNVALUED_WARRANT",
        "primaryEvidence": [
            {"accession": "0001486159-20-000089"},
            {"accession": "0001486159-20-000115"},
            {"accession": "0001486159-21-000017"},
        ],
        "valuationPolicy": {
            "precedent": {
                "b3ResultState": "DISCONTINUOUS_NO_COMPLETE_VALUATION",
                "b3TransformationKind": (
                    "MULTI_LEG_UNIT_SEPARATION_UNVALUED_WARRANT"
                ),
            }
        },
    }


def test_oas_cannot_be_mapped_to_successor_common() -> None:
    row = _oas_row()
    gap = _oas_gap()
    mod._validate_gap(row, gap)
    result = mod._oas_resolution(row, gap, _oas_evidence())

    assert result["resolutionDecision"] == (
        "DISCONTINUOUS_NO_COMPLETE_VALUATION"
    )
    assert result["successorSymbol"] == ""
    assert result["holderConsideration"] == (
        "PRO_RATA_REORGANIZATION_WARRANTS"
    )
    assert result["warrantAggregateIssued"] == 1621622
    assert result["initialWarrantExercisePrice"] == 94.57


def test_oas_requires_cancellation_date_at_gap_end() -> None:
    gap = _oas_gap()
    gap["lastMissingSession"] = "2020-11-18"

    with pytest.raises(
        ValueError,
        match="cancellation date no longer aligns",
    ):
        mod._oas_resolution(_oas_row(), gap, _oas_evidence())


def test_frozen_gap_tuple_is_fail_closed() -> None:
    gap = _oas_gap()
    gap["firstMissingSession"] = "2020-10-13"

    with pytest.raises(ValueError, match="frozen gap tuple changed"):
        mod._validate_gap(_oas_row(), gap)
