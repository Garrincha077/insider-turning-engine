from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_continuity_resolution_candidates")


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "eventNumber": "1",
        "issuerCik": "0001",
        "ticker": "ABC",
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "horizon": "126",
        "targetExitSession": "2020-07-06",
        "resolutionSource": "provider",
        "candidateActionTypes": "",
        "candidateActionIds": "",
        "maxInternalGapSessions": "0",
    }
    row.update(overrides)
    return row


def test_stock_dividend_preserves_explicit_quantity_rate() -> None:
    row = _row(candidateActionIds="sd")
    actions = {
        "sd": {
            "id": "sd",
            "bucket": "stock_dividends",
            "actionDate": "2020-03-02",
            "rate": 1.05,
        }
    }
    candidate, reason = mod._provider_candidate(row, actions)
    assert reason == "RESOLVED_PROVIDER_STOCK_DIVIDEND"
    assert candidate is not None
    assert candidate["successorSymbol"] == "ABC"
    assert candidate["successorSharesPerEntryShare"] == 1.05
    assert candidate["cashPerEntryShare"] == 0.0


def test_paired_stock_and_cash_merger_preserves_both_terms() -> None:
    row = _row(candidateActionIds="cash;stock")
    actions = {
        "cash": {
            "id": "cash",
            "bucket": "cash_mergers",
            "actionDate": "2020-03-02",
            "rate": 12.5,
        },
        "stock": {
            "id": "stock",
            "bucket": "stock_mergers",
            "actionDate": "2020-03-02",
            "acquiree_rate": 1,
            "acquirer_rate": 0.2558,
            "acquirer_symbol": "XYZ",
        },
    }
    candidate, reason = mod._provider_candidate(row, actions)
    assert reason == "RESOLVED_PROVIDER_MIXED_MERGER"
    assert candidate is not None
    assert candidate["successorSymbol"] == "XYZ"
    assert candidate["successorSharesPerEntryShare"] == 0.2558
    assert candidate["cashPerEntryShare"] == 12.5


def test_changed_cusip_name_change_stays_unresolved() -> None:
    row = _row(candidateActionIds="name")
    actions = {
        "name": {
            "id": "name",
            "bucket": "name_changes",
            "actionDate": "2020-03-02",
            "old_symbol": "ABC",
            "new_symbol": "XYZ",
            "old_cusip": "111",
            "new_cusip": "222",
        }
    }
    candidate, reason = mod._provider_candidate(row, actions)
    assert candidate is None
    assert reason == "PROVIDER_AMBIGUOUS_REQUIRES_PRIMARY_EVIDENCE"


def test_same_cusip_name_change_plus_one_to_one_stock_row_is_continuous() -> None:
    row = _row(candidateActionIds="name;stock")
    actions = {
        "name": {
            "id": "name",
            "bucket": "name_changes",
            "actionDate": "2020-03-03",
            "old_cusip": "111",
            "new_cusip": "111",
            "new_symbol": "XYZ",
        },
        "stock": {
            "id": "stock",
            "bucket": "stock_mergers",
            "actionDate": "2020-03-02",
            "acquiree_rate": 1,
            "acquirer_rate": 1,
            "acquirer_cusip": "111",
        },
    }
    candidate, reason = mod._provider_candidate(row, actions)
    assert reason == "RESOLVED_PROVIDER_SAME_CUSIP"
    assert candidate is not None
    assert candidate["resultState"] == "SYMBOL_CHANGED_SAME_SECURITY"
    assert candidate["successorSymbol"] == "XYZ"
    assert candidate["successorSharesPerEntryShare"] == 1.0
