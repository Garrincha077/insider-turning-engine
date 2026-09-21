from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_pope_adjudication"
)


def _boundary() -> dict[str, object]:
    return {
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }


def _conflict() -> dict[str, object]:
    return {
        **_boundary(),
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_POPE_PRIOR_CONTINUITY_"
            "CONFLICT_FROZEN"
        ),
        "sourceResidualScopeSha256": "sha256:test",
        "conflictRows": 1,
        "conflictRowSha256": "sha256:row",
        "adjudicated": False,
        "row": {
            "currentEventNumber": 16553,
            "currentResolutionSource": "provider",
            "issuerCik": "0000784011",
            "ticker": "POPE",
            "evaluationSession": "2019-06-24",
            "entrySession": "2019-06-25",
            "horizon": 252,
            "targetExitSession": "2020-06-24",
            "matchStatus": "PRIOR_ECONOMIC_CONFLICT",
            "priorSources": ["B1", "B3"],
            "priorMatches": [
                {
                    "source": "B1",
                    "economicFingerprint": {
                        "successorSymbol": "RYN",
                        "quantityFactor": "3.929",
                        "cashPerEntryShare": "0",
                    },
                },
                {
                    "source": "B3",
                    "economicFingerprint": {
                        "successorSymbol": "RYN",
                        "quantityFactor": "3.929",
                        "cashPerEntryShare": "125",
                    },
                },
            ],
        },
    }


def _evidence() -> dict[str, object]:
    return {
        **_boundary(),
        "contractId": (
            "phase1-feature-tournament-pope-primary-evidence-v1"
        ),
        "subject": {
            "issuerCik": "0000784011",
            "historicalTicker": "POPE",
            "evaluationSession": "2019-06-24",
            "entrySession": "2019-06-25",
            "horizon": 252,
            "targetExitSession": "2020-06-24",
            "effectiveDate": "2020-05-08",
        },
        "primarySource": {
            "form": "8-K",
            "accession": "0000052827-20-000138",
            "document": "https://www.sec.gov/example",
        },
        "passiveHolderPolicy": {
            "policy": "NO_VALID_ELECTION_DEFAULT",
            "result": {
                "resolutionDecision": (
                    "TRANSFORMED_HOLDER_CONSIDERATION"
                ),
                "transformationKind": "PASSIVE_HOLDER_STOCK_MERGER",
                "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
                "successorSymbol": "RYN",
                "successorSharesPerEntryShare": 3.929,
                "cashPerEntryShare": 0,
            },
        },
        "conflictAdjudication": {
            "b1EconomicSemantics": "SUPPORTED_BY_PRIMARY_SOURCE",
            "b3EconomicSemantics": (
                "REJECTED_FOR_THIS_PASSIVE_HOLDER_POLICY"
            ),
        },
    }


def _write(
    tmp_path: Path,
    name: str,
    payload: dict[str, object],
) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_adjudicates_to_passive_holder_stock_only(
    tmp_path: Path,
) -> None:
    result = mod.run(
        conflict_path=_write(tmp_path, "conflict.json", _conflict()),
        evidence_path=_write(tmp_path, "evidence.json", _evidence()),
        output_path=tmp_path / "out.json",
        verify_frozen_asset=False,
    )

    assert result["adjudicated"] is True
    assert result["remainingPOPEConflictRows"] == 0
    resolution = result["resolution"]
    assert resolution["successorSymbol"] == "RYN"
    assert resolution["successorSharesPerEntryShare"] == 3.929
    assert resolution["cashPerEntryShare"] == 0
    assert result["performanceRead"] is False
    assert result["featureDiscoveryOutcomesOpened"] is False


def test_rejects_combined_full_stock_and_cash_terms(
    tmp_path: Path,
) -> None:
    evidence = _evidence()
    policy = evidence["passiveHolderPolicy"]
    assert isinstance(policy, dict)
    result = policy["result"]
    assert isinstance(result, dict)
    result["cashPerEntryShare"] = 125

    with pytest.raises(
        ValueError,
        match="authoritative passive-holder terms changed",
    ):
        mod.run(
            conflict_path=_write(
                tmp_path,
                "conflict.json",
                _conflict(),
            ),
            evidence_path=_write(
                tmp_path,
                "evidence.json",
                evidence,
            ),
            output_path=tmp_path / "out.json",
            verify_frozen_asset=False,
        )
