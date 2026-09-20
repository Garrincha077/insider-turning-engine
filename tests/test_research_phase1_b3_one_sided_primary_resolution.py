from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_one_sided_primary_resolution")


def _same(cik: str, ticker: str, rows: int) -> dict[str, object]:
    return {
        "issuerCik": cik,
        "ticker": ticker,
        "expectedRows": rows,
        "resolutionDecision": "SAME_SECURITY_CONTINUITY",
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "transformationKind": "",
        "successorSymbol": ticker,
        "successorIssuerCik": cik,
        "successorSharesPerEntryShare": 1.0,
        "cashPerEntryShare": 0.0,
        "primaryEvidence": [
            {
                "accession": "acc",
                "evidenceDate": "2021-01-01",
            }
        ],
    }


def _contract() -> dict[str, object]:
    return {
        "schemaVersion": "1.0.0",
        "contractId": "phase1-b3-one-sided-primary-evidence-v1",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "scopeResidualKeySha256": mod.SOURCE_SCOPE_KEY_SHA256,
        "expectedResolutionRows": 20,
        "expectedResolutionKeySha256": mod.EXPECTED_RESOLUTION_KEY_SHA256,
        "identities": [
            _same("0000865058", "NSEC", 7),
            _same("0001122063", "FTNW", 5),
            {
                "issuerCik": "0001314475",
                "ticker": "LOV",
                "expectedRows": 7,
                "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
                "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
                "transformationKind": "ADS_EXCHANGE",
                "effectiveDate": "2017-11-02",
                "successorSymbol": "LOV",
                "successorIssuerCik": "0001705338",
                "successorSharesPerEntryShare": 0.1,
                "cashPerEntryShare": 0.0,
                "primaryEvidence": [
                    {
                        "accession": "acc-lov",
                        "evidenceDate": "2017-11-02",
                    }
                ],
            },
            {
                "issuerCik": "0001330421",
                "ticker": "BV",
                "expectedRows": 1,
                "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
                "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
                "transformationKind": "CASH_MERGER",
                "effectiveDate": "2018-02-01",
                "successorSymbol": "",
                "successorIssuerCik": "",
                "successorSharesPerEntryShare": 0.0,
                "cashPerEntryShare": 5.5,
                "primaryEvidence": [
                    {
                        "accession": "acc-bv",
                        "evidenceDate": "2018-02-01",
                    }
                ],
            },
        ],
    }


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_exact_identity_contract_passes(tmp_path: Path) -> None:
    result = mod._load_evidence(_write(tmp_path, _contract()))
    assert set(result) == set(mod.EXPECTED_COUNTS)


def test_lov_exchange_ratio_is_frozen(tmp_path: Path) -> None:
    payload = _contract()
    payload["identities"][2]["successorSharesPerEntryShare"] = 1.0
    with pytest.raises(ValueError, match="LOV ADS exchange terms changed"):
        mod._load_evidence(_write(tmp_path, payload))


def test_lov_successor_issuer_is_frozen(tmp_path: Path) -> None:
    payload = _contract()
    payload["identities"][2]["successorIssuerCik"] = "0001314475"
    with pytest.raises(ValueError, match="LOV successor issuer changed"):
        mod._load_evidence(_write(tmp_path, payload))


def test_bv_cash_consideration_is_frozen(tmp_path: Path) -> None:
    payload = _contract()
    payload["identities"][3]["cashPerEntryShare"] = 5.0
    with pytest.raises(ValueError, match="BV cash merger terms changed"):
        mod._load_evidence(_write(tmp_path, payload))


def test_same_security_cannot_change_successor_ticker(tmp_path: Path) -> None:
    payload = _contract()
    payload["identities"][0]["successorSymbol"] = "OTHER"
    with pytest.raises(ValueError, match="same-security terms changed"):
        mod._load_evidence(_write(tmp_path, payload))


def test_2023_primary_evidence_fails_closed(tmp_path: Path) -> None:
    payload = _contract()
    payload["identities"][1]["primaryEvidence"][0]["evidenceDate"] = "2023-01-01"
    with pytest.raises(ValueError, match="sealed OOS"):
        mod._load_evidence(_write(tmp_path, payload))


def test_holder_transformation_must_fall_inside_horizon() -> None:
    row = {
        "eventNumber": 1,
        "issuerCik": "0001330421",
        "ticker": "BV",
        "evaluationSession": "2017-01-01",
        "entrySession": "2017-01-02",
        "horizon": 21,
        "targetExitSession": "2017-02-01",
        "pivotDate": "2017-01-15",
    }
    fact = _contract()["identities"][3]
    with pytest.raises(ValueError, match="outside event horizon"):
        mod._resolution_for(row, fact)
