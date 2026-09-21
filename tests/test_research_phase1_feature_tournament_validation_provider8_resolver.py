from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_validation_provider8_resolver"
)


def _row(
    event: int,
    ticker: str,
    *,
    decision: str = "TRANSFORMED_HOLDER_CONSIDERATION",
    kind: str = "STOCK_DIVIDEND_QUANTITY",
    successor: str | None = None,
    quantity: str = "1.1",
    cash: str = "0",
) -> dict[str, object]:
    if successor is None:
        successor = ticker
    action = f"action-{event}"
    return {
        "eventNumber": event,
        "issuerCik": f"{event:010d}",
        "ticker": ticker,
        "evaluationSession": "2021-01-04",
        "entrySession": "2021-01-05",
        "horizon": 126,
        "targetExitSession": "2021-07-07",
        "resolutionSource": "provider",
        "candidateActionIds": [action],
        "evidenceAudit": {
            "category": "PROVIDER_EXACT_ACTION_PRIOR_CANDIDATE",
            "actionIds": [action],
            "economicFingerprint": [
                (
                    "SYMBOL_CHANGED_SAME_SECURITY"
                    if decision == "SYMBOL_CHANGED_SAME_SECURITY"
                    else "TRANSFORMED_HOLDER_CONSIDERATION"
                ),
                successor,
                quantity,
                cash,
                [],
            ],
            "schemaLabels": [[decision, kind]],
            "exampleEffectiveDate": "2021-06-01",
            "priorSources": ["B3"],
            "priorMatchCount": 1,
        },
    }


def _audit() -> dict[str, object]:
    reusable = [
        _row(1, "BOTJ"),
        _row(2, "BOTJ"),
        _row(3, "CLDB", successor="FMNB", quantity="1.75", cash="28"),
        _row(4, "CLDB", successor="FMNB", quantity="1.75", cash="28"),
        _row(5, "CLDB", successor="FMNB", quantity="1.75", cash="28"),
        _row(6, "GNTY"),
        _row(7, "HWBK", quantity="1.04"),
        _row(
            8,
            "WPF",
            decision="SYMBOL_CHANGED_SAME_SECURITY",
            kind="SAME_SECURITY_SYMBOL_CHANGE",
            successor="ALIT",
            quantity="1",
        ),
    ]
    residual = []
    for event in range(9, 42):
        residual.append(
            {
                "eventNumber": event,
                "issuerCik": f"{event:010d}",
                "ticker": f"R{event}",
                "evaluationSession": "2021-01-04",
                "entrySession": "2021-01-05",
                "horizon": 126,
                "targetExitSession": "2021-07-07",
                "resolutionSource": "long_internal_gap",
                "candidateActionIds": [],
                "evidenceAudit": {
                    "category": "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED"
                },
            }
        )
    return {
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "PRIOR_EVIDENCE_AUDIT_COMPLETE"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": 41,
        "auditedRows": 41,
        "auditOnly": True,
        "resolutionApplied": False,
        "validationPerformanceOpened": False,
        "rows": reusable + residual,
    }


def test_provider8_resolver_freezes_exact_eight_rows(tmp_path: Path) -> None:
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps(_audit()), encoding="utf-8")

    resolution, residual = mod.run(
        audit_path=audit,
        resolution_output=tmp_path / "provider.json",
        residual_output=tmp_path / "residual.json",
    )

    assert resolution["resolvedProviderRows"] == 8
    assert resolution["remainingResidualRows"] == 33
    assert resolution["tickerCounts"] == {
        "BOTJ": 2,
        "CLDB": 3,
        "GNTY": 1,
        "HWBK": 1,
        "WPF": 1,
    }
    assert residual["residualRows"] == 33
    assert resolution["validationPerformanceOpened"] is False


def test_provider8_rejects_action_identity_drift() -> None:
    row = _row(1, "BOTJ")
    evidence = row["evidenceAudit"]
    assert isinstance(evidence, dict)
    evidence["actionIds"] = ["other"]
    with pytest.raises(ValueError, match="action identity changed"):
        mod._resolution(row)


def test_provider8_rejects_effective_date_outside_horizon() -> None:
    row = _row(1, "BOTJ")
    evidence = row["evidenceAudit"]
    assert isinstance(evidence, dict)
    evidence["exampleEffectiveDate"] = "2022-01-01"
    with pytest.raises(ValueError, match="outside current horizon"):
        mod._resolution(row)
