from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_residual_multisource_synthesis")


def _row() -> dict[str, object]:
    return {
        "eventNumber": 1,
        "issuerCik": "0000000001",
        "ticker": "ABC",
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "horizon": 126,
        "targetExitSession": "2020-07-06",
        "resolutionSource": "long_internal_gap",
        "candidateActionIds": "",
        "candidateActionTypes": "",
        "pivotDate": "2020-03-02",
        "corroborationStatus": "EXPECTED_TICKER_BOTH_SIDES",
        "securityTitleStatus": "TITLE_SET_EXACT_MATCH",
        "beforeSecurityTitles": ["COMMON STOCK"],
        "afterSecurityTitles": ["COMMON STOCK"],
        "form345CorroborationStatus": "EXPECTED_TICKER_BOTH_SIDES",
        "beforeObservation": {
            "issuerCik": "0000000001",
            "ticker": "ABC",
            "accession": "a",
            "knowledgeAt": "2020-02-01T12:00:00Z",
        },
        "afterObservation": {
            "issuerCik": "0000000001",
            "ticker": "ABC",
            "accession": "b",
            "knowledgeAt": "2020-04-01T12:00:00Z",
        },
        "form345BeforeObservation": {
            "issuerCik": "0000000001",
            "ticker": "ABC",
            "accession": "c",
            "filingDate": "2020-02-03",
        },
        "form345AfterObservation": {
            "issuerCik": "0000000001",
            "ticker": "ABC",
            "accession": "d",
            "filingDate": "2020-04-03",
        },
    }


def test_exact_multisource_same_security_is_promotable() -> None:
    assert mod._promotable(_row()) is True


def test_title_overlap_only_fails_closed() -> None:
    row = _row()
    row["securityTitleStatus"] = "TITLE_SET_OVERLAP"
    assert mod._promotable(row) is False


def test_ticker_change_fails_closed() -> None:
    row = _row()
    row["afterObservation"] = {
        "issuerCik": "0000000001",
        "ticker": "XYZ",
        "accession": "b",
        "knowledgeAt": "2020-04-01T12:00:00Z",
    }
    row["corroborationStatus"] = "TICKER_CHANGED_AFTER_PIVOT"
    assert mod._promotable(row) is False


def test_provider_identity_action_fails_closed() -> None:
    row = _row()
    row["candidateActionIds"] = "action-1"
    row["candidateActionTypes"] = "name_changes"
    assert mod._promotable(row) is False


def test_mismatched_form345_issuer_fails_closed() -> None:
    row = _row()
    row["form345AfterObservation"] = {
        "issuerCik": "0000000002",
        "ticker": "ABC",
        "accession": "d",
        "filingDate": "2020-04-03",
    }
    assert mod._promotable(row) is False


def test_2023_evidence_is_rejected() -> None:
    try:
        mod._assert_pre2023("2023-01-03", "fixture")
    except ValueError as exc:
        assert "sealed OOS" in str(exc)
    else:
        raise AssertionError("2023+ evidence was not rejected")
