from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_b3_common_security_primary_resolution"
)


def _fact(cik: str, ticker: str, rows: int) -> dict[str, object]:
    return {
        "issuerCik": cik,
        "ticker": ticker,
        "expectedRows": rows,
        "primaryEvidence": [
            {
                "accession": "fixture",
                "evidenceDate": "2020-01-02",
                "fact": "fixture",
            }
        ],
        "resolutionDecision": "SAME_SECURITY_CONTINUITY",
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "transformationKind": "",
        "successorSymbol": ticker,
        "successorIssuerCik": cik,
        "successorSharesPerEntryShare": 1.0,
        "cashPerEntryShare": 0.0,
    }


def _contract() -> dict[str, object]:
    return {
        "schemaVersion": "1.0.0",
        "contractId": "phase1-b3-common-security-primary-evidence-v1",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "scopeResidualKeySha256": mod.SOURCE_SCOPE_KEY_SHA256,
        "expectedResolutionRows": 19,
        "expectedResolutionKeySha256": mod.EXPECTED_RESOLUTION_KEY_SHA256,
        "identities": [
            _fact(cik, ticker, rows)
            for (cik, ticker), rows in mod.EXPECTED_COUNTS.items()
        ],
    }


def test_evidence_accepts_exact_frozen_identity_set(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(_contract()), encoding="utf-8")
    result = mod._load_evidence(path)
    assert set(result) == set(mod.EXPECTED_COUNTS)


def test_quantity_change_fails_closed(tmp_path: Path) -> None:
    payload = _contract()
    payload["identities"][0]["successorSharesPerEntryShare"] = 0.5
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="quantity changed"):
        mod._load_evidence(path)


def test_successor_ticker_change_fails_closed(tmp_path: Path) -> None:
    payload = _contract()
    payload["identities"][0]["successorSymbol"] = "OTHER"
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="successor symbol changed"):
        mod._load_evidence(path)


def test_2023_evidence_fails_closed(tmp_path: Path) -> None:
    payload = _contract()
    payload["identities"][0]["primaryEvidence"][0]["evidenceDate"] = "2023-01-03"
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="sealed OOS"):
        mod._load_evidence(path)
