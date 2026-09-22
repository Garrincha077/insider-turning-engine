from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_cbtx_symbol_change"
)


def _row() -> dict[str, object]:
    return {
        "eventNumber": 7087,
        "issuerCik": "0001473844",
        "ticker": "CBTX",
        "evaluationSession": "2022-06-08",
        "entrySession": "2022-06-09",
        "horizon": 126,
        "targetExitSession": "2022-12-08",
        "resolutionSource": "provider",
        "candidateActionIds": ["a3cb78f9-b741-4301-93d4-6bfa64c30882"],
        "candidateActionTypes": ["name_changes"],
        "evidenceAudit": {
            "category": "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED"
        },
    }


def _fact() -> dict[str, object]:
    return {
        **mod._key_object(_row()),
        "actionId": "a3cb78f9-b741-4301-93d4-6bfa64c30882",
        "effectiveDate": "2022-10-01",
        "resolutionDecision": "SYMBOL_CHANGED_SAME_SECURITY",
        "transformationKind": "SAME_SECURITY_SYMBOL_CHANGE",
        "resultState": "SYMBOL_CHANGED_SAME_SECURITY",
        "successorSymbol": "STEL",
        "successorSharesPerEntryShare": 1,
        "cashPerEntryShare": 0,
        "primaryEvidence": [{"accession": "x"}],
    }


def test_cbtx_symbol_change() -> None:
    out = mod._resolution(_row(), _fact())
    assert out["successorSymbol"] == "STEL"
    assert out["successorSharesPerEntryShare"] == "1"
    assert out["cashPerEntryShare"] == "0"


def test_allegiance_ratio_cannot_enter_cbtx_holder() -> None:
    fact = _fact()
    fact["successorSharesPerEntryShare"] = 1.4184
    with pytest.raises(ValueError, match="share quantity"):
        mod._resolution(_row(), fact)
