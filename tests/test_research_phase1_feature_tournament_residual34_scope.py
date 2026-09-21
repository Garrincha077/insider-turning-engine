from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_residual34_scope"
)


def test_frozen_partition_constants() -> None:
    assert mod.EXPECTED_ROWS == 34
    assert mod.RESIDUAL35_DIGEST.endswith("7f0574e01")
    assert mod.POPE_ADJUDICATION_DIGEST.endswith("8afd18a4")


def test_semantic_key_ignores_cohort_event_number() -> None:
    row = {
        "eventNumber": 1,
        "issuerCik": "0001",
        "ticker": "ABC",
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "horizon": 252,
        "targetExitSession": "2021-01-04",
    }
    other = {**row, "eventNumber": 999}
    assert mod._key(row) == mod._key(other)
