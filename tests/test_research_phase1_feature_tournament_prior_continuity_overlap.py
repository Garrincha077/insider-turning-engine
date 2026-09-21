from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_prior_continuity_overlap"
)


def test_semantic_key_excludes_cohort_event_number() -> None:
    base = {
        "eventNumber": 10,
        "issuerCik": "0001",
        "ticker": "ABC",
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "horizon": 126,
        "targetExitSession": "2020-07-02",
    }
    other = {**base, "eventNumber": 999}
    assert mod._semantic_key(base) == mod._semantic_key(other)


def test_compatible_requires_same_frozen_classification() -> None:
    row = {
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "successorSymbol": "ABC",
        "resolutionDecision": "SAME_SECURITY_CONTINUITY",
        "transformationKind": "",
        "shareQuantityFactor": "1.0",
    }
    assert mod._compatible([row, dict(row)])
    changed = {**row, "successorSymbol": "XYZ"}
    assert not mod._compatible([row, changed])


def test_key_digest_is_event_number_independent() -> None:
    row = {
        "eventNumber": 1,
        "issuerCik": "0001",
        "ticker": "ABC",
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "horizon": 126,
        "targetExitSession": "2020-07-02",
    }
    changed = {**row, "eventNumber": 999}
    assert mod._key_digest([row]) == mod._key_digest([changed])
