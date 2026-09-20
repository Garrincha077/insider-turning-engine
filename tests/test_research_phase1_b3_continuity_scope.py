from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
scope = importlib.import_module("research_phase1_b3_continuity_scope")


def test_scope_constants_lock_authoritative_counts() -> None:
    assert scope.EXPECTED_UNRESOLVED == 264
    assert scope.EXPECTED_LONG_GAP == 200
    assert scope.EXPECTED_PROVIDER == 64


def test_scope_safe_fields_exclude_performance_and_prices() -> None:
    lowered = {field.lower() for field in scope.SAFE_FIELDS}
    assert not any(field.startswith(("raw_", "excess_", "mae_")) for field in lowered)
    assert not {"open", "high", "low", "close"} & lowered


def test_frozen_scope_rejects_2023(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scope, "EXPECTED_UNRESOLVED", 1)
    monkeypatch.setattr(scope, "EXPECTED_LONG_GAP", 1)
    monkeypatch.setattr(scope, "EXPECTED_PROVIDER", 0)

    ledger = tmp_path / "ledger.csv"
    fields = list(scope.SAFE_FIELDS)
    row = {field: "" for field in fields}
    row.update(
        eventNumber="1",
        issuerCik="0001",
        ticker="ABC",
        evaluationSession="2020-01-02",
        entrySession="2020-01-03",
        horizon="252",
        targetExitSession="2023-01-03",
        state="UNRESOLVED_CONTINUITY",
        resolutionSource="long_internal_gap",
        maxInternalGapSessions="10",
        longInternalGapCandidate="True",
    )
    with ledger.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)

    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "status": "PHASE1_SECURITY_CONTINUITY_LEDGER_COMPLETE",
                "performanceRead": False,
                "oosOpened": False,
                "productionScoringChanged": False,
                "gapThresholdSessions": 10,
                "unresolvedEventHorizonRows": 1,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sealed OOS"):
        scope.freeze(
            ledger_path=ledger,
            ledger_summary_path=summary,
            output_path=tmp_path / "out.json",
            source_release="x",
            source_asset="x",
            source_asset_digest="sha256:x",
        )
