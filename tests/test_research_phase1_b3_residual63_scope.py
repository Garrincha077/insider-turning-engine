from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_residual63_scope")


def test_frozen_scope_digests_are_distinct() -> None:
    assert mod.SOURCE_SCOPE_KEY_SHA256 != mod.ONE_SIDED_RESOLUTION_KEY_SHA256
    assert mod.SOURCE_SCOPE_KEY_SHA256 != mod.RESIDUAL63_KEY_SHA256
    assert mod.ONE_SIDED_RESOLUTION_KEY_SHA256 != mod.RESIDUAL63_KEY_SHA256


def test_residual63_digest_is_sha256_contract() -> None:
    assert mod.RESIDUAL63_KEY_SHA256.startswith("sha256:")
    assert len(mod.RESIDUAL63_KEY_SHA256) == 71


def test_removed_bucket_is_exact_one_sided_bucket() -> None:
    assert mod.REMOVED_BUCKET == (
        "BEFORE_ONLY_EXPECTED_TICKER|ONE_SIDED_ACCESSION_ONLY|"
        "EXPECTED_TICKER_BOTH_SIDES"
    )
