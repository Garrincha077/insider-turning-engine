from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_residual87_scope")


def test_frozen_digest_constants_are_distinct() -> None:
    assert mod.SOURCE_SCOPE_KEY_SHA256 != mod.PROVIDER_RESOLUTION_KEY_SHA256
    assert mod.SOURCE_SCOPE_KEY_SHA256 != mod.RESIDUAL87_KEY_SHA256
    assert mod.PROVIDER_RESOLUTION_KEY_SHA256 != mod.RESIDUAL87_KEY_SHA256


def test_residual87_digest_is_sha256_contract() -> None:
    assert mod.RESIDUAL87_KEY_SHA256.startswith("sha256:")
    assert len(mod.RESIDUAL87_KEY_SHA256) == 71
