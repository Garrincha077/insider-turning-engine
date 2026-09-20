from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_final_residual13_resolution")


def _base_fact(cik: str, ticker: str, rows: int) -> dict[str, object]:
    return {
        "issuerCik": cik,
        "ticker": ticker,
        "expectedRows": rows,
        "mode": "UNCHANGED_COMMON",
        "successorSymbol": ticker,
        "successorIssuerCik": cik,
        "successorSharesPerEntryShare": 1.0,
        "cashPerEntryShare": 0.0,
        "primaryEvidence": [
            {
                "accession": "fixture",
                "evidenceDate": "2021-01-02",
                "fact": "fixture",
            }
        ],
    }


def _contract() -> dict[str, object]:
    facts: list[dict[str, object]] = []
    for (cik, ticker), rows in mod.EXPECTED_COUNTS.items():
        fact = _base_fact(cik, ticker, rows)
        if ticker == "ARWA":
            fact.update(
                mode="COMMON_TO_SUCCESSOR_COMMON",
                effectiveDate="2016-12-28",
                successorSymbol="VVPR",
                successorIssuerCik="0001681348",
            )
        elif ticker == "ATACU":
            fact.update(
                mode="UNIT_TO_COMMON_PLUS_RIGHT",
                effectiveDate="2018-08-22",
                successorSymbol="HFFG",
                successorSharesPerEntryShare=1.1,
            )
        elif ticker == "TPGE":
            fact.update(
                mode="COMMON_SYMBOL_CHANGE",
                effectiveDate="2018-08-01",
                successorSymbol="MGY",
            )
        elif ticker == "NBA.U":
            fact = {
                "issuerCik": cik,
                "ticker": ticker,
                "expectedRows": rows,
                "mode": "UNIT_TO_MULTI_COMPONENT_BASKET",
                "effectiveDate": "2021-08-13",
                "basket": [
                    {
                        "symbol": "MIMO",
                        "securityClass": "COMMON_STOCK",
                        "quantityPerEntryUnit": 1.0,
                    },
                    {
                        "symbol": "MIMO WS",
                        "securityClass": "PUBLIC_WARRANT",
                        "quantityPerEntryUnit": 1.0,
                    },
                ],
                "cashPerEntryShare": 0.0,
                "primaryEvidence": [
                    {
                        "accession": "fixture",
                        "evidenceDate": "2021-08-13",
                        "fact": "fixture",
                    }
                ],
            }
        facts.append(fact)
    return {
        "contractId": "phase1-b3-final-residual13-primary-evidence-v1",
        "scopeResidualKeySha256": mod.SOURCE_SCOPE_KEY_SHA256,
        "expectedResolutionRows": 13,
        "expectedResolutionKeySha256": mod.EXPECTED_RESOLUTION_KEY_SHA256,
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "identities": facts,
    }


def test_evidence_accepts_exact_identity_set(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(_contract()), encoding="utf-8")
    assert set(mod._load_evidence(path)) == set(mod.EXPECTED_COUNTS)


def test_nba_basket_cannot_drop_warrant(tmp_path: Path) -> None:
    payload = _contract()
    nba = next(
        item for item in payload["identities"] if item["ticker"] == "NBA.U"
    )
    nba["basket"] = nba["basket"][:1]
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly two"):
        mod._load_evidence(path)


def test_arwa_post_close_is_one_vvpr_not_unit_bundle() -> None:
    row = {
        "eventNumber": 1,
        "issuerCik": "0001622577",
        "ticker": "ARWA",
        "evaluationSession": "2016-06-30",
        "entrySession": "2016-07-01",
        "horizon": 126,
        "targetExitSession": "2016-12-30",
        "pivotDate": "2016-07-22",
    }
    fact = next(
        item for item in _contract()["identities"] if item["ticker"] == "ARWA"
    )
    out = mod._resolve_row(row, fact)
    assert out["resolutionDecision"] == "TRANSFORMED_HOLDER_CONSIDERATION"
    assert out["successorSymbol"] == "VVPR"
    assert out["successorSharesPerEntryShare"] == 1.0


def test_atacu_pre_close_target_remains_unit() -> None:
    row = {
        "eventNumber": 1,
        "issuerCik": "0001680873",
        "ticker": "ATACU",
        "evaluationSession": "2017-08-25",
        "entrySession": "2017-08-28",
        "horizon": 126,
        "targetExitSession": "2018-02-28",
        "pivotDate": "2018-01-16",
    }
    fact = next(
        item for item in _contract()["identities"] if item["ticker"] == "ATACU"
    )
    out = mod._resolve_row(row, fact)
    assert out["resolutionDecision"] == "SAME_SECURITY_CONTINUITY"
    assert out["successorSymbol"] == "ATACU"
