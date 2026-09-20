from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_spac_unit_primary_resolution")


def _fact(
    *,
    cik: str,
    unit: str,
    common: str,
    target_max: str,
) -> dict[str, object]:
    return {
        "issuerCik": cik,
        "unitSymbol": unit,
        "componentCommonSymbol": common,
        "componentRightSymbol": unit + "R",
        "componentWarrantSymbol": unit + "W",
        "unitSecurityKind": "SPAC_UNIT",
        "unitComposition": "fixture",
        "separationAccession": "acc-sep",
        "separationEventDate": "2018-01-02",
        "separationEffectiveDate": "2018-01-03",
        "postGapEvidence": [
            {
                "accession": "acc-post",
                "evidenceDate": target_max,
                "fact": "fixture",
            }
        ],
        "scopedTargetExitMax": target_max,
        "primaryConclusion": "ORIGINAL_UNIT_REMAINED_LISTED_UNDER_SAME_SYMBOL",
        "resolutionDecision": "SAME_SECURITY_CONTINUITY",
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "successorSymbol": unit,
        "successorSharesPerEntryShare": 1.0,
        "cashPerEntryShare": 0.0,
    }


def _contract() -> dict[str, object]:
    return {
        "schemaVersion": "1.0.0",
        "contractId": "phase1-b3-spac-unit-primary-evidence-v1",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "scopeResidualKeySha256": mod.SOURCE_SCOPE_KEY_SHA256,
        "expectedResolutionRows": 4,
        "expectedResolutionKeySha256": mod.EXPECTED_RESOLUTION_KEY_SHA256,
        "identities": [
            _fact(
                cik="0001705771",
                unit="DOTAU",
                common="DOTA",
                target_max="2018-09-24",
            ),
            _fact(
                cik="0001735041",
                unit="GLACU",
                common="GLAC",
                target_max="2019-08-02",
            ),
        ],
    }


def test_primary_evidence_accepts_exact_two_unit_identities(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(_contract()), encoding="utf-8")
    result = mod._load_evidence(path)
    assert set(result) == mod.EXPECTED_IDENTITIES


def test_component_common_cannot_equal_unit_symbol(tmp_path: Path) -> None:
    payload = _contract()
    payload["identities"][0]["componentCommonSymbol"] = "DOTAU"
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="not distinct"):
        mod._load_evidence(path)


def test_changed_successor_unit_symbol_fails_closed(tmp_path: Path) -> None:
    payload = _contract()
    payload["identities"][1]["successorSymbol"] = "GLAC"
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unit symbol changed"):
        mod._load_evidence(path)


def test_2023_evidence_fails_closed(tmp_path: Path) -> None:
    payload = _contract()
    payload["identities"][0]["postGapEvidence"][0]["evidenceDate"] = "2023-01-03"
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="sealed OOS"):
        mod._load_evidence(path)


def test_business_combination_before_target_fails_closed() -> None:
    row = {
        "entrySession": "2018-01-03",
        "targetExitSession": "2018-09-24",
    }
    fact = _fact(
        cik="0001705771",
        unit="DOTAU",
        common="DOTA",
        target_max="2018-09-24",
    )
    fact["businessCombinationEffectiveDate"] = "2018-09-20"
    with pytest.raises(ValueError, match="transformation occurred"):
        mod._assert_target_bracket(row, fact)
