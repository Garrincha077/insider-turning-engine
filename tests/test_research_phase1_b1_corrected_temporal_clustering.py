from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
_mod = importlib.import_module("research_phase1_b1_corrected_temporal_clustering")


def _row(
    evaluation: str,
    excess: float,
    *,
    issuer: str = "0000000001",
    entry: str = "2016-01-05",
) -> dict[str, str]:
    return {
        "evaluationSession": evaluation,
        "entrySession": entry,
        "issuerCik": issuer,
        "excess_126": str(excess),
    }


def test_bucket_assignment_is_frozen_for_month_and_quarter() -> None:
    assert _mod._bucket_key("2018-05-14", "month") == "2018-05"
    assert _mod._bucket_key("2018-05-14", "quarter") == "2018-Q2"
    assert _mod._bucket_key("2020-12-31", "quarter") == "2020-Q4"


def test_bucket_assignment_hard_fails_on_2023() -> None:
    with pytest.raises(ValueError, match="sealed OOS boundary"):
        _mod._bucket_key("2023-01-03", "month")


def test_longest_run_semantics() -> None:
    assert _mod._longest_run([True, True, False, True]) == 2
    assert _mod._longest_run([False, False, False]) == 0
    assert _mod._longest_run([True, True, True]) == 3


def test_monthly_concentration_arithmetic() -> None:
    rows = [
        _row("2016-01-04", 0.10, issuer="1"),
        _row("2016-01-11", -0.05, issuer="1"),
        _row("2016-01-20", 0.20, issuer="2"),
        _row("2016-02-01", -0.10, issuer="3"),
        _row("2016-02-10", 0.05, issuer="4"),
        _row("2016-03-01", 0.30, issuer="5"),
    ]
    result = _mod._bucket_diagnostics(rows, "month")
    buckets = result["buckets"]
    assert [item["bucket"] for item in buckets] == ["2016-01", "2016-02", "2016-03"]
    assert [item["count"] for item in buckets] == [3, 2, 1]
    assert buckets[0]["uniqueIssuers"] == 2
    assert buckets[0]["largestIssuerEventCount"] == 2
    concentration = result["concentration"]
    assert concentration["fiveBusiestEventShare"] == pytest.approx(1.0)
    assert concentration["maxBucketEventCount"] == 3
    assert concentration["maxBucketEventShare"] == pytest.approx(0.5)
    assert concentration["eventCountHhi"] == pytest.approx(14 / 36)


def test_bucket_stability_uses_non_empty_bucket_sequence_only() -> None:
    rows = [
        _row("2016-01-04", 0.10),
        _row("2016-03-04", 0.20),
        _row("2016-04-04", -0.10),
        _row("2016-06-04", -0.20),
    ]
    stability = _mod._bucket_diagnostics(rows, "month")["stability"]
    assert stability["longestPositiveMeanRun"] == 2
    assert stability["longestNonPositiveMeanRun"] == 2


def test_leave_one_year_out_semantics() -> None:
    rows = [
        _row("2016-01-04", 0.10),
        _row("2017-01-04", -0.20),
        _row("2018-01-04", 0.30),
        _row("2019-01-04", -0.40),
        _row("2020-01-04", 0.50),
    ]
    result = _mod._leave_one_year_out(rows)
    assert set(result) == {"2016", "2017", "2018", "2019", "2020"}
    assert result["2016"]["count"] == 4
    assert result["2016"]["mean"] == pytest.approx(0.05)
    assert result["2020"]["mean"] == pytest.approx(-0.05)


def test_entry_session_clustering_reuses_frozen_group_count_arithmetic() -> None:
    rows = [
        _row("2016-01-04", 0.1, entry="2016-01-05"),
        _row("2016-01-05", 0.2, entry="2016-01-05"),
        _row("2016-01-06", -0.1, entry="2016-01-07"),
    ]
    result = _mod._entry_session_reproduction(rows)
    assert result["uniqueEntrySessions"] == 2
    assert result["groups"] == 2
    assert result["events"] == 3
    assert result["maxEventsPerGroup"] == 2


def test_corrected_primary_reproduction_rejects_changed_summary() -> None:
    rows = [_row("2016-01-04", 0.1)]
    summary = {
        "horizons": {
            "126": {
                "B1ContinuityCorrected": {
                    "maturedOutcomeCount": 1,
                    "spyExcessMean": 0.2,
                    "spyExcessMedian": 0.1,
                    "spyExcessWinRate": 1.0,
                }
            }
        }
    }
    with pytest.raises(ValueError, match="spyExcessMean mismatch"):
        _mod._corrected_reproduction(rows, summary)


def test_exact_corrected_canonical_join_is_reused() -> None:
    canonical = {
        "issuerCik": "0000000001",
        "ticker": "AAA",
        "knowledgeAtFirst": "2016-01-03T12:00:00Z",
        "evaluationSession": "2016-01-04",
        "entrySession": "2016-01-05",
        "entryOpen": "10",
        "opportunisticOwnerCount": "2",
        "rawOpportunisticPurchaseRows": "3",
        "exit_21": "2016-02-03",
        "exit_63": "2016-04-04",
        "exit_126": "2016-07-05",
        "exit_252": "2017-01-04",
        "raw_126": "0.2",
        "excess_126": "0.1",
    }
    corrected = {
        "eventNumber": "1",
        "issuerCik": "0000000001",
        "ticker": "WRONG",
        "evaluationSession": "2016-01-04",
        "entrySession": "2016-01-05",
        "entryOpen": "10",
        "horizon": "126",
        "targetExitSession": "2016-07-05",
        "continuityState": "PRICE_CONTINUOUS_ADJUSTED",
        "valuationKind": "PRICE_CONTINUOUS_ADJUSTED",
        "correctedRaw": "0.2",
        "correctedExcess": "0.1",
        "valuationStatus": "VALUED",
    }
    with pytest.raises(ValueError, match="identity-date mismatch"):
        _mod.corrected_tail._join_corrected_to_canonical([corrected], [canonical])


def test_guardrails_are_locked_before_real_artifact_execution() -> None:
    assert _mod.GUARDRAILS == {
        "diagnosticOnly": True,
        "newFilterCreated": False,
        "researchOnly": True,
        "formalAlphaClaim": False,
        "oosEligible": False,
        "oosOpened": False,
        "calendarTimeHacStageOpened": False,
        "productionScoringChanged": False,
    }
