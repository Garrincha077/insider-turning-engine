from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_stage_b_unresolved_scope"
)


def _summary() -> dict[str, object]:
    return {
        "status": "PHASE1_SECURITY_CONTINUITY_LEDGER_COMPLETE",
        "eventRowsScanned": 1,
        "eventHorizonRows": 4,
        "unresolvedEventHorizonRows": 1,
        "performanceRead": False,
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "gapThresholdSessions": 10,
    }


def _patch_small(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "EXPECTED_SOURCE_EVENTS", 1)
    monkeypatch.setattr(mod, "EXPECTED_SOURCE_ROWS", 4)
    monkeypatch.setattr(mod, "EXPECTED_UNRESOLVED_ROWS", 1)


def test_freezes_only_unresolved_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_small(monkeypatch)
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps(_summary()), encoding="utf-8")
    ledger = tmp_path / "ledger.csv"
    fields = [
        "eventNumber",
        "issuerCik",
        "ticker",
        "evaluationSession",
        "entrySession",
        "horizon",
        "targetExitSession",
        "state",
        "successorSymbol",
        "resolutionSource",
        "candidateActionTypes",
        "adjustedActionTypes",
        "candidateActionIds",
        "maxInternalGapSessions",
        "longInternalGapCandidate",
    ]
    with ledger.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "eventNumber": 1,
                "issuerCik": "0001",
                "ticker": "TEST",
                "evaluationSession": "2020-01-02",
                "entrySession": "2020-01-03",
                "horizon": 126,
                "targetExitSession": "2020-07-02",
                "state": "UNRESOLVED_CONTINUITY",
                "successorSymbol": "",
                "resolutionSource": "long_internal_gap",
                "candidateActionTypes": "",
                "adjustedActionTypes": "",
                "candidateActionIds": "",
                "maxInternalGapSessions": 12,
                "longInternalGapCandidate": "True",
            }
        )
    output = tmp_path / "scope.json"
    result = mod.run(ledger_path=ledger, summary_path=summary, output_path=output)
    assert result["unresolvedRows"] == 1
    assert result["longInternalGapRows"] == 1
    assert result["rowsByResolutionSource"] == {"long_internal_gap": 1}
    assert result["rows"][0]["ticker"] == "TEST"


def test_rejects_performance_column(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_small(monkeypatch)
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps(_summary()), encoding="utf-8")
    ledger = tmp_path / "ledger.csv"
    ledger.write_text(
        "eventNumber,issuerCik,ticker,evaluationSession,entrySession,horizon,"
        "targetExitSession,state,raw_126\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="performance fields"):
        mod.run(
            ledger_path=ledger,
            summary_path=summary,
            output_path=tmp_path / "out.json",
        )
