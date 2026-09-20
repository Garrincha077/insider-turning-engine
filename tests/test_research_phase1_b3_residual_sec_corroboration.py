from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_residual_sec_corroboration")


def test_nearest_observations_are_time_ordered() -> None:
    rows = [
        {"knowledgeAt": "2020-01-02T20:00:00+00:00", "ticker": "ABC", "accession": "a"},
        {"knowledgeAt": "2020-03-04T20:00:00+00:00", "ticker": "ABC", "accession": "b"},
    ]
    before, after = mod._nearest(rows, "2020-02-01")
    assert before is not None and before["accession"] == "a"
    assert after is not None and after["accession"] == "b"


def test_gap_pivot_uses_frozen_first_missing_session() -> None:
    row = {
        "eventNumber": 1,
        "issuerCik": "0001",
        "ticker": "ABC",
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "horizon": 126,
        "targetExitSession": "2020-07-06",
        "resolutionSource": "long_internal_gap",
    }
    key = ("1", "0001", "ABC", "", "2020-01-03", "126", "2020-07-06")
    gaps = {key: {"firstMissingSession": "2020-03-02"}}
    pivot, kind = mod._pivot(row, gaps, {})
    assert pivot == "2020-03-02"
    assert kind == "FROZEN_LONG_GAP_START"
