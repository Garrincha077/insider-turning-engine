from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_residual10_long_gap_scope"
)


def test_frozen_constants() -> None:
    assert mod.EXPECTED_SOURCE_ROWS == 11
    assert mod.EXPECTED_RESOLVED_ROWS == 1
    assert mod.EXPECTED_RESIDUAL_ROWS == 10
    assert len(mod.EXPECTED_TICKERS) == 10
    assert mod.EXPECTED_RESIDUAL_DIGEST.startswith("sha256:")
