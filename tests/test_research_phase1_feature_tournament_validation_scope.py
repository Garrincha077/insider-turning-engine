from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_scope"
)


def _confirmation() -> dict[str, object]:
    return {
        "status": "PHASE1_INSIDER_FEATURE_TOURNAMENT_CONFIRMATION_COMPLETE",
        "definitionId": "PHASE1_INSIDER_FEATURE_TOURNAMENT_V1",
        "confirmedCandidateCount": 1,
        "confirmationComplete": True,
        "validationOpened": False,
        "validationEventOutcomesRead": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "confirmedCandidates": [
            {
                "family": "F2",
                "variantId": "F2_DIRECT_VS_INDIRECT",
                "coverageClass": "GENERAL_ELIGIBLE",
                "frozenGroupDefinition": {
                    "kind": "F2_DYNAMIC",
                    "sourceFeature": "F2_DIRECT_VS_INDIRECT",
                    "preferred": "INDIRECT_ONLY",
                    "complement": "DIRECT_ONLY",
                },
            }
        ],
    }


def test_accepts_only_frozen_f2_confirmation(tmp_path: Path) -> None:
    path = tmp_path / "confirmation.json"
    path.write_text(json.dumps(_confirmation()), encoding="utf-8")
    mod._assert_confirmation(path)


def test_rejects_confirmation_candidate_drift(tmp_path: Path) -> None:
    payload = _confirmation()
    confirmed = payload["confirmedCandidates"]
    assert isinstance(confirmed, list)
    candidate = confirmed[0]
    assert isinstance(candidate, dict)
    group = candidate["frozenGroupDefinition"]
    assert isinstance(group, dict)
    group["preferred"] = "DIRECT_ONLY"

    path = tmp_path / "confirmation.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="confirmed candidate changed"):
        mod._assert_confirmation(path)


def test_scope_digest_binds_f2_orientation_and_target() -> None:
    row = {
        "eventNumber": 1,
        "issuerCik": "0000000001",
        "ticker": "TEST",
        "evaluationSession": "2021-01-04",
        "entrySession": "2021-01-05",
        "targetExitSession": "2021-07-07",
        "F2_DIRECT_VS_INDIRECT": "INDIRECT_ONLY",
    }
    first = mod._scope_digest([row])
    changed = dict(row)
    changed["F2_DIRECT_VS_INDIRECT"] = "DIRECT_ONLY"
    second = mod._scope_digest([changed])
    assert first.startswith("sha256:")
    assert first != second
