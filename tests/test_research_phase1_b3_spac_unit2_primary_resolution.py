from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_spac_unit2_primary_resolution")


def _fact(cik: str, unit: str, common: str, rows: int) -> dict[str, object]:
    return {
        "issuerCik": cik,
        "unitSymbol": unit,
        "componentCommonSymbol": common,
        "expectedRows": rows,
        "targetExitMax": "2021-01-01",
        "unitSecurityKind": "SPAC_UNIT",
        "primaryConclusion": "ORIGINAL_UNIT_REMAINED_LISTED_UNDER_SAME_SYMBOL",
        "resolutionDecision": "SAME_SECURITY_CONTINUITY",
        "transformationKind": "",
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "successorSymbol": unit,
        "successorSharesPerEntryShare": 1.0,
        "cashPerEntryShare": 0.0,
        "evidence": [{"accession": "acc", "evidenceDate": "2021-01-01"}],
    }


def _contract() -> dict[str, object]:
    return {
        "contractId": "phase1-b3-spac-unit2-primary-evidence-v1",
        "scopeResidualKeySha256": mod.SOURCE_SCOPE_KEY_SHA256,
        "expectedResolutionRows": 8,
        "expectedResolutionKeySha256": mod.EXPECTED_RESOLUTION_KEY_SHA256,
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "identities": [
            _fact("0001719893", "MTECU", "MTEC", 4),
            _fact("0001768910", "GRCYU", "GRCY", 2),
            _fact("0001777393", "SBE.U", "SBE", 1),
            _fact("0001785424", "FSRVU", "FSRV", 1),
        ],
    }


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    p = tmp_path / "evidence.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_exact_identity_contract_passes(tmp_path: Path) -> None:
    assert set(mod._load_evidence(_write(tmp_path, _contract()))) == set(mod.EXPECTED_COUNTS)


def test_component_common_cannot_equal_unit(tmp_path: Path) -> None:
    p = _contract()
    p["identities"][0]["componentCommonSymbol"] = "MTECU"
    with pytest.raises(ValueError, match="not distinct"):
        mod._load_evidence(_write(tmp_path, p))


def test_unit_successor_symbol_is_frozen(tmp_path: Path) -> None:
    p = _contract()
    p["identities"][1]["successorSymbol"] = "GRCY"
    with pytest.raises(ValueError, match="successor symbol changed"):
        mod._load_evidence(_write(tmp_path, p))


def test_2023_evidence_fails_closed(tmp_path: Path) -> None:
    p = _contract()
    p["identities"][2]["evidence"][0]["evidenceDate"] = "2023-01-01"
    with pytest.raises(ValueError, match="sealed OOS"):
        mod._load_evidence(_write(tmp_path, p))
