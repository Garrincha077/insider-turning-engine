from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_hsdt_gap_interval"
)


def test_frozen_hsdt_identity() -> None:
    assert mod.EXPECTED_EVENT == 3657
    assert mod.EXPECTED_CIK == "0001610853"
    assert mod.EXPECTED_TICKER == "HSDT"
    assert mod.EXPECTED_ENTRY == "2021-11-16"
    assert mod.EXPECTED_TARGET == "2022-05-18"
    assert mod.EXPECTED_GAP == 29


def test_market_files_reject_2023(tmp_path: Path) -> None:
    for year in (2021, 2022, 2023):
        path = tmp_path / f"canonical-market-{year}.csv"
        path.write_text(
            "date,ticker,volume,trade_count,terminal_candidate\n",
            encoding="utf-8",
        )
    with pytest.raises(ValueError, match="sealed 2023"):
        mod._market_files(tmp_path)


def test_candidate_requires_exact_hsdt_row() -> None:
    payload = {
        "rows": [
            {
                "eventNumber": 3657,
                "issuerCik": "0001610853",
                "ticker": "HSDT",
                "entrySession": "2021-11-16",
                "targetExitSession": "2022-05-18",
                "horizon": 126,
                "maxInternalGapSessions": 29,
                "evidenceAudit": {
                    "category": "LONG_GAP_PRIOR_SECURITY_CANDIDATE"
                },
            }
        ]
    }
    row = mod._candidate(payload)
    assert row["ticker"] == "HSDT"


def test_candidate_rejects_changed_gap() -> None:
    payload = {
        "rows": [
            {
                "eventNumber": 3657,
                "issuerCik": "0001610853",
                "ticker": "HSDT",
                "entrySession": "2021-11-16",
                "targetExitSession": "2022-05-18",
                "horizon": 126,
                "maxInternalGapSessions": 28,
                "evidenceAudit": {
                    "category": "LONG_GAP_PRIOR_SECURITY_CANDIDATE"
                },
            }
        ]
    }
    with pytest.raises(ValueError, match="maxInternalGapSessions"):
        mod._candidate(payload)
