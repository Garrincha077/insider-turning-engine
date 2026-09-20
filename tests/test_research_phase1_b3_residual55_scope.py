from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_residual55_scope")


def test_frozen_digests_are_distinct() -> None:
    assert mod.SOURCE_SCOPE_KEY_SHA256 != mod.RESOLUTION_KEY_SHA256
    assert mod.SOURCE_SCOPE_KEY_SHA256 != mod.RESIDUAL55_KEY_SHA256
    assert mod.RESOLUTION_KEY_SHA256 != mod.RESIDUAL55_KEY_SHA256


def test_residual55_digest_is_sha256() -> None:
    assert mod.RESIDUAL55_KEY_SHA256.startswith("sha256:")
    assert len(mod.RESIDUAL55_KEY_SHA256) == 71


def test_removed_identities_are_exact_second_spac_wave() -> None:
    assert mod.REMOVED_IDENTITIES == {
        ("0001719893", "MTECU"),
        ("0001768910", "GRCYU"),
        ("0001777393", "SBE.U"),
        ("0001785424", "FSRVU"),
    }
