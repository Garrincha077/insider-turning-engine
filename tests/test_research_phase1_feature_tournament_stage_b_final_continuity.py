from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_stage_b_final_continuity"
)


def _overlap_row(
    *,
    source: str,
    prior_event: int,
    source_row: dict[str, object],
) -> dict[str, object]:
    return {
        "currentEventNumber": 999,
        "issuerCik": source_row["issuerCik"],
        "ticker": source_row["ticker"],
        "evaluationSession": source_row["evaluationSession"],
        "entrySession": source_row["entrySession"],
        "horizon": source_row["horizon"],
        "targetExitSession": source_row["targetExitSession"],
        "currentResolutionSource": "long_internal_gap",
        "matchStatus": "SAFE_PRIOR_ECONOMIC_MATCH",
        "priorMatches": [
            {
                "source": source,
                "priorEventNumber": prior_event,
                "economicFingerprint": mod._fingerprint(source_row),
                "schemaLabels": {
                    "resolutionDecision": source_row["resolutionDecision"],
                    "transformationKind": source_row["transformationKind"],
                },
            }
        ],
    }


def test_prior_resolution_preserves_multicomponent_basket() -> None:
    source_row: dict[str, object] = {
        "eventNumber": 10,
        "issuerCik": "0000000001",
        "ticker": "NBA.U",
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "horizon": 252,
        "targetExitSession": "2021-01-04",
        "effectiveDate": "2020-08-01",
        "resolutionDecision": "TRANSFORMED_MULTI_COMPONENT_CONSIDERATION",
        "transformationKind": "UNIT_SEPARATION",
        "resultState": "TRANSFORMED_MULTI_COMPONENT_CONSIDERATION",
        "successorSymbol": "",
        "successorSharesPerEntryShare": "",
        "cashPerEntryShare": 0,
        "sourceActionIds": [],
        "basket": [
            {
                "symbol": "MIMO",
                "securityClass": "COMMON",
                "quantityPerEntryUnit": 1,
            },
            {
                "symbol": "MIMO WS",
                "securityClass": "WARRANT",
                "quantityPerEntryUnit": 0.5,
            },
        ],
        "evidenceClass": "TEST",
        "classificationSource": "test",
        "classificationSourceRelease": "test-release",
    }
    overlap = _overlap_row(
        source="B3",
        prior_event=10,
        source_row=source_row,
    )
    index = {(mod._semantic_key(source_row), 10): source_row}

    result = mod._prior_resolution(overlap, {}, index)

    assert result["eventNumber"] == 999
    assert result["resolutionDecision"] == (
        "TRANSFORMED_MULTI_COMPONENT_CONSIDERATION"
    )
    assert {item["symbol"] for item in result["basket"]} == {
        "MIMO",
        "MIMO WS",
    }
    assert all("quantityPerEntryUnit" in item for item in result["basket"])
    assert all("quantity" not in item for item in result["basket"])


def test_prior_resolution_normalizes_legacy_b1_quantity() -> None:
    source_row: dict[str, object] = {
        "eventNumber": 20,
        "issuerCik": "0000000002",
        "ticker": "TEST",
        "evaluationSession": "2020-02-03",
        "entrySession": "2020-02-04",
        "horizon": 126,
        "targetExitSession": "2020-08-04",
        "effectiveDate": "2020-05-01",
        "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
        "transformationKind": "STOCK_DIVIDEND_QUANTITY",
        "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol": "TEST",
        "shareQuantityFactor": "1.05",
        "sourceActionIds": ["action-1"],
    }
    overlap = _overlap_row(
        source="B1",
        prior_event=20,
        source_row=source_row,
    )
    index = {(mod._semantic_key(source_row), 20): source_row}

    result = mod._prior_resolution(overlap, index, {})

    assert result["successorSharesPerEntryShare"] == "1.05"
    assert result["cashPerEntryShare"] == "0"
    assert result["sourceActionIds"] == ["action-1"]
    assert result["evidenceClass"] == (
        "PRIOR_FROZEN_B1_CONTINUITY_EVIDENCE"
    )
