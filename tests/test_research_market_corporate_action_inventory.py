from __future__ import annotations

import csv
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
inventory = importlib.import_module("research_market_corporate_action_inventory")


def _events(path: Path, *, entry: str = "2020-01-03") -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "ticker",
                "evaluationSession",
                "entrySession",
                "raw_126",
                "excess_126",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "ticker": "abc",
                "evaluationSession": "2020-01-02",
                "entrySession": entry,
                "raw_126": "not-read",
                "excess_126": "not-read",
            }
        )


def test_event_tickers_ignore_performance_values(tmp_path: Path) -> None:
    path = tmp_path / "events.csv"
    _events(path)
    assert inventory._event_tickers(path) == ["ABC"]


def test_event_tickers_reject_sealed_oos_metadata(tmp_path: Path) -> None:
    path = tmp_path / "events.csv"
    _events(path, entry="2023-01-03")
    with pytest.raises(ValueError, match="sealed OOS boundary"):
        inventory._event_tickers(path)


def test_normalize_preserves_identity_terms() -> None:
    row = {
        "id": "x",
        "corporate_action_type": "name_changes",
        "old_symbol": "AI",
        "old_cusip": "041356205",
        "new_symbol": "AAIC",
        "new_cusip": "041356205",
        "process_date": "2020-10-26",
    }
    result = inventory._normalize("name_changes", row)
    assert result["actionDate"] == "2020-10-26"
    assert result["old_symbol"] == "AI"
    assert result["new_symbol"] == "AAIC"
    assert result["old_cusip"] == result["new_cusip"]
