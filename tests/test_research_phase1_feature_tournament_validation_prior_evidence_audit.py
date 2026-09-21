from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_prior_evidence_audit"
)


def _prior(
    *,
    source: str,
    action_ids: list[str],
    quantity: float = 1.1,
    state: str = "TRANSFORMED_HOLDER_CONSIDERATION",
) -> dict[str, object]:
    return {
        "_source": source,
        "issuerCik": "0000000001",
        "ticker": "TEST",
        "resultState": state,
        "successorSymbol": "TEST",
        "successorSharesPerEntryShare": quantity,
        "cashPerEntryShare": 0,
        "sourceActionIds": action_ids,
        "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
        "transformationKind": "STOCK_DIVIDEND_QUANTITY",
        "effectiveDate": "2021-06-01",
    }


def _provider_row() -> dict[str, object]:
    return {
        "issuerCik": "0000000001",
        "ticker": "TEST",
        "candidateActionIds": "a1",
    }


def test_provider_exact_action_reuse_accepts_same_economics() -> None:
    prior = [
        _prior(source="B1", action_ids=["a1"]),
        {
            **_prior(source="B3", action_ids=["a1"]),
            "resolutionDecision": "SAME_SCHEMA_DIFFERENCE_ALLOWED",
        },
    ]
    result = mod._provider_evidence(_provider_row(), prior)
    assert result["category"] == "PROVIDER_EXACT_ACTION_PRIOR_CANDIDATE"
    assert result["priorMatchCount"] == 2
    assert result["priorSources"] == ["B1", "B3"]


def test_provider_exact_action_reuse_fails_closed_on_economic_conflict() -> None:
    prior = [
        _prior(source="B1", action_ids=["a1"], quantity=1.1),
        _prior(source="B3", action_ids=["a1"], quantity=1.2),
    ]
    result = mod._provider_evidence(_provider_row(), prior)
    assert result["category"] == "PROVIDER_PRIOR_EVIDENCE_CONFLICT"


def test_provider_without_prior_action_match_needs_primary() -> None:
    result = mod._provider_evidence(
        _provider_row(),
        [_prior(source="B3", action_ids=["different"])],
    )
    assert result["category"] == "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED"


def test_long_gap_prior_same_security_is_candidate_not_resolution() -> None:
    row = {
        "issuerCik": "0000000001",
        "ticker": "TEST",
    }
    prior = [
        {
            "_source": "B3",
            "issuerCik": "0000000001",
            "ticker": "TEST",
            "resultState": "PRICE_CONTINUOUS_ADJUSTED",
            "successorSymbol": "TEST",
            "successorSharesPerEntryShare": 1,
            "cashPerEntryShare": 0,
            "sourceActionIds": [],
            "effectiveDate": "2020-08-01",
        }
    ]
    result = mod._long_gap_evidence(row, prior)
    assert result["category"] == "LONG_GAP_PRIOR_SECURITY_CANDIDATE"
    assert result["priorMatchCount"] == 1
