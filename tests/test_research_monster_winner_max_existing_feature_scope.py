from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod=importlib.import_module("research_monster_winner_max_existing_feature_scope")


def test_extension_bounds_are_frozen() -> None:
    assert mod.EXTENSION_START=="2021-01-01"
    assert mod.EXTENSION_END=="2022-12-31"
    assert mod.DATA_BOUNDARY=="2022-12-30"
    assert mod.SEALED_YEAR==2023
    assert mod.HORIZONS==(126,252)
    assert mod.CANDIDATES==("F3_DRAWDOWN_252","F4_DISTANCE_BELOW")


def test_multi_root_market_paths_require_exactly_one_per_year(tmp_path: Path) -> None:
    a=tmp_path/"a"
    b=tmp_path/"b"
    a.mkdir()
    b.mkdir()
    (a/"raw-feature-market-2021.csv").write_text("x\n",encoding="utf-8")
    (b/"raw-feature-market-2022.csv").write_text("x\n",encoding="utf-8")
    paths=mod._market_paths_multi([a,b],"raw-feature-market",range(2021,2023))
    assert [p.name for p in paths]==[
        "raw-feature-market-2021.csv",
        "raw-feature-market-2022.csv",
    ]

    (a/"raw-feature-market-2022.csv").write_text("x\n",encoding="utf-8")
    with pytest.raises(ValueError,match="exactly one"):
        mod._market_paths_multi([a,b],"raw-feature-market",range(2022,2023))
