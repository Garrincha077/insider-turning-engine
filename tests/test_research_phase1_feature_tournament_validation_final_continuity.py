from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_final_continuity"
)


def _row(state: str, successor: str = "") -> dict[str, object]:
    return {
        "eventNumber": 1,
        "issuerCik": "0000000001",
        "ticker": "OLD",
        "evaluationSession": "2021-01-04",
        "entrySession": "2021-01-05",
        "horizon": 126,
        "targetExitSession": "2021-07-07",
        "state": state,
        "successorSymbol": successor,
        "resolutionSource": "provider",
        "candidateActionIds": "action-1",
    }


def test_provider_symbol_change_terms() -> None:
    row = _row("SYMBOL_CHANGED_SAME_SECURITY", "NEW")
    actions = {
        "action-1": {
            "id": "action-1",
            "bucket": "name_changes",
            "actionDate": "2021-03-01",
            "old_symbol": "OLD",
            "new_symbol": "NEW",
            "old_cusip": "123456789",
            "new_cusip": "123456789",
        }
    }
    result = mod._provider_resolution(row, actions)
    assert result["resolutionDecision"] == "SYMBOL_CHANGED_SAME_SECURITY"
    assert result["successorSymbol"] == "NEW"
    assert result["successorSharesPerEntryShare"] == "1"


def test_provider_stock_merger_ratio() -> None:
    row = _row("TRANSFORMED_HOLDER_CONSIDERATION", "NEW")
    actions = {
        "action-1": {
            "id": "action-1",
            "bucket": "stock_mergers",
            "actionDate": "2021-03-01",
            "acquiree_rate": 2,
            "acquirer_rate": 1,
            "acquirer_symbol": "NEW",
        }
    }
    result = mod._provider_resolution(row, actions)
    assert result["successorSharesPerEntryShare"] == "0.5"
    assert result["cashPerEntryShare"] == "0"


def test_provider_cash_merger_terms() -> None:
    row = _row("TRANSFORMED_HOLDER_CONSIDERATION")
    actions = {
        "action-1": {
            "id": "action-1",
            "bucket": "cash_mergers",
            "actionDate": "2021-03-01",
            "rate": 7.5,
        }
    }
    result = mod._provider_resolution(row, actions)
    assert result["successorSymbol"] == ""
    assert result["successorSharesPerEntryShare"] == "0"
    assert result["cashPerEntryShare"] == "7.5"


def test_provider_effective_date_is_fail_closed() -> None:
    row = _row("TRANSFORMED_HOLDER_CONSIDERATION")
    actions = {
        "action-1": {
            "id": "action-1",
            "bucket": "cash_mergers",
            "actionDate": "2022-01-01",
            "rate": 7.5,
        }
    }
    with pytest.raises(ValueError, match="outside horizon"):
        mod._provider_resolution(row, actions)


def test_frozen_counts() -> None:
    assert mod.EXPECTED_SCOPE_ROWS == 7493
    assert mod.EXPECTED_AFFECTED_ROWS == 191
    assert mod.EXPECTED_UNRESOLVED_ROWS == 41
