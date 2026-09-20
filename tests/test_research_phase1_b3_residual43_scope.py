from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_residual43_scope")


def test_frozen_digests_are_distinct() -> None:
    assert mod.SOURCE_SCOPE_KEY_SHA256 != mod.RESOLUTION_KEY_SHA256
    assert mod.SOURCE_SCOPE_KEY_SHA256 != mod.RESIDUAL43_KEY_SHA256
    assert mod.RESOLUTION_KEY_SHA256 != mod.RESIDUAL43_KEY_SHA256


def test_residual43_digest_is_sha256() -> None:
    assert mod.RESIDUAL43_KEY_SHA256.startswith("sha256:")
    assert len(mod.RESIDUAL43_KEY_SHA256) == 71


def test_removed_identities_are_exact_multiclass_subset() -> None:
    assert mod.REMOVED_IDENTITIES == {
        ("0001635193", "GGO"),
        ("0001471824", "TAGS"),
        ("0001647088", "EAGL"),
        ("0001697152", "FMCIU"),
    }
