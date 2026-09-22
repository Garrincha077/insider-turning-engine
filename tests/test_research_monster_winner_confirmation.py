from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod=importlib.import_module("research_monster_winner_confirmation")

def test_confirmation_scope_is_frozen() -> None:
    assert mod.EXPECTED_EVENTS==9850
    assert mod.EXPECTED_BY_YEAR=={"2019":4529,"2020":5321}
    assert mod.CANDIDATES==("F3_DRAWDOWN_252","F4_DISTANCE_BELOW")

def test_confirmation_market_window_excludes_oos(tmp_path: Path) -> None:
    for year in range(2019,2023):
        d=tmp_path/str(year)
        d.mkdir()
        (d/f"canonical-market-{year}.csv").write_text("x\n",encoding="utf-8")
    assert len(mod._market_paths(tmp_path))==4
    (tmp_path/"2023").mkdir()
    try:
        mod._market_paths(tmp_path)
    except ValueError as exc:
        assert "sealed OOS" in str(exc)
    else:
        raise AssertionError("2023 mount must fail")

def test_candidate_binding_rejects_reselection(tmp_path: Path) -> None:
    p=tmp_path/"discovery.json"
    p.write_text(
        '{"status":"MONSTER_WINNER_ENRICHMENT_V1_DISCOVERY_COMPLETE",'
        '"familyCandidates":{"F1":{"status":"NO_MONSTER_DISCOVERY_CANDIDATE"},'
        '"F2":{"status":"NO_MONSTER_DISCOVERY_CANDIDATE"},'
        '"F3":{"status":"MONSTER_DISCOVERY_FAMILY_CANDIDATE_FROZEN","variantId":"F3_RETURN_63"},'
        '"F4":{"status":"MONSTER_DISCOVERY_FAMILY_CANDIDATE_FROZEN","variantId":"F4_DISTANCE_BELOW"}}}',
        encoding="utf-8",
    )
    try:
        mod._load_discovery_result(p)
    except ValueError as exc:
        assert "F3 discovery candidate changed" in str(exc)
    else:
        raise AssertionError("candidate reselection must fail")
