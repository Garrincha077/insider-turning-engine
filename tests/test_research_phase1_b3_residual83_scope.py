from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_residual83_scope")


def test_frozen_scope_digests_are_distinct() -> None:
    assert mod.SOURCE_SCOPE_KEY_SHA256 != mod.SPAC_RESOLUTION_KEY_SHA256
    assert mod.SOURCE_SCOPE_KEY_SHA256 != mod.RESIDUAL83_KEY_SHA256
    assert mod.SPAC_RESOLUTION_KEY_SHA256 != mod.RESIDUAL83_KEY_SHA256


def test_residual83_digest_is_sha256_contract() -> None:
    assert mod.RESIDUAL83_KEY_SHA256.startswith("sha256:")
    assert len(mod.RESIDUAL83_KEY_SHA256) == 71


def test_removed_bucket_is_exact_title_ticker_change_bucket() -> None:
    assert mod.REMOVED_BUCKET == (
        "TICKER_CHANGED_AFTER_PIVOT|TITLE_SET_EXACT_MATCH|"
        "TICKER_CHANGED_AFTER_PIVOT"
    )
