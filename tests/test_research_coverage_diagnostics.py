"""Safeguard the explanatory report; never increase scoring eligibility."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from research_coverage_diagnostics import CoverageEvidenceError, summarize


def inputs():
    research = {
        "runId": "run_fixture_001", "asOf": "2026-11-01T11:00:00Z",
        "companies": [{"issuerCik": cik, "ticker": f"SYM{i}"}
                      for i, cik in enumerate(("0000000001", "0000000002",
                                               "0000000003", "0000000004"))],
        "researchScores": [
            {"issuerCik": "0000000001", "total": 42.0, "reasons": ["STATE_HELD"]},
            {"issuerCik": "0000000002", "total": None,
             "reasons": ["UNRESOLVED_IDENTITY"]},
            {"issuerCik": "0000000003", "total": None,
             "reasons": ["INSUFFICIENT_COMPONENT_DATA", "STALE_DATA_HOLD"]},
            {"issuerCik": "0000000004", "total": None,
             "reasons": ["STALE_DATA_HOLD", "UNRESOLVED_AMENDMENT"]},
        ],
        "coverage": {
            "completeScores": 1, "expectedSecDays": ["2026-10-29", "2026-10-30"],
            "missingSecDays": [], "days": [
                {"day": "2026-10-29", "discoveredFilings": 2, "storedFilings": 2,
                 "failures": 0, "quarantinedRows": 2, "complete": False},
                {"day": "2026-10-30", "discoveredFilings": 1, "storedFilings": 1,
                 "failures": 0, "quarantinedRows": 0, "complete": True},
            ],
        },
        "readiness": {"dashboard": {"status": "PARTIAL"},
                      "predictive": {"status": "BLOCKED"}},
    }
    daily = {"runId": "run_fixture_001", "states": {
        "0000000003": {"reason_codes": ["MISSING_CLUSTER", "MISSING_CONVICTION",
                                       "STALE_DATA_HOLD"]},
    }}
    identity = {"runId": "run_fixture_001", "requestedIssuerCount": 3,
                "resolvedIssuerCount": 2, "unresolved": [
                    {"cik": "0000000002", "reasons": ["NO_CURRENT_LISTING"]},
                ]}
    market = {"requested": 12, "available": 12, "failures": {},
              "requiredCacheSession": "2026-10-30"}
    quarantine = {"runId": "run_fixture_001", "days": {
        "2026-10-29": {"INVALID_ROW": 1, "MISSING_TRANSACTION": 1},
    }}
    return research, daily, identity, market, quarantine


def test_reasons_reconcile_without_spurious_score_or_source_success():
    inputs_value = inputs()
    before = copy.deepcopy(inputs_value)
    result = summarize(*inputs_value)
    assert inputs_value == before
    assert result["scoring"]["completeScores"] == 1
    assert result["scoring"]["issuerCount"] == 4
    assert result["scoring"]["blockedByPrimaryReason"] == {
        "UNRESOLVED_IDENTITY": 1, "UNRESOLVED_AMENDMENT": 1,
        "JOINT_OWNER_SCORE_NOT_RECOMPUTED": 0, "SOURCE_QUARANTINE": 0,
        "INSUFFICIENT_COMPONENT_DATA": 1,
    }
    assert result["scoring"]["missingComponentTagCountsOverlapping"] == {
        "MISSING_CLUSTER": 1, "MISSING_CONVICTION": 1,
    }
    assert result["scoring"]["staleHoldOverlayCount"] == 2
    assert result["sec"]["expectedDays"] == result["sec"]["checkpointDays"] == 2
    assert result["sec"]["missingDays"] == []
    assert result["sec"]["quarantinedRows"] == 2
    assert result["sec"]["incompleteCheckpointDays"] == 1
    assert result["sec"]["quarantineCauseTotals"]["MISSING_TRANSACTION"] == 1
    assert result["readiness"]["predictive"]["status"] == "BLOCKED"
    text = json.dumps(result)
    assert "0000000002" not in text
    assert "SYM" not in text
    assert "telegram" not in text.lower()


@pytest.mark.parametrize("part,field,value,match", [
    (0, "runId", "different", "runId"),
    (0, "companies", [], "shape"),
    (2, "resolvedIssuerCount", 3, "inventory"),
    (3, "available", 13, "availability"),
    (4, "days", {}, "cause count"),
])
def test_fail_closed_when_source_evidence_inconsistent(part, field, value, match):
    inputs_value = list(inputs())
    inputs_value[part][field] = value
    with pytest.raises(CoverageEvidenceError, match=match):
        summarize(*inputs_value)


def test_unknown_score_reason_or_false_complete_does_not_become_score():
    args = list(inputs())
    args[0]["researchScores"][1]["reasons"] = ["MYSTERY"]
    with pytest.raises(CoverageEvidenceError, match="unique primary"):
        summarize(*args)
    args = list(inputs())
    args[0]["researchScores"][2]["total"] = 20
    with pytest.raises(CoverageEvidenceError, match="missing-score blocker"):
        summarize(*args)


def test_missed_day_is_not_misclassified_as_parser_quarantine():
    args = list(inputs())
    args[0]["coverage"]["expectedSecDays"].append("2026-10-31")
    args[0]["coverage"]["missingSecDays"] = ["2026-10-31"]
    result = summarize(*args)
    assert result["sec"]["missingDays"] == ["2026-10-31"]
    assert result["sec"]["quarantinedRows"] == 2
    args[0]["coverage"]["missingSecDays"] = []
    with pytest.raises(CoverageEvidenceError, match="SEC day inventory"):
        summarize(*args)
