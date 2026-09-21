from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_provider17_resolver"
)


def _provider_row(
    index: int,
    *,
    category: str,
    kind: str,
) -> dict[str, object]:
    ticker = f"P{index:02d}"
    action_id = f"action-{index}"
    successor = ticker if kind == "STOCK_DIVIDEND_QUANTITY" else "FNF"
    shares = "1.05" if kind == "STOCK_DIVIDEND_QUANTITY" else "0.2558"
    cash = "0" if kind == "STOCK_DIVIDEND_QUANTITY" else "12.5"
    return {
        "currentEventNumber": 1000 + index,
        "currentResolutionSource": "provider",
        "issuerCik": f"{index:010d}",
        "ticker": ticker,
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "horizon": 252,
        "targetExitSession": "2021-01-04",
        "candidateActionIds": [action_id],
        "candidateActionTypes": ["stock_dividends"],
        "evidenceAudit": {
            "actionIds": [action_id],
            "category": category,
            "economicFingerprint": [
                "TRANSFORMED_HOLDER_CONSIDERATION",
                kind,
                "TRANSFORMED_HOLDER_CONSIDERATION",
                successor,
                shares,
                cash,
            ],
            "effectiveDate": "2020-06-01",
            "evidenceClass": "TEST",
            "priorMatchCount": 1,
            "sourceRelease": "test-release",
        },
    }


def _long_gap_row(index: int, *, candidate: bool) -> dict[str, object]:
    category = (
        "LONG_GAP_PRIOR_SECURITY_CANDIDATE"
        if candidate
        else "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED"
    )
    return {
        "currentEventNumber": 3000 + index,
        "currentResolutionSource": "long_internal_gap",
        "issuerCik": f"{5000 + index:010d}",
        "ticker": f"L{index:02d}",
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "horizon": 126,
        "targetExitSession": "2020-07-03",
        "candidateActionIds": [],
        "candidateActionTypes": [],
        "evidenceAudit": {"category": category},
    }


def _audit() -> dict[str, object]:
    provider: list[dict[str, object]] = []
    for index in range(12):
        provider.append(
            _provider_row(
                index,
                category="PROVIDER_ACTION_REUSE_B3",
                kind="STOCK_DIVIDEND_QUANTITY",
            )
        )
    for index in range(12, 16):
        provider.append(
            _provider_row(
                index,
                category="PROVIDER_ACTION_REUSE_B3",
                kind="STOCK_AND_CASH_MERGER",
            )
        )
    provider.append(
        _provider_row(
            16,
            category="PROVIDER_ACTION_REUSE_B1_STOCK_DIVIDEND",
            kind="STOCK_DIVIDEND_QUANTITY",
        )
    )
    long_gap = [
        _long_gap_row(index, candidate=index < 7)
        for index in range(17)
    ]
    return {
        "status": "PHASE1_FEATURE_TOURNAMENT_RESIDUAL_EVIDENCE_AUDIT_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": 34,
        "auditedRows": 34,
        "providerRows": 17,
        "providerActionReusableRows": 17,
        "longGapRows": 17,
        "newPrimaryEvidenceRows": 10,
        "auditOnly": True,
        "resolutionApplied": False,
        "featureDiscoveryOutcomesOpened": False,
        "rows": provider + long_gap,
    }


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_resolves_provider17_and_freezes_long_gap17(
    tmp_path: Path,
) -> None:
    resolution, residual = mod.run(
        audit_path=_write(tmp_path, _audit()),
        resolution_output=tmp_path / "provider.json",
        residual_output=tmp_path / "long-gap.json",
    )

    assert resolution["resolvedProviderRows"] == 17
    assert resolution["remainingLongGapRows"] == 17
    assert resolution["transformationCounts"] == {
        "STOCK_AND_CASH_MERGER": 4,
        "STOCK_DIVIDEND_QUANTITY": 13,
    }
    assert residual["priorSecurityCandidateRows"] == 7
    assert residual["newPrimaryEvidenceRows"] == 10
    assert resolution["performanceRead"] is False
    assert residual["featureDiscoveryOutcomesOpened"] is False


def test_rejects_provider_action_identity_mismatch(
    tmp_path: Path,
) -> None:
    audit = _audit()
    rows = audit["rows"]
    assert isinstance(rows, list)
    first = rows[0]
    assert isinstance(first, dict)
    evidence = first["evidenceAudit"]
    assert isinstance(evidence, dict)
    evidence["actionIds"] = ["different-action"]

    with pytest.raises(ValueError, match="action identity mismatch"):
        mod.run(
            audit_path=_write(tmp_path, audit),
            resolution_output=tmp_path / "provider.json",
            residual_output=tmp_path / "long-gap.json",
        )
