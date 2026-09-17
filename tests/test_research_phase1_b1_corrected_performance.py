from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
_corrected = importlib.import_module("research_phase1_b1_corrected_performance")


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "eventNumber": "1",
        "issuerCik": "0000000001",
        "ticker": "ABC",
        "evaluationSession": "2020-01-02",
        "entrySession": "2020-01-03",
        "horizon": "126",
        "targetExitSession": "2020-07-06",
        "state": "PRICE_CONTINUOUS_ADJUSTED",
        "successorSymbol": "",
        "candidateActionIds": "",
        "resolutionSource": "provider",
        "resolutionEffectiveDate": "",
        "shareQuantityFactor": "",
        "frozenResolutionApplied": "False",
    }
    row.update(overrides)
    return row


def test_price_continuity_keeps_one_share_of_original_security() -> None:
    terms = _corrected._valuation_terms(_row(), actions={}, fixtures={})
    assert terms == {
        "kind": "PRICE_CONTINUOUS_ADJUSTED",
        "effectiveDate": "",
        "terminalTicker": "ABC",
        "shareQuantity": 1.0,
        "cashPerEntryShare": 0.0,
    }


def test_frozen_overlay_stock_transformation_uses_frozen_terms() -> None:
    row = _row(
        state="TRANSFORMED_HOLDER_CONSIDERATION",
        successorSymbol="XYZ",
        resolutionEffectiveDate="2020-03-02",
        shareQuantityFactor="1.17",
        frozenResolutionApplied="True",
    )
    terms = _corrected._valuation_terms(row, actions={}, fixtures={})
    assert terms["kind"] == "FROZEN_RESOLUTION_STOCK_TRANSFORMATION"
    assert terms["effectiveDate"] == "2020-03-02"
    assert terms["terminalTicker"] == "XYZ"
    assert terms["shareQuantity"] == pytest.approx(1.17)
    assert terms["cashPerEntryShare"] == 0.0


def test_frozen_overlay_effective_date_must_be_inside_horizon() -> None:
    row = _row(
        state="TRANSFORMED_HOLDER_CONSIDERATION",
        successorSymbol="XYZ",
        resolutionEffectiveDate="2020-01-03",
        shareQuantityFactor="1.17",
        frozenResolutionApplied="True",
    )
    with pytest.raises(ValueError, match="effective date falls outside event horizon"):
        _corrected._valuation_terms(row, actions={}, fixtures={})


def test_discontinuous_security_requires_verified_fixture_and_stays_missing() -> None:
    row = _row(state="DISCONTINUOUS_NO_COMPLETE_VALUATION", successorSymbol="ABC")
    fixture = {
        "issuerCik": "0000000001",
        "ticker": "ABC",
        "entrySession": "2020-01-03",
        "effectiveDate": "2020-03-02",
        "correctionState": "DISCONTINUOUS_NO_COMPLETE_VALUATION",
    }
    fixtures = {("0000000001", "ABC", "2020-01-03"): fixture}
    terms = _corrected._valuation_terms(row, actions={}, fixtures=fixtures)
    assert terms["kind"] == "DISCONTINUOUS_NO_COMPLETE_VALUATION"
    assert terms["terminalTicker"] == ""
    assert terms["shareQuantity"] == 0.0
    assert terms["cashPerEntryShare"] == 0.0


def test_symbol_change_fixture_cannot_chain_reused_old_ticker() -> None:
    row = _row(state="SYMBOL_CHANGED_SAME_SECURITY", successorSymbol="AAIC")
    fixture = {
        "issuerCik": "0000000001",
        "ticker": "ABC",
        "entrySession": "2020-01-03",
        "effectiveDate": "2020-03-02",
        "correctionState": "SYMBOL_CHANGED_SAME_SECURITY",
        "successorSymbol": "AAIC",
    }
    fixtures = {("0000000001", "ABC", "2020-01-03"): fixture}
    terms = _corrected._valuation_terms(row, actions={}, fixtures=fixtures)
    assert terms["terminalTicker"] == "AAIC"
    assert terms["shareQuantity"] == 1.0


def test_provider_cash_merger_carries_cash_without_reinvestment() -> None:
    row = _row(
        state="TRANSFORMED_HOLDER_CONSIDERATION",
        candidateActionIds="cash-1",
    )
    actions = {
        "cash-1": {
            "id": "cash-1",
            "bucket": "cash_mergers",
            "actionDate": "2020-03-02",
            "rate": "12.50",
        }
    }
    terms = _corrected._valuation_terms(row, actions=actions, fixtures={})
    assert terms["kind"] == "CASH_MERGER"
    assert terms["terminalTicker"] == ""
    assert terms["shareQuantity"] == 0.0
    assert terms["cashPerEntryShare"] == pytest.approx(12.5)


def test_provider_stock_and_cash_merger_normalizes_acquiree_rate() -> None:
    row = _row(
        state="TRANSFORMED_HOLDER_CONSIDERATION",
        successorSymbol="XYZ",
        candidateActionIds="mixed-1",
    )
    actions = {
        "mixed-1": {
            "id": "mixed-1",
            "bucket": "stock_and_cash_mergers",
            "actionDate": "2020-03-02",
            "acquiree_rate": "2",
            "acquirer_rate": "3",
            "cash_rate": "5",
            "acquirer_symbol": "XYZ",
        }
    }
    terms = _corrected._valuation_terms(row, actions=actions, fixtures={})
    assert terms["shareQuantity"] == pytest.approx(1.5)
    assert terms["cashPerEntryShare"] == pytest.approx(2.5)
    assert terms["terminalTicker"] == "XYZ"


def test_2023_event_metadata_hard_fails_before_performance_use(tmp_path: Path) -> None:
    path = tmp_path / "events.csv"
    fields = [
        "issuerCik",
        "ticker",
        "evaluationSession",
        "entrySession",
        "entryOpen",
        *[f"exit_{h}" for h in _corrected.HORIZONS],
        *[f"raw_{h}" for h in _corrected.HORIZONS],
        *[f"excess_{h}" for h in _corrected.HORIZONS],
    ]
    row = {field: "" for field in fields}
    row.update(
        issuerCik="0000000001",
        ticker="ABC",
        evaluationSession="2020-01-02",
        entrySession="2020-01-03",
        entryOpen="10",
        exit_21="2023-01-03",
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)
    with pytest.raises(ValueError, match="sealed OOS boundary"):
        _corrected._load_events(path)


def test_continuity_gate_must_be_zero_unresolved(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    payload = {
        "status": "PHASE1_SECURITY_CONTINUITY_RESOLUTION_COMPLETE",
        "unresolvedEventHorizonRows": 1,
        "performanceStageBlocked": False,
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceLedgerUntouched": True,
        "frozenScopeExpanded": False,
        "sealedYear": 2023,
        "outcomeEnd": "2022-12-31",
        "primaryHorizon": 126,
        "horizons": [21, 63, 126, 252],
        "developmentCohortYears": [2016, 2017, 2018, 2019, 2020],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="continuity gate mismatch"):
        _corrected._load_continuity_summary(path)


def test_b4_coverage_reports_outside_frozen_b1_scope_without_expansion(tmp_path: Path) -> None:
    path = tmp_path / "b4.csv"
    fields = ["issuerCik", "ticker", "evaluationSession", "entrySession"]
    rows = [
        {
            "issuerCik": "1",
            "ticker": "AAA",
            "evaluationSession": "2020-01-02",
            "entrySession": "2020-01-03",
        },
        {
            "issuerCik": "2",
            "ticker": "BBB",
            "evaluationSession": "2020-01-02",
            "entrySession": "2020-01-03",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    keys = {("1", "AAA", "2020-01-02", "2020-01-03")}
    coverage = _corrected._b4_coverage(path, keys)
    assert coverage["b4ExactEntryEvents"] == 2
    assert coverage["coveredByFrozenB1ContinuityLedger"] == 1
    assert coverage["outsideFrozenB1ContinuityLedger"] == 1
    assert coverage["correctedB4Claimed"] is False
