from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_performance"
)


def _source() -> dict[str, object]:
    return {
        "eventNumber": 1,
        "issuerCik": "0000000001",
        "ticker": "OLD",
        "evaluationSession": "2021-01-04",
        "entrySession": "2021-01-05",
        "horizon": 126,
        "targetExitSession": "2021-07-07",
    }


def test_ordinary_terms_use_original_adjusted_security() -> None:
    result = mod._terms(_source(), None)
    assert result["terminalTicker"] == "OLD"
    assert result["marketQuantity"] == 1.0
    assert result["cash"] == 0.0


def test_stock_dividend_is_not_double_applied_to_adjusted_bars() -> None:
    contract = {
        "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
        "transformationKind": "STOCK_DIVIDEND_QUANTITY",
        "successorSymbol": "OLD",
        "successorSharesPerEntryShare": "1.10",
        "cashPerEntryShare": "0",
    }
    result = mod._terms(_source(), contract)
    assert result["legalQuantity"] == 1.1
    assert result["marketQuantity"] == 1.0


def test_symbol_change_requires_one_for_one_terms() -> None:
    contract = {
        "resolutionDecision": "SYMBOL_CHANGED_SAME_SECURITY",
        "transformationKind": "SAME_SECURITY_SYMBOL_CHANGE",
        "successorSymbol": "NEW",
        "successorSharesPerEntryShare": "2",
        "cashPerEntryShare": "0",
    }
    with pytest.raises(ValueError, match="invalid symbol-change"):
        mod._terms(_source(), contract)


def test_validation_frozen_constants() -> None:
    assert mod.PRIMARY_HORIZON == 126
    assert mod.EXPECTED_SCOPE_ROWS == 7493
    assert mod.EXPECTED_CONTRACT_ROWS == 191
