from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_provider_primary_resolution")


def _contract() -> dict[str, object]:
    base = {
        "schemaVersion": "1.0.0",
        "contractId": "phase1-b3-provider-primary-resolution-evidence-v1",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "scopeResidualKeySha256": mod.EXPECTED_SCOPE_DIGEST,
        "evidence": [],
    }
    facts = []
    for cik, old, new, date, acc, conflict in (
        ("0001679688", "CLNY", "DBRG", "2021-06-22", "0001679688-21-000065", True),
        ("0001717547", "CLNC", "BRSP", "2021-06-25", "0001717547-21-000024", False),
    ):
        facts.append({
            "issuerCik": cik,
            "oldSymbol": old,
            "successorSymbol": new,
            "securityClass": "CLASS A COMMON STOCK",
            "effectiveSymbolDate": date,
            "secEventDate": date,
            "secAccession": acc,
            "resolutionDecision": "SYMBOL_CHANGED_SAME_SECURITY",
            "transformationKind": "SAME_SECURITY_SYMBOL_CHANGE",
            "resultState": "SYMBOL_CHANGED_SAME_SECURITY",
            "successorSharesPerEntryShare": 1.0,
            "cashPerEntryShare": 0.0,
            "providerCusipConflict": conflict,
        })
    base["evidence"] = facts
    return base


def test_primary_evidence_contract_accepts_only_frozen_two_identities(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(_contract()), encoding="utf-8")
    result = mod._evidence(path)
    assert set(result) == {("0001679688", "CLNY"), ("0001717547", "CLNC")}


def test_non_one_to_one_terms_fail_closed(tmp_path: Path) -> None:
    payload = _contract()
    payload["evidence"][0]["successorSharesPerEntryShare"] = 0.5
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="non-1:1"):
        mod._evidence(path)


def test_2023_primary_evidence_fails_closed(tmp_path: Path) -> None:
    payload = _contract()
    payload["evidence"][0]["secEventDate"] = "2023-01-01"
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="sealed OOS"):
        mod._evidence(path)


def test_security_class_change_fails_closed(tmp_path: Path) -> None:
    payload = _contract()
    payload["evidence"][1]["securityClass"] = "PREFERRED STOCK"
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Class A common"):
        mod._evidence(path)
