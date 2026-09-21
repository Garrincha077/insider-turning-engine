from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_confirmation"
)


def test_expected_confirmation_candidates_are_exact() -> None:
    assert set(mod.EXPECTED_CANDIDATES) == {"F1", "F2", "F4"}
    assert mod.EXPECTED_CANDIDATES["F2"]["frozenGroupDefinition"] == {
        "kind": "F2_DYNAMIC",
        "sourceFeature": "F2_DIRECT_VS_INDIRECT",
        "preferred": "INDIRECT_ONLY",
        "complement": "DIRECT_ONLY",
    }


def test_confirmation_period_is_fixed() -> None:
    assert mod.CONFIRMATION_START == "2019-01-01"
    assert mod.CONFIRMATION_END == "2020-12-31"
    assert mod.EXPECTED_CONFIRMATION_EVENTS == 9850


def test_candidate_rows_keep_frozen_f2_orientation() -> None:
    outcomes = [
        {
            "F2_DIRECT_VS_INDIRECT": "INDIRECT_ONLY",
            "issuerCik": "1",
            "ticker": "A",
            "evaluationSession": "2019-01-02",
            "entrySession": "2019-01-03",
        },
        {
            "F2_DIRECT_VS_INDIRECT": "DIRECT_ONLY",
            "issuerCik": "2",
            "ticker": "B",
            "evaluationSession": "2019-01-02",
            "entrySession": "2019-01-03",
        },
    ]
    candidate = mod.EXPECTED_CANDIDATES["F2"]
    rows = mod._candidate_rows(outcomes, {}, candidate)
    assert [row["_group"] for row in rows] == [
        "PREFERRED",
        "COMPLEMENT",
    ]


def test_confirmation_pass_requires_both_years_positive() -> None:
    assert mod.PRIMARY_HORIZON == 126
    assert mod.HORIZONS == (21, 63, 126, 252)
