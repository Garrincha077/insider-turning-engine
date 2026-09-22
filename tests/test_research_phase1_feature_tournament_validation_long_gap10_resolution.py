from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_long_gap10_resolution"
)


def _row() -> dict[str, object]:
    return {
        "eventNumber": 3928,
        "issuerCik": "0001854458",
        "ticker": "NETC.U",
        "horizon": 126,
        "maxInternalGapSessions": 19,
    }


def _gap() -> dict[str, str]:
    return {
        "eventNumber": "3928",
        "issuerCik": "0001854458",
        "ticker": "NETC.U",
        "horizon": "126",
        "previousObservedSession": "2022-03-15",
        "firstMissingSession": "2022-03-16",
        "lastMissingSession": "2022-04-11",
        "nextObservedSession": "2022-04-12",
        "maxInternalGapSessions": "19",
    }


def _identity() -> dict[str, object]:
    return {
        "securityKind": "SPAC_UNIT",
        "unitComposition": "one Class A common share plus one-half redeemable warrant",
        "resolutionDecision": "SAME_SECURITY_CONTINUITY",
        "transformationKind": "",
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "successorIssuerCik": "0001854458",
        "successorSymbol": "NETC.U",
        "successorSharesPerEntryShare": 1,
        "cashPerEntryShare": 0,
        "effectiveDatePolicy": "NEXT_OBSERVED_SESSION_AFTER_FROZEN_GAP",
        "primaryEvidence": [
            {"accession": "0001104659-22-001979"},
            {"accession": "0001558370-22-008586"},
        ],
    }


def test_netcu_gap_and_unit_identity_are_frozen() -> None:
    row = _row()
    gap = _gap()
    mod._validate_gap(row, gap)
    mod._validate_identity(row, _identity())


def test_gap_tuple_change_fails_closed() -> None:
    gap = _gap()
    gap["nextObservedSession"] = "2022-04-13"
    with pytest.raises(ValueError, match="frozen gap tuple changed"):
        mod._validate_gap(_row(), gap)


def test_unit_cannot_be_silently_mapped_to_component_common() -> None:
    identity = _identity()
    identity["successorSymbol"] = "NETC"
    with pytest.raises(ValueError, match="primary-evidence contract changed"):
        mod._validate_identity(_row(), identity)


def test_expected_partition_is_exact() -> None:
    assert len(mod.EXPECTED_GAPS) == 10
    assert len(mod.EXPECTED_ACCESSIONS) == 10
    assert mod.UNIT_TICKERS == {"ROCGU", "APMIU", "MCAGU", "NETC.U", "KACLU"}
