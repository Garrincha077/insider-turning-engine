from __future__ import annotations

import csv
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
gaps = importlib.import_module("research_phase1_security_gap_diagnostics")


def test_max_gap_detail_returns_bracketing_observations() -> None:
    assert gaps._max_gap_detail([0, 1, 12, 13], 0, 13) == (10, 1, 12)
    assert gaps._max_gap_detail([0, 1, 11, 12], 0, 12) == (9, 1, 11)


def test_max_gap_detail_tie_breaks_to_first_gap() -> None:
    assert gaps._max_gap_detail([0, 11, 22], 0, 22) == (10, 0, 11)


def test_load_frozen_gap_rows_is_performance_blind_and_bounded(tmp_path: Path) -> None:
    path = tmp_path / "ledger.csv"
    fields = [
        "eventNumber",
        "issuerCik",
        "ticker",
        "entrySession",
        "horizon",
        "targetExitSession",
        "state",
        "resolutionSource",
        "maxInternalGapSessions",
        "longInternalGapCandidate",
        "raw_126",
        "excess_126",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "eventNumber": "1",
                "issuerCik": "0001",
                "ticker": "TEST",
                "entrySession": "2020-01-02",
                "horizon": "126",
                "targetExitSession": "2020-07-02",
                "state": "UNRESOLVED_CONTINUITY",
                "resolutionSource": "long_internal_gap",
                "maxInternalGapSessions": "10",
                "longInternalGapCandidate": "true",
                "raw_126": "MUST_NOT_BE_PARSED",
                "excess_126": "MUST_NOT_BE_PARSED",
            }
        )
    rows = gaps._load_frozen_gap_rows(path)
    assert len(rows) == 1
    assert "raw_126" not in rows[0]
    assert "excess_126" not in rows[0]


def test_load_frozen_gap_rows_rejects_2023(tmp_path: Path) -> None:
    path = tmp_path / "ledger.csv"
    fields = [
        "eventNumber",
        "issuerCik",
        "ticker",
        "entrySession",
        "horizon",
        "targetExitSession",
        "state",
        "resolutionSource",
        "maxInternalGapSessions",
        "longInternalGapCandidate",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "eventNumber": "1",
                "issuerCik": "0001",
                "ticker": "TEST",
                "entrySession": "2020-01-02",
                "horizon": "252",
                "targetExitSession": "2023-01-03",
                "state": "UNRESOLVED_CONTINUITY",
                "resolutionSource": "long_internal_gap",
                "maxInternalGapSessions": "10",
                "longInternalGapCandidate": "true",
            }
        )
    with pytest.raises(ValueError, match="sealed OOS boundary"):
        gaps._load_frozen_gap_rows(path)


def test_below_threshold_frozen_row_hard_fails(tmp_path: Path) -> None:
    path = tmp_path / "ledger.csv"
    fields = [
        "eventNumber",
        "issuerCik",
        "ticker",
        "entrySession",
        "horizon",
        "targetExitSession",
        "state",
        "resolutionSource",
        "maxInternalGapSessions",
        "longInternalGapCandidate",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "eventNumber": "1",
                "issuerCik": "0001",
                "ticker": "TEST",
                "entrySession": "2020-01-02",
                "horizon": "63",
                "targetExitSession": "2020-04-02",
                "state": "UNRESOLVED_CONTINUITY",
                "resolutionSource": "long_internal_gap",
                "maxInternalGapSessions": "9",
                "longInternalGapCandidate": "true",
            }
        )
    with pytest.raises(ValueError, match="below predeclared threshold"):
        gaps._load_frozen_gap_rows(path)
