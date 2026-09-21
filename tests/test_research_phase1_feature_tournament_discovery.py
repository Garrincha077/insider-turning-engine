from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_discovery"
)


def test_quintile_boundaries_are_frozen() -> None:
    cuts = {"q20": 1.0, "q40": 2.0, "q60": 3.0, "q80": 4.0}
    assert mod._quintile(1.0, cuts) == "Q1"
    assert mod._quintile(2.0, cuts) == "Q2"
    assert mod._quintile(3.0, cuts) == "Q3"
    assert mod._quintile(4.0, cuts) == "Q4"
    assert mod._quintile(4.0001, cuts) == "Q5"


def test_f2_orientation_uses_higher_event_weighted_mean() -> None:
    rows = [
        {
            "F2_DIRECT_VS_INDIRECT": "DIRECT_ONLY",
            "excess_126": 0.10,
        },
        {
            "F2_DIRECT_VS_INDIRECT": "DIRECT_ONLY",
            "excess_126": 0.00,
        },
        {
            "F2_DIRECT_VS_INDIRECT": "INDIRECT_ONLY",
            "excess_126": 0.01,
        },
        {
            "F2_DIRECT_VS_INDIRECT": "INDIRECT_ONLY",
            "excess_126": 0.02,
        },
    ]
    assert mod._f2_orientation(rows) == "DIRECT_ONLY"


def test_top1_removal_is_pooled_and_deterministic() -> None:
    rows = []
    for index in range(100):
        rows.append(
            {
                "_group": "PREFERRED" if index < 50 else "COMPLEMENT",
                "eventNumber": index + 1,
                "issuerCik": f"{index:010d}",
                "excess_126": 10.0 if index == 0 else 0.1,
            }
        )
    value, removed = mod._top1_removed_increment(rows)
    assert removed == 1
    assert value == 0.0


def test_final_stock_dividend_uses_adjusted_market_quantity_one() -> None:
    row = {
        "ticker": "TEST",
        "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
        "transformationKind": "STOCK_DIVIDEND_QUANTITY",
        "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol": "TEST",
        "successorSharesPerEntryShare": 1.10,
        "cashPerEntryShare": 0,
    }
    terms = mod._final_terms(row)
    assert terms["marketQuantity"] == 1.0
    assert terms["legalQuantity"] == 1.10
    assert terms["terminalTicker"] == "TEST"


def test_provider_stock_and_cash_merger_normalizes_per_acquiree_share() -> None:
    ledger = {
        "entrySession": "2020-01-02",
        "targetExitSession": "2020-12-31",
        "candidateActionIds": "a1",
    }
    actions = {
        "a1": {
            "bucket": "stock_and_cash_mergers",
            "actionDate": "2020-06-01",
            "acquiree_rate": 2,
            "acquirer_rate": 1,
            "cash_rate": 4,
            "acquirer_symbol": "NEW",
        }
    }
    terms = mod._provider_terms(ledger, actions)
    assert terms["marketQuantity"] == 0.5
    assert terms["cash"] == 2.0
    assert terms["terminalTicker"] == "NEW"


def test_family_tie_break_prefers_top1_then_variant_id() -> None:
    base = {
        "family": "F1",
        "coverageClass": "GENERAL_ELIGIBLE",
        "candidateScope": "GENERAL",
        "frozenGroupDefinition": {},
        "discoveryPass": True,
    }
    results = [
        {
            **base,
            "variantId": "F1_B",
            "primary126": {
                "top1PctRemovedIncrementalMean": 0.1,
                "issuerEqualWeightIncrementalMean": 0.1,
                "entrySessionEqualWeightIncrementalMean": 0.1,
                "eventWeightedIncrementalMean": 0.1,
            },
        },
        {
            **base,
            "variantId": "F1_A",
            "primary126": {
                "top1PctRemovedIncrementalMean": 0.1,
                "issuerEqualWeightIncrementalMean": 0.1,
                "entrySessionEqualWeightIncrementalMean": 0.1,
                "eventWeightedIncrementalMean": 0.1,
            },
        },
    ]
    winners = mod._select_family_winners(results)
    assert winners["F1"]["variantId"] == "F1_A"
    assert winners["F2"]["status"] == "NO_FAMILY_CANDIDATE"
