from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_stage_b_prior_evidence_reuse"
)


def _scope_row(
    event: int,
    issuer: str,
    ticker: str,
    evaluation: str,
    entry: str,
    horizon: int,
    target: str,
    source: str,
) -> dict[str, object]:
    return {
        "eventNumber": event,
        "issuerCik": issuer,
        "ticker": ticker,
        "evaluationSession": evaluation,
        "entrySession": entry,
        "horizon": horizon,
        "targetExitSession": target,
        "resolutionSource": source,
        "candidateActionTypes": "",
        "candidateActionIds": "",
        "adjustedActionTypes": "",
        "maxInternalGapSessions": 0,
        "longInternalGapCandidate": source == "long_internal_gap",
    }


def _scope(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "status": "PHASE1_FEATURE_TOURNAMENT_STAGE_B_UNRESOLVED_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "unresolvedRows": len(rows),
        "resolutionComplete": False,
        "featureDiscoveryOutcomesOpened": False,
        "rows": rows,
    }


def _b3_row(scope_row: dict[str, object], decision: str = "SAME_SECURITY_CONTINUITY") -> dict[str, object]:
    result_state = (
        "PRICE_CONTINUOUS_ADJUSTED"
        if decision == "SAME_SECURITY_CONTINUITY"
        else "TRANSFORMED_HOLDER_CONSIDERATION"
    )
    successor = str(scope_row["ticker"])
    factor = 1
    kind = ""
    if decision != "SAME_SECURITY_CONTINUITY":
        factor = 1.1
        kind = "STOCK_DIVIDEND_QUANTITY"
    return {
        **{key: scope_row[key] for key in mod.KEY_FIELDS},
        "eventNumber": 9000 + int(scope_row["eventNumber"]),
        "expectedSourceResolutionSource": scope_row["resolutionSource"],
        "resolutionDecision": decision,
        "resultState": result_state,
        "effectiveDate": "2020-06-01",
        "successorSymbol": successor,
        "successorSharesPerEntryShare": factor,
        "cashPerEntryShare": 0,
        "transformationKind": kind,
        "sourceActionIds": [],
        "classificationSource": "test",
        "classificationSourceRelease": "test",
        "evidenceClass": "TEST",
    }


def _b3_payload(primary: dict[str, object]) -> dict[str, object]:
    rows = [primary]
    for index in range(263):
        rows.append(
            {
                "issuerCik": f"{7000000000 + index:010d}",
                "ticker": f"B3X{index}",
                "evaluationSession": "2019-01-02",
                "entrySession": "2019-01-03",
                "horizon": 21,
                "targetExitSession": "2019-02-04",
                "eventNumber": 10000 + index,
                "expectedSourceResolutionSource": "long_internal_gap",
                "resolutionDecision": "SAME_SECURITY_CONTINUITY",
                "resultState": "PRICE_CONTINUOUS_ADJUSTED",
                "effectiveDate": "2019-01-15",
                "successorSymbol": f"B3X{index}",
                "successorSharesPerEntryShare": 1,
                "cashPerEntryShare": 0,
                "transformationKind": "",
                "sourceActionIds": [],
                "classificationSource": "test",
                "classificationSourceRelease": "test",
                "evidenceClass": "TEST",
            }
        )
    return {
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "classifiedRows": 264,
        "finalResolutionContractCreated": True,
        "correctedPerformanceOpened": False,
        "resolutionRows": rows,
    }


def _b1_resolution(scope_row: dict[str, object], decision: str = "TRANSFORMED_HOLDER_CONSIDERATION") -> list[object]:
    result_state = (
        "PRICE_CONTINUOUS_ADJUSTED"
        if decision == "SAME_SECURITY_CONTINUITY"
        else "TRANSFORMED_HOLDER_CONSIDERATION"
    )
    factor = "1.0" if decision == "SAME_SECURITY_CONTINUITY" else "1.05"
    kind = "" if decision == "SAME_SECURITY_CONTINUITY" else "STOCK_DIVIDEND_QUANTITY"
    return [
        8000 + int(scope_row["eventNumber"]),
        scope_row["issuerCik"],
        scope_row["ticker"],
        scope_row["evaluationSession"],
        scope_row["entrySession"],
        scope_row["horizon"],
        scope_row["targetExitSession"],
        scope_row["resolutionSource"],
        "2020-07-01",
        decision,
        kind,
        result_state,
        scope_row["ticker"],
        factor,
        [],
        0,
    ]


def _b1_payload(primary: list[object]) -> dict[str, object]:
    columns = [
        "eventNumber",
        "issuerCik",
        "ticker",
        "evaluationSession",
        "entrySession",
        "horizon",
        "targetExitSession",
        "expectedSourceResolutionSource",
        "effectiveDate",
        "resolutionDecision",
        "transformationKind",
        "resultState",
        "successorSymbol",
        "shareQuantityFactor",
        "sourceActionIds",
        "maxInternalGapSessions",
    ]
    rows = [primary]
    for index in range(53):
        rows.append(
            [
                7000 + index,
                f"{6000000000 + index:010d}",
                f"B1X{index}",
                "2019-01-02",
                "2019-01-03",
                21,
                "2019-02-04",
                "long_internal_gap",
                "2019-01-15",
                "SAME_SECURITY_CONTINUITY",
                "",
                "PRICE_CONTINUOUS_ADJUSTED",
                f"B1X{index}",
                "1.0",
                [],
                0,
            ]
        )
    return {
        "contractId": "phase1-b1-security-continuity-resolution-v1",
        "researchOnly": True,
        "performanceRead": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "frozenScope": {"expectedSourceUnresolvedRows": 54},
        "resolutionColumns": columns,
        "resolutions": rows,
    }


def _patch_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "EXPECTED_SCOPE_ROWS", 3)
    monkeypatch.setattr(mod, "EXPECTED_B3_EXACT_MATCHES", 1)
    monkeypatch.setattr(mod, "EXPECTED_B1_ONLY_EXACT_MATCHES", 1)
    monkeypatch.setattr(mod, "EXPECTED_REUSED_ROWS", 2)
    monkeypatch.setattr(mod, "EXPECTED_RESIDUAL_ROWS", 1)


def test_exact_reuse_and_residual_freeze(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_counts(monkeypatch)
    rows = [
        _scope_row(1, "0000000001", "AAA", "2020-01-02", "2020-01-03", 126, "2020-07-02", "long_internal_gap"),
        _scope_row(2, "0000000002", "BBB", "2020-02-03", "2020-02-04", 252, "2021-02-03", "provider"),
        _scope_row(3, "0000000003", "CCC", "2020-03-02", "2020-03-03", 63, "2020-06-02", "provider"),
    ]

    scope_path = tmp_path / "scope.json"
    b3_path = tmp_path / "b3.json"
    b1_path = tmp_path / "b1.json"
    scope_path.write_text(json.dumps(_scope(rows)), encoding="utf-8")
    b3_path.write_text(json.dumps(_b3_payload(_b3_row(rows[0]))), encoding="utf-8")
    b1_path.write_text(json.dumps(_b1_payload(_b1_resolution(rows[1]))), encoding="utf-8")

    reuse, residual = mod.run(
        scope_path=scope_path,
        b3_contract_path=b3_path,
        b1_contract_path=b1_path,
        reuse_output=tmp_path / "reuse.json",
        residual_output=tmp_path / "residual.json",
    )

    assert reuse["reusedRows"] == 2
    assert reuse["b3ExactMatches"] == 1
    assert reuse["b1OnlyExactMatches"] == 1
    assert residual["residualRows"] == 1
    assert residual["rows"][0]["ticker"] == "CCC"
    assert reuse["performanceRead"] is False
    assert residual["featureDiscoveryOutcomesOpened"] is False


def test_exact_overlap_requires_semantic_agreement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod, "EXPECTED_SCOPE_ROWS", 1)
    row = _scope_row(
        1,
        "0000000001",
        "AAA",
        "2020-01-02",
        "2020-01-03",
        126,
        "2020-07-02",
        "long_internal_gap",
    )
    scope_path = tmp_path / "scope.json"
    b3_path = tmp_path / "b3.json"
    b1_path = tmp_path / "b1.json"
    scope_path.write_text(json.dumps(_scope([row])), encoding="utf-8")
    b3_path.write_text(json.dumps(_b3_payload(_b3_row(row, "SAME_SECURITY_CONTINUITY"))), encoding="utf-8")
    b1_path.write_text(
        json.dumps(_b1_payload(_b1_resolution(row, "TRANSFORMED_HOLDER_CONSIDERATION"))),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="semantic conflict"):
        mod.run(
            scope_path=scope_path,
            b3_contract_path=b3_path,
            b1_contract_path=b1_path,
            reuse_output=tmp_path / "reuse.json",
            residual_output=tmp_path / "residual.json",
        )


def test_rejects_sealed_oos_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod, "EXPECTED_SCOPE_ROWS", 1)
    row = _scope_row(
        1,
        "0000000001",
        "AAA",
        "2020-01-02",
        "2020-01-03",
        252,
        "2023-01-03",
        "long_internal_gap",
    )
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(json.dumps(_scope([row])), encoding="utf-8")
    with pytest.raises(ValueError, match="sealed OOS"):
        mod._load_scope(scope_path)
