from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_residual27_scope"
)


def _row(
    event: int,
    *,
    category: str,
    action_types: list[str],
    source: str,
) -> dict[str, object]:
    return {
        "eventNumber": event,
        "issuerCik": f"{event:010d}",
        "ticker": f"T{event}",
        "evaluationSession": "2022-01-03",
        "entrySession": "2022-01-04",
        "horizon": 126,
        "targetExitSession": "2022-07-06",
        "candidateActionTypes": action_types,
        "resolutionSource": source,
        "evidenceAudit": {"category": category},
    }


def test_wave_classifier_matches_frozen_shapes() -> None:
    rows = [
        _row(
            1,
            category="PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED",
            action_types=["stock_mergers"],
            source="provider_incomplete_terms",
        ),
        _row(
            2,
            category="PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED",
            action_types=["name_changes", "stock_mergers"],
            source="provider",
        ),
        _row(
            3,
            category="PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED",
            action_types=["name_changes"],
            source="provider",
        ),
        _row(
            4,
            category="LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED",
            action_types=[],
            source="long_internal_gap",
        ),
    ]
    assert mod._wave_counts(rows) == {
        "incompleteStockMergerRows": 1,
        "nameChangeStockMergerRows": 1,
        "standaloneNameChangeRows": 1,
        "longGapRows": 1,
    }


def test_frozen_counts_are_consistent() -> None:
    assert mod.EXPECTED_SOURCE_ROWS == 32
    assert mod.EXPECTED_RESOLVED_ROWS == 5
    assert mod.EXPECTED_RESIDUAL_ROWS == 27
    assert (
        mod.EXPECTED_RESOLVED_ROWS + mod.EXPECTED_RESIDUAL_ROWS
        == mod.EXPECTED_SOURCE_ROWS
    )
