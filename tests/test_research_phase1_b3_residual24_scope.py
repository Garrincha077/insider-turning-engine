from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_residual24_scope")


def test_frozen_digests_are_distinct() -> None:
    assert mod.SOURCE_SCOPE_KEY_SHA256 != mod.COMMON_RESOLUTION_KEY_SHA256
    assert mod.SOURCE_SCOPE_KEY_SHA256 != mod.RESIDUAL24_KEY_SHA256
    assert mod.COMMON_RESOLUTION_KEY_SHA256 != mod.RESIDUAL24_KEY_SHA256


def test_residual24_identity_count_is_frozen() -> None:
    assert len(mod.EXPECTED_IDENTITIES) == 12


def test_residual24_digest_is_sha256_contract() -> None:
    assert mod.RESIDUAL24_KEY_SHA256.startswith("sha256:")
    assert len(mod.RESIDUAL24_KEY_SHA256) == 71
