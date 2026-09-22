from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod=importlib.import_module("research_monster_winner_max_existing_continuity")


def test_frozen_extension_horizons() -> None:
    assert mod.HORIZONS==(126,252)
    assert mod.SEALED_YEAR==2023
    assert mod.GAP_THRESHOLD==10


def test_mature_rows_only_emit_frozen_horizons() -> None:
    rows=[{
        "eventNumber":"1",
        "issuerCik":"0001",
        "ticker":"AAA",
        "evaluationSession":"2021-01-04",
        "entrySession":"2021-01-05",
        "targetExitSession126":"2021-07-06",
        "horizon126MatureAtBoundary":"true",
        "targetExitSession252":"2022-01-05",
        "horizon252MatureAtBoundary":"true",
        "F3_DRAWDOWN_252_GROUP":"PREFERRED",
        "F4_DISTANCE_BELOW_GROUP":"COMPLEMENT",
    }]
    out=mod._mature_rows(rows)
    assert len(out)==2
    assert {r["horizon"] for r in out}=={126,252}


def test_censored_horizon_is_not_emitted() -> None:
    rows=[{
        "eventNumber":"1",
        "issuerCik":"0001",
        "ticker":"AAA",
        "evaluationSession":"2022-08-01",
        "entrySession":"2022-08-02",
        "targetExitSession126":"2023-02-01",
        "horizon126MatureAtBoundary":"false",
        "targetExitSession252":"2023-08-02",
        "horizon252MatureAtBoundary":"false",
        "F3_DRAWDOWN_252_GROUP":"",
        "F4_DISTANCE_BELOW_GROUP":"",
    }]
    assert mod._mature_rows(rows)==[]
