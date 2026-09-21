from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module(
    "research_phase1_feature_tournament_long_gap7_resolver"
)


def _candidate(
    event: int,
    ticker: str,
    issuer: str,
    horizon: int,
    entry: str,
    target: str,
    gap: int,
    fp: list[str],
) -> dict[str, object]:
    return {
        "currentEventNumber": event,
        "issuerCik": issuer,
        "ticker": ticker,
        "evaluationSession": entry,
        "entrySession": entry,
        "horizon": horizon,
        "targetExitSession": target,
        "currentResolutionSource": "long_internal_gap",
        "maxInternalGapSessions": gap,
        "evidenceAudit": {
            "category": "LONG_GAP_PRIOR_SECURITY_CANDIDATE",
            "economicFingerprint": fp,
        },
    }


def _new_primary(event: int, ticker: str, horizon: int) -> dict[str, object]:
    return {
        "currentEventNumber": event,
        "issuerCik": f"{event:010d}",
        "ticker": ticker,
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "horizon": horizon,
        "targetExitSession": "2021-01-04",
        "currentResolutionSource": "long_internal_gap",
        "maxInternalGapSessions": 10,
        "evidenceAudit": {
            "category": "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED",
        },
    }


def _scope() -> dict[str, object]:
    same_ckx = [
        "SAME_SECURITY_CONTINUITY",
        "",
        "PRICE_CONTINUOUS_ADJUSTED",
        "CKX",
        "1",
        "0",
    ]
    same_cmct = [
        "SAME_SECURITY_CONTINUITY",
        "",
        "PRICE_CONTINUOUS_ADJUSTED",
        "CMCT",
        "1",
        "0",
    ]
    same_nsec = [
        "SAME_SECURITY_CONTINUITY",
        "",
        "PRICE_CONTINUOUS_ADJUSTED",
        "NSEC",
        "1",
        "0",
    ]
    lov = [
        "TRANSFORMED_HOLDER_CONSIDERATION",
        "ADS_EXCHANGE",
        "TRANSFORMED_HOLDER_CONSIDERATION",
        "LOV",
        "0.1",
        "0",
    ]
    rows = [
        _candidate(
            1,
            "CKX",
            "0000352955",
            252,
            "2016-11-10",
            "2017-11-10",
            16,
            same_ckx,
        ),
        _candidate(
            2,
            "LOV",
            "0001314475",
            252,
            "2016-11-30",
            "2017-11-30",
            10,
            lov,
        ),
        _candidate(
            3,
            "CMCT",
            "0000908311",
            252,
            "2019-12-02",
            "2020-12-01",
            19,
            same_cmct,
        ),
        _candidate(
            4,
            "NSEC",
            "0000865058",
            252,
            "2020-01-07",
            "2021-01-06",
            15,
            same_nsec,
        ),
        _candidate(
            5,
            "CKX",
            "0000352955",
            63,
            "2020-10-02",
            "2021-01-04",
            10,
            same_ckx,
        ),
        _candidate(
            5,
            "CKX",
            "0000352955",
            126,
            "2020-10-02",
            "2021-04-06",
            10,
            same_ckx,
        ),
        _candidate(
            5,
            "CKX",
            "0000352955",
            252,
            "2020-10-02",
            "2021-10-04",
            10,
            same_ckx,
        ),
    ]
    for i, ticker in enumerate(
        ["AVGR", "AVGR", "AVGR", "HMG", "HMG", "OAS", "OAS", "OAS", "SNES", "SNES"],
        start=20,
    ):
        rows.append(_new_primary(i, ticker, 63 + (i % 3) * 63))
    return {
        "status": "PHASE1_FEATURE_TOURNAMENT_LONG_GAP17_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "residualRows": 17,
        "priorSecurityCandidateRows": 7,
        "newPrimaryEvidenceRows": 10,
        "resolutionComplete": False,
        "featureDiscoveryOutcomesOpened": False,
        "rows": rows,
    }


def _stage_gaps() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {
            "eventNumber": "1",
            "issuerCik": "0000352955",
            "ticker": "CKX",
            "horizon": "252",
            "entrySession": "2016-11-10",
            "targetExitSession": "2017-11-10",
            "maxInternalGapSessions": "16",
            "previousObservedSession": "2017-06-16",
            "firstMissingSession": "2017-06-19",
            "lastMissingSession": "2017-07-11",
            "nextObservedSession": "2017-07-12",
        },
        {
            "eventNumber": "2",
            "issuerCik": "0001314475",
            "ticker": "LOV",
            "horizon": "252",
            "entrySession": "2016-11-30",
            "targetExitSession": "2017-11-30",
            "maxInternalGapSessions": "10",
            "previousObservedSession": "2017-11-02",
            "firstMissingSession": "2017-11-03",
            "lastMissingSession": "2017-11-16",
            "nextObservedSession": "2017-11-17",
        },
        {
            "eventNumber": "3",
            "issuerCik": "0000908311",
            "ticker": "CMCT",
            "horizon": "252",
            "entrySession": "2019-12-02",
            "targetExitSession": "2020-12-01",
            "maxInternalGapSessions": "19",
            "previousObservedSession": "2020-07-20",
            "firstMissingSession": "2020-07-21",
            "lastMissingSession": "2020-08-14",
            "nextObservedSession": "2020-08-17",
        },
        {
            "eventNumber": "4",
            "issuerCik": "0000865058",
            "ticker": "NSEC",
            "horizon": "252",
            "entrySession": "2020-01-07",
            "targetExitSession": "2021-01-06",
            "maxInternalGapSessions": "15",
            "previousObservedSession": "2020-07-16",
            "firstMissingSession": "2020-07-17",
            "lastMissingSession": "2020-08-06",
            "nextObservedSession": "2020-08-07",
        },
    ]
    for horizon in (63, 126, 252):
        rows.append(
            {
                "eventNumber": "5",
                "issuerCik": "0000352955",
                "ticker": "CKX",
                "horizon": str(horizon),
                "entrySession": "2020-10-02",
                "targetExitSession": "2021-10-04",
                "maxInternalGapSessions": "10",
                "previousObservedSession": "2020-11-03",
                "firstMissingSession": "2020-11-04",
                "lastMissingSession": "2020-11-17",
                "nextObservedSession": "2020-11-18",
            }
        )
    for i in range(148):
        rows.append(
            {
                "eventNumber": str(10000 + i),
                "issuerCik": f"{6000000000 + i:010d}",
                "ticker": f"X{i}",
                "horizon": "252",
                "entrySession": "2020-01-03",
                "targetExitSession": "2021-01-04",
                "maxInternalGapSessions": "10",
                "previousObservedSession": "2020-02-03",
                "firstMissingSession": "2020-02-04",
                "lastMissingSession": "2020-02-17",
                "nextObservedSession": "2020-02-18",
            }
        )
    assert len(rows) == 155
    return rows


def _b3() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for ticker, issuer, date in [
        ("CKX", "0000352955", "2017-06-19"),
        ("CKX", "0000352955", "2020-11-04"),
        ("NSEC", "0000865058", "2020-07-17"),
    ]:
        rows.append(
            {
                "issuerCik": issuer,
                "ticker": ticker,
                "effectiveDate": date,
                "evidenceClass": "SEC_MULTI_SOURCE_EXACT_CONTINUITY",
                "classificationSourceRelease": "research-phase1-b3-residual-multisource-v1",
                "resolutionDecision": "SAME_SECURITY_CONTINUITY",
                "resultState": "PRICE_CONTINUOUS_ADJUSTED",
                "successorSymbol": ticker,
                "successorSharesPerEntryShare": 1.0,
                "cashPerEntryShare": 0.0,
            }
        )
    for i in range(261):
        rows.append(
            {
                "issuerCik": f"{7000000000 + i:010d}",
                "ticker": f"B{i}",
                "effectiveDate": "2020-05-01",
                "evidenceClass": "TEST",
                "classificationSourceRelease": "test",
                "resolutionDecision": "SAME_SECURITY_CONTINUITY",
                "resultState": "PRICE_CONTINUOUS_ADJUSTED",
                "successorSymbol": f"B{i}",
                "successorSharesPerEntryShare": 1.0,
                "cashPerEntryShare": 0.0,
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


def _b1() -> dict[str, object]:
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
    rows: list[list[object]] = [
        [
            5550,
            "0000908311",
            "CMCT",
            "2020-07-10",
            "2020-07-13",
            252,
            "2021-07-13",
            "long_internal_gap",
            "2020-08-17",
            "SAME_SECURITY_CONTINUITY",
            "",
            "PRICE_CONTINUOUS_ADJUSTED",
            "CMCT",
            "1.0",
            [],
            19,
        ]
    ]
    for i in range(53):
        rows.append(
            [
                6000 + i,
                f"{8000000000 + i:010d}",
                f"D{i}",
                "2020-01-02",
                "2020-01-03",
                252,
                "2021-01-04",
                "long_internal_gap",
                "2020-02-18",
                "SAME_SECURITY_CONTINUITY",
                "",
                "PRICE_CONTINUOUS_ADJUSTED",
                f"D{i}",
                "1.0",
                [],
                10,
            ]
        )
    return {
        "contractId": "phase1-b1-security-continuity-resolution-v1",
        "researchOnly": True,
        "performanceRead": False,
        "oosOpened": False,
        "resolutionColumns": columns,
        "resolutions": rows,
    }


def _b1_gaps() -> list[dict[str, object]]:
    return [
        {
            "eventNumber": "5550",
            "issuerCik": "0000908311",
            "ticker": "CMCT",
            "horizon": "252",
            "entrySession": "2020-07-13",
            "targetExitSession": "2021-07-13",
            "maxInternalGapSessions": "19",
            "previousObservedSession": "2020-07-20",
            "firstMissingSession": "2020-07-21",
            "lastMissingSession": "2020-08-14",
            "nextObservedSession": "2020-08-17",
        }
    ]


def _one_sided() -> dict[str, object]:
    return {
        "contractId": "phase1-b3-one-sided-primary-evidence-v1",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "identities": [
            {
                "issuerCik": "0001314475",
                "ticker": "LOV",
                "effectiveDate": "2017-11-02",
                "primaryEvidence": [
                    {"accession": "0001144204-17-057262"},
                    {"accession": "0001144204-17-055907"},
                ],
            }
        ],
    }


def _write_json(tmp_path: Path, name: str, payload: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_csv(tmp_path: Path, name: str, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / name
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_resolves_seven_and_freezes_primary10(tmp_path: Path) -> None:
    resolution, residual = mod.run(
        long_gap_scope_path=_write_json(tmp_path, "scope.json", _scope()),
        stage_gap_path=_write_csv(tmp_path, "stage.csv", _stage_gaps()),
        b3_contract_path=_write_json(tmp_path, "b3.json", _b3()),
        b1_contract_path=_write_json(tmp_path, "b1.json", _b1()),
        b1_gap_path=_write_csv(tmp_path, "b1-gap.csv", _b1_gaps()),
        one_sided_evidence_path=_write_json(
            tmp_path,
            "one-sided.json",
            _one_sided(),
        ),
        resolution_output=tmp_path / "resolved.json",
        residual_output=tmp_path / "primary10.json",
    )
    assert resolution["resolvedRows"] == 7
    assert resolution["resolvedTickerCounts"] == {
        "CKX": 4,
        "CMCT": 1,
        "LOV": 1,
        "NSEC": 1,
    }
    assert residual["residualRows"] == 10
    assert residual["tickerCounts"] == {
        "AVGR": 3,
        "HMG": 2,
        "OAS": 3,
        "SNES": 2,
    }


def test_rejects_ckx_when_gap_pivot_changes(tmp_path: Path) -> None:
    stage = _stage_gaps()
    stage[0]["firstMissingSession"] = "2017-06-20"
    with pytest.raises(ValueError, match="no exact B3 multisource gap-pivot"):
        mod.run(
            long_gap_scope_path=_write_json(tmp_path, "scope.json", _scope()),
            stage_gap_path=_write_csv(tmp_path, "stage.csv", stage),
            b3_contract_path=_write_json(tmp_path, "b3.json", _b3()),
            b1_contract_path=_write_json(tmp_path, "b1.json", _b1()),
            b1_gap_path=_write_csv(tmp_path, "b1-gap.csv", _b1_gaps()),
            one_sided_evidence_path=_write_json(
                tmp_path,
                "one-sided.json",
                _one_sided(),
            ),
            resolution_output=tmp_path / "resolved.json",
            residual_output=tmp_path / "primary10.json",
        )
