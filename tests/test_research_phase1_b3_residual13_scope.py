from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_residual13_scope")


def test_frozen_digests_are_distinct() -> None:
    assert mod.SOURCE_SCOPE_KEY_SHA256 != mod.SURVIVING_RESOLUTION_KEY_SHA256
    assert mod.SOURCE_SCOPE_KEY_SHA256 != mod.RESIDUAL13_KEY_SHA256
    assert mod.SURVIVING_RESOLUTION_KEY_SHA256 != mod.RESIDUAL13_KEY_SHA256


def test_residual13_identity_count_is_frozen() -> None:
    assert len(mod.EXPECTED_IDENTITIES) == 6


def test_residual13_digest_is_sha256_contract() -> None:
    assert mod.RESIDUAL13_KEY_SHA256.startswith("sha256:")
    assert len(mod.RESIDUAL13_KEY_SHA256) == 71
