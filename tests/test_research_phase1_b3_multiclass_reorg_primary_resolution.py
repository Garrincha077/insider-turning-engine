from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_b3_multiclass_reorg_primary_resolution"
)


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
            {"accession": "acc", "evidenceDate": "2020-01-01"}
        ],
    }


def _contract() -> dict[str, object]:
    return {
        "contractId": "phase1-b3-multiclass-reorg-primary-evidence-v1",
        "scopeResidualKeySha256": mod.SOURCE_SCOPE_KEY_SHA256,
        "expectedResolutionRows": 12,
        "expectedResolutionKeySha256": mod.EXPECTED_RESOLUTION_KEY_SHA256,
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "identities": [
            _same("0001635193", "GGO", 8),
            _same("0001471824", "TAGS", 1),
            {
                "issuerCik": "0001647088",
                "ticker": "EAGL",
                "expectedRows": 2,
                "resolutionDecision": "SYMBOL_CHANGED_SAME_SECURITY",
                "resultState": "SYMBOL_CHANGED_SAME_SECURITY",
                "transformationKind": "SAME_SECURITY_DOMESTICATION",
                "effectiveDate": "2017-11-30",
                "successorSymbol": "WSC",
                "successorIssuerCik": "0001647088",
                "successorSharesPerEntryShare": 1.0,
                "cashPerEntryShare": 0.0,
                "primaryEvidence": [
                    {"accession": "acc-eagl", "evidenceDate": "2017-11-29"}
                ],
            },
            {
                "issuerCik": "0001697152",
                "ticker": "FMCIU",
                "expectedRows": 1,
                "resolutionDecision": "DISCONTINUOUS_NO_COMPLETE_VALUATION",
                "resultState": "DISCONTINUOUS_NO_COMPLETE_VALUATION",
                "transformationKind":
                    "MULTI_LEG_UNIT_SEPARATION_UNVALUED_WARRANT",
                "effectiveDate": "2018-02-22",
                "successorSymbol": "",
                "successorIssuerCik": "0001697152",
                "successorSharesPerEntryShare": 0.0,
                "cashPerEntryShare": 0.0,
                "unitComposition": {
                    "commonShares": 1.0,
                    "rightsPerUnit": 1.0,
                    "warrantPerUnit": 0.5,
                    "rightConversionCommonShares": 0.1,
                },
                "primaryEvidence": [
                    {"accession": "acc-fmciu", "evidenceDate": "2018-02-22"}
                ],
                "completeHolderValuationRepresentableByFrozenShareCashSchema":
                    False,
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


def test_eagl_must_remain_one_to_one_wsc(tmp_path: Path) -> None:
    payload = _contract()
    payload["identities"][2]["successorSharesPerEntryShare"] = 0.5
    with pytest.raises(ValueError, match="EAGL continuation terms changed"):
        mod._load_evidence(_write(tmp_path, payload))


def test_fmciu_warrant_leg_cannot_be_dropped(tmp_path: Path) -> None:
    payload = _contract()
    payload["identities"][3][
        "completeHolderValuationRepresentableByFrozenShareCashSchema"
    ] = True
    with pytest.raises(ValueError, match="FMCIU representation boundary changed"):
        mod._load_evidence(_write(tmp_path, payload))


def test_fmciu_unit_composition_is_frozen(tmp_path: Path) -> None:
    payload = _contract()
    payload["identities"][3]["unitComposition"]["warrantPerUnit"] = 0.0
    with pytest.raises(ValueError, match="FMCIU unit composition changed"):
        mod._load_evidence(_write(tmp_path, payload))


def test_2023_primary_evidence_fails_closed(tmp_path: Path) -> None:
    payload = _contract()
    payload["identities"][0]["primaryEvidence"][0]["evidenceDate"] = "2023-01-01"
    with pytest.raises(ValueError, match="sealed OOS"):
        mod._load_evidence(_write(tmp_path, payload))
