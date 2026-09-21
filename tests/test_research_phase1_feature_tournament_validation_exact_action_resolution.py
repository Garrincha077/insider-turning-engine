from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_exact_action_resolution"
)


def _row() -> dict[str, object]:
    return {
        "eventNumber": 126,
        "issuerCik": "0001275101",
        "ticker": "BOTJ",
        "evaluationSession": "2021-01-25",
        "entrySession": "2021-01-26",
        "horizon": 126,
        "targetExitSession": "2021-07-27",
        "resolutionSource": "provider",
        "candidateActionIds": ["260e3e34-93cc-45cc-811e-33399f65ce7b"],
        "evidenceAudit": {
            "category": "PROVIDER_EXACT_ACTION_PRIOR_CANDIDATE",
            "economicFingerprint": [
                "TRANSFORMED_HOLDER_CONSIDERATION",
                "BOTJ",
                "1.1",
                "0",
                [],
            ],
            "exampleEffectiveDate": "2021-06-24",
            "priorMatchCount": 7,
            "priorSources": ["B1", "B3", "STAGE_B"],
            "schemaLabels": [
                [
                    "TRANSFORMED_HOLDER_CONSIDERATION",
                    "STOCK_DIVIDEND_QUANTITY",
                ]
            ],
        },
    }


def test_resolution_normalizes_frozen_stock_dividend() -> None:
    result = mod._resolution(_row())
    assert result["resultState"] == "TRANSFORMED_HOLDER_CONSIDERATION"
    assert result["successorSymbol"] == "BOTJ"
    assert result["successorSharesPerEntryShare"] == "1.1"
    assert result["cashPerEntryShare"] == "0"
    assert result["sourceActionIds"] == [
        "260e3e34-93cc-45cc-811e-33399f65ce7b"
    ]
    assert result["classificationSource"] == (
        "VALIDATION_EXACT_ACTION_PRIOR_EVIDENCE_REUSE"
    )


def test_symbol_change_requires_quantity_one() -> None:
    row = _row()
    row["ticker"] = "WPF"
    evidence = row["evidenceAudit"]
    assert isinstance(evidence, dict)
    evidence["economicFingerprint"] = [
        "SYMBOL_CHANGED_SAME_SECURITY",
        "ALIT",
        "2",
        "0",
        [],
    ]
    evidence["schemaLabels"] = [
        ["SYMBOL_CHANGED_SAME_SECURITY", "SAME_SECURITY_SYMBOL_CHANGE"]
    ]
    with pytest.raises(ValueError, match="same-security"):
        mod._resolution(row)


def test_effective_date_must_be_inside_horizon() -> None:
    row = _row()
    evidence = row["evidenceAudit"]
    assert isinstance(evidence, dict)
    evidence["exampleEffectiveDate"] = "2021-08-01"
    with pytest.raises(ValueError, match="outside validation horizon"):
        mod._resolution(row)


def test_schema_labels_must_be_singular() -> None:
    row = _row()
    evidence = row["evidenceAudit"]
    assert isinstance(evidence, dict)
    evidence["schemaLabels"] = [
        ["TRANSFORMED_HOLDER_CONSIDERATION", "STOCK_DIVIDEND_QUANTITY"],
        ["TRANSFORMED_HOLDER_CONSIDERATION", "OTHER"],
    ]
    with pytest.raises(ValueError, match="singular schema labels"):
        mod._resolution(row)


def test_exact_scope_digest_is_order_invariant() -> None:
    a = _row()
    b = dict(a)
    b["eventNumber"] = 1122
    b["evaluationSession"] = "2021-04-27"
    b["entrySession"] = "2021-04-28"
    b["targetExitSession"] = "2021-10-26"
    assert mod._key_digest([a, b]) == mod._key_digest([b, a])


def test_source_contract_rejects_changed_partition() -> None:
    payload = {
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "PRIOR_EVIDENCE_AUDIT_COMPLETE"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": 41,
        "auditedRows": 41,
        "resolutionApplied": False,
        "categoryCounts": {
            "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED": 9,
            "LONG_GAP_PRIOR_SECURITY_CANDIDATE": 2,
            "PROVIDER_EXACT_ACTION_PRIOR_CANDIDATE": 8,
            "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED": 22,
        },
        "rows": [],
    }
    with pytest.raises(ValueError, match="partition changed"):
        mod._assert_source(payload)
