from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_development_performance")
p0 = importlib.import_module("research_market_event_audit_v2")


def test_identity_metrics_use_frozen_p0_tiers() -> None:
    identity = {
        "sourceEventCount": 1000,
        "identityEligibleEvents": 950,
        "identityQuarantineEvents": 50,
        "quarantineStatusCounts": {
            "MISSING_REAL_TICKER": 30,
            "MULTIPLE_REAL_TICKERS": 10,
            "TICKER_SESSION_CIK_COLLISION": 5,
        },
    }
    annual = {
        "2016": {"identityEligible": 190, "exactEntryMatched": 170},
        "2017": {"identityEligible": 190, "exactEntryMatched": 171},
        "2018": {"identityEligible": 190, "exactEntryMatched": 172},
        "2019": {"identityEligible": 190, "exactEntryMatched": 173},
        "2020": {"identityEligible": 190, "exactEntryMatched": 174},
    }
    metrics = mod._identity_metrics(
        identity,
        entry_matched=sum(v["exactEntryMatched"] for v in annual.values()),
        annual_entry=annual,
        spy_coverage=1.0,
    )
    tier, _ = p0.select_data_quality_tier(metrics)

    assert metrics["identityMissing"] == 0.03
    assert metrics["totalIdentityProblem"] == 0.05
    assert tier == "C_EXPLORATORY"


def test_event_clock_requires_exact_next_xnys_session() -> None:
    sessions = p0._expected_sessions()
    event = {
        "evaluationSession": "2019-01-02",
        "entrySession": "2019-01-03",
    }
    index = mod._validate_event_clock(event, sessions)
    assert sessions[index] == "2019-01-02"

    bad = {
        "evaluationSession": "2019-01-02",
        "entrySession": "2019-01-04",
    }
    try:
        mod._validate_event_clock(bad, sessions)
    except ValueError as exc:
        assert "exact next XNYS" in str(exc)
    else:
        raise AssertionError("non-exact entry session must fail closed")
