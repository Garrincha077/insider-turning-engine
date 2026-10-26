from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

from insider_turning_engine.backtest.baseline_audit import (
    audit_baseline,
    main,
    net_return,
    text_sha256,
)


def _bundle(tmp_path: Path, mutate=None):
    rows = []
    for event in [1, 2]:
        for horizon in [21, 63, 126, 252]:
            rows.append({
                "eventNumber": str(event), "issuerCik": f"{event:010}", "ticker": f"T{event}",
                "evaluationSession": "2018-01-02", "entrySession": "2018-01-03",
                "targetExitSession": "2019-01-04", "effectiveDate": "", "entryOpen": "10",
                "horizon": str(horizon), "valuationStatus": "VALUED",
                "correctedRaw": "0.2", "correctedExcess": "0.1", "spyReturn": "0.1",
                "continuityState": "PRICE_CONTINUOUS_ADJUSTED", "missingReason": "",
            })
    if mutate:
        mutate(rows)
    csv_path = tmp_path / "events.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    source = {
        "researchOnly": True, "oosOpened": False, "productionScoringChanged": False,
        "outcomeMarketBoundary": "2016-2022 only",
        "horizons": {str(h): {"B1ContinuityCorrected": {
            "maturedOutcomeCount": sum(r["horizon"] == str(h) and r["valuationStatus"] == "VALUED"
                                      for r in rows),
            "spyExcessMean": .1, "spyExcessMedian": .1,
        }} for h in [21, 63, 126, 252]},
    }
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(source), encoding="utf-8")
    contract = json.loads(Path("research/predictive-baseline-audit.v1.json").read_text())
    contract.update(sourceCsvSha256=hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                    sourceSummarySha256=hashlib.sha256(summary_path.read_bytes()).hexdigest(),
                    expectedEvents=2)
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    return csv_path, summary_path, contract_path


def test_cost_is_entry_premium_and_exit_haircut():
    assert net_return(.2, 25) == pytest.approx(1.2 * .9975 / 1.0025 - 1)
    assert net_return(-1, 50) == -1
    assert net_return(0, 0) == 0


def test_tracked_text_hash_is_portable_but_does_not_ignore_content():
    assert text_sha256(b"a\r\nb\r\n") == text_sha256(b"a\nb\n")
    assert text_sha256(b"a\nb\n") != text_sha256(b"a\nc\n")


@pytest.mark.parametrize("gross,cost", [(float("nan"), 0), (-1.01, 0), (0, -1),
                                       (0, 10000), (0, float("inf"))])
def test_invalid_costs_or_returns_fail(gross, cost):
    with pytest.raises(ValueError):
        net_return(gross, cost)


def test_replay_and_cost_scenarios_keep_unresolved_research_unknown(tmp_path):
    csv_path, summary, contract = _bundle(tmp_path)
    report = audit_baseline(csv_path, summary, contract_path=contract)
    assert report == audit_baseline(csv_path, summary, contract_path=contract)
    primary = report["horizons"]["126"]
    assert primary["events"] == primary["observed"] == 2
    costs = primary["costScenarios"]
    assert [row["costBpsPerLeg"] for row in costs] == [0, 10, 25, 50]
    assert costs[0]["netExcessVsGrossSpy"]["median"] == pytest.approx(.1)
    assert costs[-1]["netExcessVsGrossSpy"]["median"] < .1
    assert costs[-1]["netExcessVsEquallyCostedSpy"]["median"] == pytest.approx(.1 * .995 / 1.005)
    assert primary["mae"] is None
    assert report["priorGate"] == "BLOCK_HAC_AND_OOS"
    assert report["fullEngineValidated"] is report["oosOpened"] is False


def test_missing_outcome_is_not_zero_or_deleted(tmp_path):
    def missing(rows):
        rows[-2].update(valuationStatus="MISSING_EXACT_TERMINAL_HOLDER_BAR",
                        correctedRaw="", correctedExcess="", missingReason="Missing terminal bar")
    csv_path, summary, contract = _bundle(tmp_path, missing)
    primary = audit_baseline(csv_path, summary, contract_path=contract)["horizons"]["126"]
    assert primary["events"] == 2 and primary["observed"] == 1 and primary["missing"] == 1
    assert primary["coverage"] == .5
    stress = primary["costScenarios"][0]["missingStockZeroRecoveryStress"]
    assert stress["mean"] == pytest.approx(-.5)


@pytest.mark.parametrize("change,match", [
    (lambda rows: rows.append(rows[0].copy()), "Duplicate"),
    (lambda rows: rows[0].update(evaluationSession="2023-01-01"), "sealed"),
    (lambda rows: rows[0].update(targetExitSession="2023-01-01"), "boundary"),
    (lambda rows: rows[0].update(entrySession="2018-01-02"), "execution"),
    (lambda rows: rows[0].update(correctedExcess="0.9"), "inconsistent excess"),
    (lambda rows: rows[0].update(correctedRaw="nan"), "Non-finite"),
    (lambda rows: rows[0].update(issuerCik="999"), "identity"),
    (lambda rows: rows[0].update(valuationStatus="UNKNOWN"), "Unknown"),
    (lambda rows: rows.pop(), "inventory"),
])
def test_bad_rows_fail_even_when_checksums_match(tmp_path, change, match):
    csv_path, summary, contract = _bundle(tmp_path, change)
    with pytest.raises(ValueError, match=match):
        audit_baseline(csv_path, summary, contract_path=contract)


def test_checksum_is_checked_before_parsing_outcomes(tmp_path):
    csv_path, summary, contract = _bundle(tmp_path)
    csv_path.write_text("not a CSV or trusted outcome", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        audit_baseline(csv_path, summary, contract_path=contract)


def test_contract_cannot_open_other_periods(tmp_path):
    csv_path, summary, contract = _bundle(tmp_path)
    value = json.loads(contract.read_text())
    value["formationEnd"] = "2023-12-31"
    contract.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="cannot change"):
        audit_baseline(csv_path, summary, contract_path=contract)


def test_cli_writes_portable_deterministic_json(tmp_path, monkeypatch):
    csv_path, summary, contract = _bundle(tmp_path)
    output = tmp_path / "output" / "audit.json"
    monkeypatch.setattr(sys, "argv", ["audit", "--csv", str(csv_path), "--summary", str(summary),
                                     "--contract", str(contract), "--output", str(output)])
    main()
    first = output.read_bytes()
    main()
    assert first == output.read_bytes()
    assert b"\r\n" not in first
    assert json.loads(first)["fullEngineValidated"] is False
