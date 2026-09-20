from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_surviving_unit_primary_resolution")


def _fact(cik: str, ticker: str, rows: int, mode: str) -> dict[str, object]:
    fact: dict[str, object] = {
        "issuerCik": cik,
        "ticker": ticker,
        "expectedRows": rows,
        "mode": mode,
        "successorSymbol": ticker,
        "primaryEvidence": [
            {"accession": "fixture", "evidenceDate": "2021-01-02", "fact": "fixture"}
        ],
    }
    if mode == "UNIT_SYMBOL_CHANGE":
        fact["symbolChangeEffectiveDate"] = "2019-04-15"
        fact["successorSymbol"] = "BROGU"
    return fact


def _contract() -> dict[str, object]:
    return {
        "contractId": "phase1-b3-surviving-unit-primary-evidence-v1",
        "scopeResidualKeySha256": mod.SOURCE_SCOPE_KEY_SHA256,
        "expectedResolutionRows": 11,
        "expectedResolutionKeySha256": mod.EXPECTED_RESOLUTION_KEY_SHA256,
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "identities": [
            _fact(\n                cik,\n                ticker,\n                rows,\n                "UNIT_SYMBOL_CHANGE" if ticker == "TWLVU" else "UNCHANGED_UNIT",\n            )
            for (cik, ticker), rows in mod.EXPECTED_COUNTS.items()
        ],
    }


def test_evidence_accepts_exact_identity_set(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(_contract()), encoding="utf-8")
    result = mod._load_evidence(path)
    assert set(result) == set(mod.EXPECTED_COUNTS)


def test_2023_evidence_fails_closed(tmp_path: Path) -> None:
    payload = _contract()
    payload["identities"][0]["primaryEvidence"][0]["evidenceDate"] = "2023-01-03"
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="sealed OOS"):
        mod._load_evidence(path)


def test_twlvu_target_before_change_keeps_symbol() -> None:
    fact = _fact("0001726146", "TWLVU", 4, "UNIT_SYMBOL_CHANGE")
    row = {
        "eventNumber": 1,
        "issuerCik": "0001726146",
        "ticker": "TWLVU",
        "evaluationSession": "2018-01-02",
        "entrySession": "2018-01-03",
        "horizon": 126,
        "targetExitSession": "2019-01-30",
        "pivotDate": "2018-10-05",
    }
    out = mod._resolution(row, fact)
    assert out["resolutionDecision"] == "SAME_SECURITY_CONTINUITY"
    assert out["successorSymbol"] == "TWLVU"


def test_twlvu_target_after_change_uses_brogu() -> None:
    fact = _fact("0001726146", "TWLVU", 4, "UNIT_SYMBOL_CHANGE")
    row = {
        "eventNumber": 1,
        "issuerCik": "0001726146",
        "ticker": "TWLVU",
        "evaluationSession": "2018-01-02",
        "entrySession": "2018-01-03",
        "horizon": 252,
        "targetExitSession": "2019-07-31",
        "pivotDate": "2018-10-05",
    }
    out = mod._resolution(row, fact)
    assert out["resolutionDecision"] == "SYMBOL_CHANGED_SAME_SECURITY"
    assert out["successorSymbol"] == "BROGU"
