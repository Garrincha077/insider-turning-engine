from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_residual_evidence_audit"
)


def _residual_row(
    *,
    issuer: str = "0000000001",
    ticker: str = "AAA",
) -> dict[str, object]:
    return {
        "issuerCik": issuer,
        "ticker": ticker,
    }


def _unresolved_row(action_ids: str) -> dict[str, object]:
    return {
        "candidateActionIds": action_ids,
    }


def _b3_row(
    *,
    action_ids: list[str],
    issuer: str = "0000000001",
    ticker: str = "AAA",
    factor: float = 1.05,
    cash: float = 0.0,
    kind: str = "STOCK_DIVIDEND_QUANTITY",
) -> dict[str, object]:
    return {
        "issuerCik": issuer,
        "ticker": ticker,
        "sourceActionIds": action_ids,
        "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
        "transformationKind": kind,
        "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol": ticker,
        "successorSharesPerEntryShare": factor,
        "cashPerEntryShare": cash,
        "effectiveDate": "2020-01-02",
        "evidenceClass": "DIRECT_PROVIDER_TERMS",
        "classificationSourceRelease": "frozen-b3",
    }


def _b1_row(
    *,
    action_ids: list[str],
    issuer: str = "0000000001",
    ticker: str = "AAA",
    factor: str = "1.05",
    kind: str = "STOCK_DIVIDEND_QUANTITY",
) -> dict[str, object]:
    return {
        "issuerCik": issuer,
        "ticker": ticker,
        "sourceActionIds": action_ids,
        "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
        "transformationKind": kind,
        "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol": ticker,
        "shareQuantityFactor": factor,
        "effectiveDate": "2020-01-02",
    }


def test_provider_prefers_exact_b3_action_terms() -> None:
    result = mod._provider_match(
        _residual_row(),
        _unresolved_row("action-a"),
        [
            _b3_row(
                action_ids=["action-a"],
                factor=0.25,
                cash=12.5,
                kind="STOCK_AND_CASH_MERGER",
            )
        ],
        [
            _b1_row(
                action_ids=["action-a"],
                factor="0.25",
                kind="PASSIVE_HOLDER_STOCK_MERGER",
            )
        ],
    )

    assert result["category"] == "PROVIDER_ACTION_REUSE_B3"
    assert result["economicFingerprint"][4:] == ["0.25", "12.5"]


def test_provider_uses_b1_only_for_stock_dividend() -> None:
    result = mod._provider_match(
        _residual_row(),
        _unresolved_row("action-a"),
        [],
        [_b1_row(action_ids=["action-a"])],
    )

    assert result["category"] == "PROVIDER_ACTION_REUSE_B1_STOCK_DIVIDEND"
    assert result["economicFingerprint"][4:] == ["1.05", "0"]


def test_provider_rejects_non_stock_dividend_b1_fallback() -> None:
    with pytest.raises(
        ValueError,
        match="restricted to stock dividends",
    ):
        mod._provider_match(
            _residual_row(),
            _unresolved_row("action-a"),
            [],
            [
                _b1_row(
                    action_ids=["action-a"],
                    kind="PASSIVE_HOLDER_STOCK_MERGER",
                )
            ],
        )


def test_long_gap_unanimous_prior_security_is_candidate_only() -> None:
    rows = [
        {
            **_b3_row(action_ids=[]),
            "sourceActionIds": [],
            "effectiveDate": "2020-01-02",
            "evidenceClass": "SEC_MULTI_SOURCE_EXACT_CONTINUITY",
        },
        {
            **_b3_row(action_ids=[]),
            "sourceActionIds": [],
            "effectiveDate": "2020-02-03",
            "evidenceClass": "PRIMARY_SEC_ONE_SIDED_IDENTITY",
        },
    ]
    result = mod._long_gap_match(_residual_row(), rows)

    assert result["category"] == "LONG_GAP_PRIOR_SECURITY_CANDIDATE"
    assert result["priorMatchCount"] == 2
    assert result["effectiveDates"] == ["2020-01-02", "2020-02-03"]


def test_long_gap_without_prior_security_requires_primary_evidence() -> None:
    result = mod._long_gap_match(_residual_row(), [])

    assert result == {
        "category": "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED",
        "priorMatchCount": 0,
    }
