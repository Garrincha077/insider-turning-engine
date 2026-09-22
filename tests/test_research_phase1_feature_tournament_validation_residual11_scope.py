from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_residual11_scope"
)


def test_frozen_constants() -> None:
    assert mod.EXPECTED_SOURCE_ROWS == 19
    assert mod.EXPECTED_RESOLVED_ROWS == 8
    assert mod.EXPECTED_RESIDUAL_ROWS == 11
    assert mod.EXPECTED_SOURCE_DIGEST.startswith("sha256:")
    assert mod.EXPECTED_RESOLUTION_DIGEST.startswith("sha256:")
    assert mod.EXPECTED_RESIDUAL_DIGEST.startswith("sha256:")
