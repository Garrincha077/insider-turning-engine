from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_monster_winner_discovery")


def test_monster_thresholds_are_frozen() -> None:
    assert mod.LABEL_SPECS["M100_252_CLOSE"] == (252, 2.0)
    assert mod.LABEL_SPECS["M200_252_CLOSE"] == (252, 3.0)
    assert mod.LABEL_SPECS["M500_252_CLOSE"] == (252, 6.0)
    assert mod.LABEL_SPECS["M100_126_CLOSE"] == (126, 2.0)


def test_positive_crossing_has_priority_over_incomplete_path() -> None:
    result = mod._label(
        values=[10.0, None, 21.0, None],
        sessions=["d1", "d2", "d3", "d4"],
        entry_open=10.0,
        multiple=2.0,
        mandatory_unvalued=True,
        deterministic_effective=False,
    )
    assert result["state"] == "POSITIVE"
    assert result["firstCrossingSession"] == "d3"


def test_no_crossing_incomplete_path_is_unknown() -> None:
    result = mod._label(
        values=[10.0, None, None, 15.0],
        sessions=["d1", "d2", "d3", "d4"],
        entry_open=10.0,
        multiple=2.0,
        mandatory_unvalued=False,
        deterministic_effective=True,
    )
    assert result["state"] == "UNKNOWN"


def test_no_crossing_complete_path_is_negative() -> None:
    values = [10.0] * 100
    result = mod._label(
        values=values,
        sessions=[f"d{i}" for i in range(100)],
        entry_open=10.0,
        multiple=2.0,
        mandatory_unvalued=False,
        deterministic_effective=True,
    )
    assert result["state"] == "NEGATIVE"


def test_primary_density_keeps_unknowns_in_denominator() -> None:
    counts = {"N": 10, "positive": 2, "negative": 3, "unknown": 5}
    assert mod._density(counts) == 0.2
    assert mod._evaluable_hit_rate(counts) == 0.4


def test_f2_dual_orientation_is_fixed() -> None:
    row = {"F2_DIRECT_VS_INDIRECT": "INDIRECT_ONLY"}
    assert mod._membership(
        row,
        "F2_INDIRECT_VS_DIRECT",
        {},
    ) == "PREFERRED"
    assert mod._membership(
        row,
        "F2_DIRECT_VS_INDIRECT",
        {},
    ) == "COMPLEMENT"


def test_cash_holder_path_is_constant_after_effective_date() -> None:
    terms = {
        "decision": "TRANSFORMED_HOLDER_CONSIDERATION",
        "kind": "CASH_MERGER",
        "terminalTicker": "",
        "marketQuantity": 0.0,
        "legalQuantity": 0.0,
        "cash": 15.0,
        "basket": [],
    }
    maps = {"OLD": {"2020-01-01": (10.0, 11.0, 100, 10, False)}}
    assert mod._holder_close(
        day="2020-01-01",
        ticker="OLD",
        terms=terms,
        effective_date="2020-01-02",
        maps=maps,
    ) == 11.0
    assert mod._holder_close(
        day="2020-01-02",
        ticker="OLD",
        terms=terms,
        effective_date="2020-01-02",
        maps=maps,
    ) == 15.0


def test_stock_merger_applies_frozen_quantity_after_effective_date() -> None:
    terms = {
        "decision": "TRANSFORMED_HOLDER_CONSIDERATION",
        "kind": "STOCK_MERGERS",
        "terminalTicker": "NEW",
        "marketQuantity": 0.5,
        "legalQuantity": 0.5,
        "cash": 2.0,
        "basket": [],
    }
    maps = {
        "OLD": {"2020-01-01": (10.0, 11.0, 100, 10, False)},
        "NEW": {"2020-01-02": (30.0, 32.0, 100, 10, False)},
    }
    assert mod._holder_close(
        day="2020-01-02",
        ticker="OLD",
        terms=terms,
        effective_date="2020-01-02",
        maps=maps,
    ) == 18.0
