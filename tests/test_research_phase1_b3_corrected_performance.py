from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_corrected_performance")


def _event(ticker: str = "ABC") -> dict[str, str]:
    return {"ticker": ticker}


def _row(
    *,
    decision: str,
    kind: str = "",
    successor: str = "",
    quantity: float = 0.0,
    cash: float = 0.0,
) -> dict[str, object]:
    return {
        "resolutionDecision": decision,
        "resultState": decision,
        "transformationKind": kind,
        "successorSymbol": successor,
        "successorSharesPerEntryShare": quantity,
        "cashPerEntryShare": cash,
    }


def test_unaffected_row_uses_original_adjusted_price() -> None:
    out = mod._terms(_event("ABC"), None)
    assert out["decision"] == "NO_CONTINUITY_CORRECTION_REQUIRED"
    assert out["terminalTicker"] == "ABC"
    assert out["marketQuantity"] == 1.0
    assert out["cash"] == 0.0


def test_same_security_uses_one_market_share() -> None:
    row = _row(
        decision="SAME_SECURITY_CONTINUITY",
        successor="ABC",
        quantity=1.0,
    )
    row["resultState"] = "PRICE_CONTINUOUS_ADJUSTED"
    out = mod._terms(_event("ABC"), row)
    assert out["terminalTicker"] == "ABC"
    assert out["marketQuantity"] == 1.0


def test_symbol_change_uses_successor_ticker() -> None:
    row = _row(
        decision="SYMBOL_CHANGED_SAME_SECURITY",
        kind="SAME_SECURITY_SYMBOL_CHANGE",
        successor="XYZ",
        quantity=1.0,
    )
    out = mod._terms(_event("ABC"), row)
    assert out["terminalTicker"] == "XYZ"
    assert out["marketQuantity"] == 1.0


def test_adjusted_stock_dividend_preserves_legal_factor_but_values_one() -> None:
    row = _row(
        decision="TRANSFORMED_HOLDER_CONSIDERATION",
        kind="STOCK_DIVIDEND_QUANTITY",
        successor="ABC",
        quantity=1.05,
    )
    out = mod._terms(_event("ABC"), row)
    assert out["legalQuantity"] == 1.05
    assert out["marketQuantity"] == 1.0
    assert out["terminalTicker"] == "ABC"


def test_adjusted_stock_dividend_different_ticker_fails_closed() -> None:
    row = _row(
        decision="TRANSFORMED_HOLDER_CONSIDERATION",
        kind="STOCK_DIVIDEND_QUANTITY",
        successor="XYZ",
        quantity=1.05,
    )
    with pytest.raises(ValueError, match="exception scope changed"):
        mod._terms(_event("ABC"), row)


def test_stock_and_cash_holder_terms_are_preserved() -> None:
    row = _row(
        decision="TRANSFORMED_HOLDER_CONSIDERATION",
        kind="STOCK_AND_CASH_MERGER",
        successor="XYZ",
        quantity=0.2558,
        cash=12.5,
    )
    out = mod._terms(_event("ABC"), row)
    assert out["terminalTicker"] == "XYZ"
    assert out["marketQuantity"] == pytest.approx(0.2558)
    assert out["cash"] == pytest.approx(12.5)


def test_cash_only_merger_requires_no_terminal_ticker() -> None:
    row = _row(
        decision="TRANSFORMED_HOLDER_CONSIDERATION",
        kind="CASH_MERGER",
        quantity=0.0,
        cash=5.5,
    )
    out = mod._terms(_event("BV"), row)
    assert out["terminalTicker"] == ""
    assert out["marketQuantity"] == 0.0
    assert out["cash"] == 5.5


def test_multi_component_basket_preserves_every_leg() -> None:
    row = _row(
        decision="TRANSFORMED_MULTI_COMPONENT_CONSIDERATION",
        kind="UNIT_COMPONENT_BASKET",
    )
    row["basket"] = [
        {
            "symbol": "MIMO",
            "quantityPerEntryUnit": 1,
            "securityClass": "COMMON_STOCK",
        },
        {
            "symbol": "MIMO WS",
            "quantityPerEntryUnit": 1,
            "securityClass": "PUBLIC_WARRANT",
        },
    ]
    out = mod._terms(_event("NBA.U"), row)
    assert {leg["symbol"] for leg in out["basket"]} == {"MIMO", "MIMO WS"}
    assert all(leg["quantity"] == 1.0 for leg in out["basket"])


def test_discontinuous_row_stays_unvalued() -> None:
    row = _row(
        decision="DISCONTINUOUS_NO_COMPLETE_VALUATION",
        kind="MULTI_LEG_UNIT_SEPARATION_UNVALUED_WARRANT",
    )
    out = mod._terms(_event("FMCIU"), row)
    assert out["terminalTicker"] == ""
    assert out["marketQuantity"] == 0.0
    assert out["basket"] == []
