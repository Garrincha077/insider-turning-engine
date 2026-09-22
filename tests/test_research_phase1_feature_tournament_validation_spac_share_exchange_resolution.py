from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
mod=importlib.import_module(
    "research_phase1_feature_tournament_validation_spac_share_exchange_resolution"
)


def _row():
    return {
        "eventNumber":106,"issuerCik":"0001832459","ticker":"TBA",
        "evaluationSession":"2021-01-21","entrySession":"2021-01-22",
        "horizon":126,"targetExitSession":"2021-07-23",
        "resolutionSource":"provider",
        "candidateActionIds":["a","b"],
        "candidateActionTypes":["name_changes","stock_mergers"],
        "evidenceAudit":{"category":"PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED"},
    }


def _fact():
    return {
        "issuerCik":"0001832459","ticker":"TBA","actionIds":["b","a"],
        "effectiveDate":"2021-06-28","successorSymbol":"IS",
        "successorSharesPerEntryShare":1,"cashPerEntryShare":0,
        "resolutionDecision":"TRANSFORMED_HOLDER_CONSIDERATION",
        "transformationKind":"PRIMARY_SEC_SPAC_STOCK_EXCHANGE",
        "resultState":"TRANSFORMED_HOLDER_CONSIDERATION",
        "primaryEvidence":[{"accession":"x"}],
    }


def test_frozen_counts_and_digest():
    assert mod.EXPECTED_SOURCE_ROWS==19
    assert mod.EXPECTED_TARGET_ROWS==8
    assert mod.EXPECTED_REMAINING_ROWS==11
    assert mod.EXPECTED_TARGET_DIGEST.startswith("sha256:")


def test_one_for_one_spac_resolution():
    r=mod._resolution(_row(),_fact())
    assert r["successorSymbol"]=="IS"
    assert r["successorSharesPerEntryShare"]=="1"
    assert r["cashPerEntryShare"]=="0"


def test_action_set_must_match_exactly():
    fact=_fact()
    fact["actionIds"]=["a","c"]
    with pytest.raises(ValueError,match="action set"):
        mod._resolution(_row(),fact)


def test_quantity_must_be_one():
    fact=_fact()
    fact["successorSharesPerEntryShare"]=0.5
    with pytest.raises(ValueError,match="holder economics"):
        mod._resolution(_row(),fact)


def test_effective_date_inside_horizon():
    fact=_fact()
    fact["effectiveDate"]="2021-08-01"
    with pytest.raises(ValueError,match="outside event horizon"):
        mod._resolution(_row(),fact)
