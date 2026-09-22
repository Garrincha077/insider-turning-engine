from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_residual19_scope"
)


def test_frozen_counts_and_digests() -> None:
    assert mod.EXPECTED_SOURCE_ROWS == 27
    assert mod.EXPECTED_RESOLVED_ROWS == 8
    assert mod.EXPECTED_RESIDUAL_ROWS == 19
    assert mod.EXPECTED_SOURCE_DIGEST.startswith("sha256:")
    assert mod.EXPECTED_RESOLUTION_DIGEST.startswith("sha256:")
    assert mod.EXPECTED_RESIDUAL_DIGEST.startswith("sha256:")


def test_wave_counter() -> None:
    rows = [
        {
            "ticker": "TBA",
            "candidateActionTypes": ["name_changes", "stock_mergers"],
            "evidenceAudit": {"category": "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED"},
        },
        {
            "ticker": "CBTX",
            "candidateActionTypes": ["name_changes"],
            "evidenceAudit": {"category": "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED"},
        },
        {
            "ticker": "ROCGU",
            "candidateActionTypes": [],
            "evidenceAudit": {"category": "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED"},
        },
    ]
    assert mod._wave_counts(rows) == {
        "nameChangeStockMergerRows": 1,
        "standaloneNameChangeRows": 1,
        "longGapRows": 1,
    }
