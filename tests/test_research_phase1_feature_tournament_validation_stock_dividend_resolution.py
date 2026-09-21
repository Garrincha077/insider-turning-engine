from __future__ import annotations

import importlib
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_stock_dividend_resolution"
)


def test_frozen_counts_and_digest() -> None:
    assert mod.EXPECTED_SOURCE_ROWS == 32
    assert mod.EXPECTED_TARGET_ROWS == 5
    assert mod.EXPECTED_REMAINING_ROWS == 27
    assert mod.EXPECTED_TARGET_DIGEST.startswith("sha256:")


def test_quantity_formatter_preserves_fractional_units() -> None:
    assert mod._format(Decimal("1.01044")) == "1.01044"
    assert mod._format(Decimal("1.10")) == "1.1"


def test_non_numeric_rate_fails() -> None:
    with pytest.raises(ValueError, match="invalid numeric"):
        mod._number("not-a-number")
