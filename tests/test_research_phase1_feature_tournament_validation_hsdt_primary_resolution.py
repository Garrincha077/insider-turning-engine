from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_hsdt_primary_resolution"
)


def test_hsdt_key_digest_is_frozen() -> None:
    row = {
        "eventNumber": 3657,
        "issuerCik": "0001610853",
        "ticker": "HSDT",
        "evaluationSession": "2021-11-15",
        "entrySession": "2021-11-16",
        "horizon": 126,
        "targetExitSession": "2022-05-18",
    }
    assert mod._digest(row) == mod.EXPECTED_KEY_DIGEST


def test_frozen_remaining_count() -> None:
    assert mod.EXPECTED_KEY_DIGEST.startswith("sha256:")
    assert mod.EXPECTED_RESIDUAL_SCOPE_DIGEST.startswith("sha256:")
