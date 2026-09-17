from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "research_phase1_security_continuity_resolution.py"
)
if not MODULE_PATH.exists():
    MODULE_PATH = Path("/mnt/data/research_phase1_security_continuity_resolution.py")
spec = importlib.util.spec_from_file_location("continuity_resolution", MODULE_PATH)
assert spec and spec.loader
resolution_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolution_module)


BASE_FIELDS = [
    "eventNumber",
    "issuerCik",
    "ticker",
    "evaluationSession",
    "entrySession",
    "horizon",
    "targetExitSession",
    "state",
    "successorSymbol",
    "resolutionSource",
    "candidateActionTypes",
    "adjustedActionTypes",
    "candidateActionIds",
    "maxInternalGapSessions",
    "longInternalGapCandidate",
]


def _source_row(**overrides: str) -> dict[str, str]:
    row = {
        "eventNumber": "1",
        "issuerCik": "0000000001",
        "ticker": "TEST",
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "horizon": "63",
        "targetExitSession": "2020-04-03",
        "state": "UNRESOLVED_CONTINUITY",
        "successorSymbol": "",
        "resolutionSource": "long_internal_gap",
        "candidateActionTypes": "",
        "adjustedActionTypes": "",
        "candidateActionIds": "",
        "maxInternalGapSessions": "10",
        "longInternalGapCandidate": "True",
    }
    row.update(overrides)
    return row


def _write_ledger(
    path: Path, rows: list[dict[str, str]], extra_fields: list[str] | None = None
) -> str:
    fields = BASE_FIELDS + list(extra_fields or [])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return resolution_module._sha256_bytes(path.read_bytes())


def _resolution(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "eventNumber": 1,
        "issuerCik": "0000000001",
        "ticker": "TEST",
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "horizon": 63,
        "targetExitSession": "2020-04-03",
        "expectedSourceState": "UNRESOLVED_CONTINUITY",
        "expectedSourceResolutionSource": "long_internal_gap",
        "effectiveDate": "2020-02-03",
        "effectiveDateBasis": "first_regular_bar_after_frozen_gap",
        "resolutionDecision": "SAME_SECURITY_CONTINUITY",
        "resultState": "PRICE_CONTINUOUS_ADJUSTED",
        "successorSymbol": "TEST",
        "shareQuantityFactor": "1.0",
        "frozenGap": {
            "previousObservedSession": "2020-01-17",
            "firstMissingSession": "2020-01-21",
            "lastMissingSession": "2020-01-31",
            "nextObservedSession": "2020-02-03",
            "maxInternalGapSessions": 10,
        },
    }
    row.update(overrides)
    return row


def _contract(ledger_sha: str, resolutions: list[dict[str, object]]) -> dict[str, object]:
    same = sum(r["resolutionDecision"] == "SAME_SECURITY_CONTINUITY" for r in resolutions)
    transformed = len(resolutions) - same
    return {
        "schemaVersion": 1,
        "contractId": "test-continuity-resolution",
        "purpose": "test",
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "performanceRead": False,
        "source": {
            "continuityLedgerRunId": 1,
            "continuityLedgerArtifact": "test-ledger",
            "continuityLedgerArtifactDigest": "sha256:test",
            "continuityLedgerCsvSha256": ledger_sha,
        },
        "frozenScope": {
            "developmentCohortYears": [2016, 2017, 2018, 2019, 2020],
            "outcomeEnd": "2022-12-31",
            "sealedYear": 2023,
            "horizons": [21, 63, 126, 252],
            "primaryHorizon": 126,
            "longGapThresholdXnysSessions": 10,
            "expectedSourceUnresolvedRows": len(resolutions),
            "expectedSameSecurityRows": same,
            "expectedTransformedHolderRows": transformed,
            "unresolvedRowKeySha256": resolution_module._key_digest(resolutions),
            "autoExpansionAllowed": False,
        },
        "resolutions": resolutions,
    }


def _write_contract(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize("effective", ["2020-01-03", "2020-04-04"])
def test_effective_date_semantics_are_strict(tmp_path: Path, effective: str) -> None:
    ledger = tmp_path / "ledger.csv"
    ledger_sha = _write_ledger(ledger, [_source_row()])
    resolution = _resolution(effectiveDate=effective)
    if effective == "2020-04-04":
        resolution["frozenGap"] = {
            **resolution["frozenGap"],
            "nextObservedSession": effective,
        }
    contract = _contract(ledger_sha, [resolution])
    contract_path = tmp_path / "contract.json"
    _write_contract(contract_path, contract)

    with pytest.raises(ValueError, match="entry < effective <= target exit"):
        resolution_module._load_contract(contract_path)


def test_2023_plus_contract_date_hard_fails(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.csv"
    ledger_sha = _write_ledger(ledger, [_source_row()])
    resolution = _resolution(
        targetExitSession="2023-01-03",
        effectiveDate="2023-01-03",
        frozenGap={
            **_resolution()["frozenGap"],
            "nextObservedSession": "2023-01-03",
        },
    )
    contract = _contract(ledger_sha, [resolution])
    contract_path = tmp_path / "contract.json"
    _write_contract(contract_path, contract)

    with pytest.raises(ValueError, match="sealed OOS boundary"):
        resolution_module._load_contract(contract_path)


def test_2023_plus_source_ledger_hard_fails(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.csv"
    ledger_sha = _write_ledger(
        ledger,
        [_source_row(targetExitSession="2023-01-03")],
    )
    with pytest.raises(ValueError, match="sealed OOS boundary"):
        resolution_module._load_source_ledger(ledger, expected_sha256=ledger_sha)


@pytest.mark.parametrize("forbidden_field", ["raw_126", "excess_63", "mae_21", "close"])
def test_performance_and_ohlc_fields_are_rejected_before_row_use(
    tmp_path: Path, forbidden_field: str
) -> None:
    ledger = tmp_path / "ledger.csv"
    row = _source_row()
    row[forbidden_field] = "DO_NOT_READ"
    ledger_sha = _write_ledger(ledger, [row], extra_fields=[forbidden_field])

    with pytest.raises(ValueError, match="forbidden performance/price fields"):
        resolution_module._load_source_ledger(ledger, expected_sha256=ledger_sha)


def test_unresolved_row_cannot_silently_fall_through(tmp_path: Path) -> None:
    rows = [_source_row(), _source_row(eventNumber="2", ticker="MISS")]
    ledger = tmp_path / "ledger.csv"
    ledger_sha = _write_ledger(ledger, rows)
    contract = _contract(ledger_sha, [_resolution()])

    with pytest.raises(ValueError, match="source unresolved count differs from frozen scope"):
        resolution_module._assert_exact_frozen_scope(rows, contract)


def test_frozen_scope_cannot_auto_expand_to_extra_contract_row(tmp_path: Path) -> None:
    rows = [_source_row()]
    ledger = tmp_path / "ledger.csv"
    ledger_sha = _write_ledger(ledger, rows)
    extra = _resolution(
        eventNumber=2,
        issuerCik="0000000002",
        ticker="EXTRA",
    )
    contract = _contract(ledger_sha, [_resolution(), extra])

    with pytest.raises(ValueError, match="source unresolved count differs from frozen scope"):
        resolution_module._assert_exact_frozen_scope(rows, contract)


def test_overlay_resolves_only_frozen_row_and_preserves_source(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.csv"
    ledger_sha = _write_ledger(ledger, [_source_row()])
    original = ledger.read_bytes()
    contract_path = tmp_path / "contract.json"
    _write_contract(contract_path, _contract(ledger_sha, [_resolution()]))

    summary = resolution_module.run(
        ledger_path=ledger,
        contract_path=contract_path,
        output_dir=tmp_path / "out",
    )

    assert ledger.read_bytes() == original
    assert summary["unresolvedEventHorizonRows"] == 0
    assert summary["resolvedByContractRows"] == 1
    assert summary["performanceRead"] is False
    assert summary["performanceFieldsRead"] == []
    assert summary["priceFieldsRead"] == []
    assert summary["sourceLedgerUntouched"] is True
    assert summary["frozenScopeExpanded"] is False


def test_production_frozen_contract_has_exact_54_row_scope() -> None:
    contract_path = (
        Path(__file__).resolve().parents[1]
        / "research"
        / "b1-security-continuity-resolution-v1.json"
    )
    if not contract_path.exists():
        contract_path = Path("/mnt/data/b1-security-continuity-resolution-v1.json")
    payload, _ = resolution_module._load_contract(contract_path)

    assert len(payload["resolutions"]) == 54
    decisions = [row["resolutionDecision"] for row in payload["resolutions"]]
    assert decisions.count("SAME_SECURITY_CONTINUITY") == 33
    assert decisions.count("TRANSFORMED_HOLDER_CONSIDERATION") == 21
    assert payload["frozenScope"]["longGapThresholdXnysSessions"] == 10
    assert payload["researchOnly"] is True
    assert payload["oosOpened"] is False
    assert payload["productionScoringChanged"] is False
    assert payload["performanceRead"] is False
