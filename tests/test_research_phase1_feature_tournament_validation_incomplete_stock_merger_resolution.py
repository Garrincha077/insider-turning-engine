from __future__ import annotations

import importlib
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_incomplete_stock_merger_resolution"
)


def _row() -> dict[str, object]:
    return {
        "eventNumber": 887,
        "issuerCik": "0001104855",
        "ticker": "SPRT",
        "evaluationSession": "2021-03-24",
        "entrySession": "2021-03-25",
        "horizon": 126,
        "targetExitSession": "2021-09-23",
        "resolutionSource": "provider_incomplete_terms",
        "candidateActionIds": ["d6cf9395-fd17-4af5-b03b-38dd3642aafd"],
        "candidateActionTypes": ["stock_mergers"],
        "evidenceAudit": {
            "category": "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED"
        },
    }


def _fact() -> dict[str, object]:
    return {
        "actionId": "d6cf9395-fd17-4af5-b03b-38dd3642aafd",
        "issuerCik": "0001104855",
        "ticker": "SPRT",
        "effectiveDate": "2021-09-14",
        "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
        "transformationKind": "PRIMARY_SEC_STOCK_MERGER",
        "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol": "GREE",
        "successorSharesPerEntryShare": 0.115,
        "cashPerEntryShare": 0,
        "primaryEvidence": [
            {"accession": "test", "secUrl": "https://www.sec.gov/", "fact": "x"}
        ],
    }


def test_frozen_counts_and_digest() -> None:
    assert mod.EXPECTED_SOURCE_ROWS == 27
    assert mod.EXPECTED_TARGET_ROWS == 8
    assert mod.EXPECTED_REMAINING_ROWS == 19
    assert mod.EXPECTED_TARGET_DIGEST.startswith("sha256:")


def test_sprt_primary_merger_terms() -> None:
    result = mod._resolution(_row(), _fact())
    assert result["successorSymbol"] == "GREE"
    assert result["successorSharesPerEntryShare"] == "0.115"
    assert result["cashPerEntryShare"] == "0"
    assert result["classificationSource"] == (
        "VALIDATION_PRIMARY_INCOMPLETE_STOCK_MERGER_TERMS"
    )


def test_same_symbol_reorganization_requires_one_for_one() -> None:
    row = _row()
    row["issuerCik"] = "0001519061"
    row["ticker"] = "TSE"
    row["candidateActionIds"] = ["action-tse"]
    fact = _fact()
    fact.update(
        {
            "actionId": "action-tse",
            "issuerCik": "0001519061",
            "ticker": "TSE",
            "effectiveDate": "2021-09-14",
            "transformationKind": "PRIMARY_SEC_SAME_SYMBOL_REORGANIZATION",
            "successorSymbol": "TSE",
            "successorSharesPerEntryShare": 2,
        }
    )
    with pytest.raises(ValueError, match="same-symbol reorganization"):
        mod._resolution(row, fact)


def test_effective_date_must_be_inside_horizon() -> None:
    fact = _fact()
    fact["effectiveDate"] = "2021-09-24"
    with pytest.raises(ValueError, match="outside event horizon"):
        mod._resolution(_row(), fact)


def test_non_numeric_terms_fail_closed() -> None:
    with pytest.raises(ValueError, match="invalid numeric"):
        mod._number("n/a")


def test_formatter_preserves_ratio() -> None:
    assert mod._format(Decimal("0.1150")) == "0.115"
