from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_residual91_scope")


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "eventNumber": 1,
        "issuerCik": "0000000001",
        "ticker": "abc",
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "horizon": 126,
        "targetExitSession": "2020-07-06",
        "resolutionSource": "long_internal_gap",
        "residualReason": "NO_MATCHING_PRIOR_B1_EVIDENCE",
        "pivotDate": "2020-03-02",
        "pivotKind": "FROZEN_LONG_GAP_START",
        "corroborationStatus": "EXPECTED_TICKER_BOTH_SIDES",
        "securityTitleStatus": "TITLE_SET_OVERLAP",
        "form345CorroborationStatus": "EXPECTED_TICKER_BOTH_SIDES",
        "candidateActionTypes": "",
        "candidateActionIds": "",
        "maxInternalGapSessions": "14",
    }
    row.update(overrides)
    return row


def test_scope_row_normalizes_identity_and_bucket() -> None:
    out = mod._scope_row(_row())
    assert out["ticker"] == "ABC"
    assert out["issuerCik"] == "0000000001"
    assert out["horizon"] == 126
    assert out["evidenceBucket"] == (
        "EXPECTED_TICKER_BOTH_SIDES|TITLE_SET_OVERLAP|"
        "EXPECTED_TICKER_BOTH_SIDES"
    )


def test_provider_ambiguity_is_preserved_not_resolved() -> None:
    out = mod._scope_row(
        _row(
            resolutionSource="provider",
            residualReason="PROVIDER_AMBIGUOUS_REQUIRES_PRIMARY_EVIDENCE",
            candidateActionTypes="name_changes",
            candidateActionIds="action-1",
        )
    )
    assert out["resolutionSource"] == "provider"
    assert out["candidateActionTypes"] == "name_changes"
    assert out["candidateActionIds"] == "action-1"


def test_2023_row_is_rejected() -> None:
    try:
        mod._scope_row(_row(targetExitSession="2023-01-03"))
    except ValueError as exc:
        assert "sealed OOS" in str(exc)
    else:
        raise AssertionError("2023+ row was not rejected")


def test_invalid_date_is_rejected() -> None:
    try:
        mod._scope_row(_row(pivotDate=""))
    except ValueError as exc:
        assert "invalid ISO date" in str(exc)
    else:
        raise AssertionError("missing pivot date was not rejected")
