from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
_mod = importlib.import_module("research_phase1_b1_corrected_tail_attribution")


def _canonical(event_number: int = 1) -> dict[str, str]:
    return {
        "issuerCik": f"{event_number:010d}",
        "ticker": f"T{event_number}",
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


def _corrected(event_number: int = 1, *, excess: str = "0.1") -> dict[str, str]:
    return {
        "eventNumber": str(event_number),
        "issuerCik": f"{event_number:010d}",
        "ticker": f"T{event_number}",
        "evaluationSession": "2016-01-04",
        "entrySession": "2016-01-05",
        "entryOpen": "10",
        "horizon": "126",
        "targetExitSession": "2016-07-05",
        "continuityState": "PRICE_CONTINUOUS_ADJUSTED",
        "valuationKind": "PRICE_CONTINUOUS_ADJUSTED",
        "correctedRaw": "0.2",
        "correctedExcess": excess,
        "valuationStatus": "VALUED" if excess else "MISSING_EXACT_TERMINAL_HOLDER_BAR",
    }


def test_join_restores_frozen_metadata_without_changing_corrected_value_basis() -> None:
    joined = _mod._join_corrected_to_canonical([_corrected()], [_canonical()])
    assert len(joined) == 1
    row = joined[0]
    assert row["eventNumber"] == "1"
    assert row["opportunisticOwnerCount"] == "2"
    assert row["rawOpportunisticPurchaseRows"] == "3"
    assert row["raw_126"] == "0.2"
    assert row["excess_126"] == "0.1"
    assert row["valuationStatus"] == "VALUED"


def test_join_hard_fails_on_corrected_canonical_identity_mismatch() -> None:
    corrected = _corrected()
    corrected["ticker"] = "WRONG"
    with pytest.raises(ValueError, match="identity-date mismatch"):
        _mod._join_corrected_to_canonical([corrected], [_canonical()])


def test_join_hard_fails_on_exit_date_mismatch() -> None:
    corrected = _corrected()
    corrected["targetExitSession"] = "2016-07-06"
    with pytest.raises(ValueError, match="identity-date mismatch"):
        _mod._join_corrected_to_canonical([corrected], [_canonical()])


def test_mature_corrected_row_requires_corrected_raw() -> None:
    corrected = _corrected()
    corrected["correctedRaw"] = ""
    with pytest.raises(ValueError, match="missing correctedRaw"):
        _mod._join_corrected_to_canonical([corrected], [_canonical()])


def test_corrected_reproduction_matches_persisted_primary_summary() -> None:
    mature = _mod._join_corrected_to_canonical([_corrected()], [_canonical()])
    summary = {
        "horizons": {
            "126": {
                "B1ContinuityCorrected": {
                    "maturedOutcomeCount": 1,
                    "spyExcessMean": 0.1,
                    "spyExcessMedian": 0.1,
                    "spyExcessWinRate": 1.0,
                }
            }
        }
    }
    result = _mod._corrected_reproduction(mature, summary)
    assert result["maturedOutcomeCount"] == 1
    assert result["spyExcessMean"] == pytest.approx(0.1)


def test_corrected_reproduction_rejects_changed_mean() -> None:
    mature = _mod._join_corrected_to_canonical([_corrected()], [_canonical()])
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
        _mod._corrected_reproduction(mature, summary)


def test_corrected_global_top_one_percent_reuses_floor_cut_and_frozen_tie_order() -> None:
    rows = []
    for index in range(1, 101):
        row = _canonical(index)
        row["issuerCik"] = f"{index:010d}"
        row["ticker"] = f"T{index:03d}"
        row["excess_126"] = "1.0" if index in {1, 2} else str(index / 1000)
        rows.append(row)
    result, top = _mod.base._global_tail(rows)
    assert result["count"] == 1
    assert len(top) == 1
    assert top[0]["issuerCik"] == "0000000001"


def test_corrected_sanity_rejects_2023_top_event_date() -> None:
    row = _canonical()
    row["exit_126"] = "2023-01-03"
    failures = _mod.base._sanity_failures(row)
    assert "SEALED_DATE_exit_126" in failures


def test_top_set_metadata_is_descriptive_only() -> None:
    rows = [
        {
            **_canonical(1),
            "continuityState": "TRANSFORMED_HOLDER_CONSIDERATION",
            "valuationKind": "FROZEN_RESOLUTION_STOCK_TRANSFORMATION",
        },
        {
            **_canonical(2),
            "continuityState": "PRICE_CONTINUOUS_ADJUSTED",
            "valuationKind": "PRICE_CONTINUOUS_ADJUSTED",
        },
    ]
    metadata = _mod._top_set_metadata(rows)
    assert metadata["continuityStates"] == {
        "PRICE_CONTINUOUS_ADJUSTED": 1,
        "TRANSFORMED_HOLDER_CONSIDERATION": 1,
    }
