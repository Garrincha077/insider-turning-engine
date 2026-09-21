from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_residual_continuity_scope"
)


def test_digest_is_independent_of_row_order() -> None:
    a = {
        "issuerCik": "1",
        "ticker": "A",
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "horizon": 21,
        "targetExitSession": "2020-02-03",
    }
    b = {
        "issuerCik": "2",
        "ticker": "B",
        "evaluationSession": "2020-01-04",
        "entrySession": "2020-01-06",
        "horizon": 63,
        "targetExitSession": "2020-04-06",
    }
    assert mod._digest([a, b]) == mod._digest([b, a])


def test_expected_partition_is_35() -> None:
    assert mod.EXPECTED_SAFE_ROWS == 175
    assert mod.EXPECTED_CONFLICT_ROWS == 1
    assert mod.EXPECTED_UNMATCHED_ROWS == 34
    assert mod.EXPECTED_RESIDUAL_ROWS == 35
