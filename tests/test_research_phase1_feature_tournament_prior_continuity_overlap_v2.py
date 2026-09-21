from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_prior_continuity_overlap_v2"
)


def test_numeric_formatting_is_economically_equal() -> None:
    a = {
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "successorSymbol": "ABC",
        "shareQuantityFactor": "1.0",
    }
    b = {
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "successorSymbol": "ABC",
        "successorSharesPerEntryShare": 1,
        "cashPerEntryShare": 0,
    }
    assert mod._compatible([a, b])


def test_schema_labels_do_not_create_false_economic_conflict() -> None:
    a = {
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "successorSymbol": "ABC",
        "shareQuantityFactor": 1,
        "resolutionDecision": "SAME_SECURITY_CONTINUITY",
    }
    b = {
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "successorSymbol": "ABC",
        "successorSharesPerEntryShare": 1.0,
        "resolutionDecision": "UNCHANGED_COMMON",
    }
    assert mod._compatible([a, b])
    assert mod._schema_labels(a) != mod._schema_labels(b)


def test_real_successor_difference_remains_conflict() -> None:
    a = {
        "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol": "ABC",
        "shareQuantityFactor": 1.1,
    }
    b = {
        "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol": "XYZ",
        "successorSharesPerEntryShare": 1.1,
    }
    assert not mod._compatible([a, b])


def test_nonzero_cash_difference_remains_conflict() -> None:
    a = {
        "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol": "ABC",
        "shareQuantityFactor": 1,
    }
    b = {
        "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol": "ABC",
        "successorSharesPerEntryShare": 1,
        "cashPerEntryShare": 2.5,
    }
    assert not mod._compatible([a, b])
