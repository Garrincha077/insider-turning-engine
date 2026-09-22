from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_monster_winner_path_feasibility")


def _terms(
    *,
    decision: str = "TRANSFORMED_HOLDER_CONSIDERATION",
    kind: str = "STOCK_MERGERS",
    terminal: str = "NEW",
    quantity: float = 1.0,
    cash: float = 0.0,
    basket: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "decision": decision,
        "kind": kind,
        "terminalTicker": terminal,
        "marketQuantity": quantity,
        "legalQuantity": quantity,
        "cash": cash,
        "basket": basket or [],
    }


def test_path_clock_constants_are_frozen() -> None:
    assert mod.PRIMARY_HORIZON == 252
    assert mod.EXPECTED_PATH_SESSIONS == 253
    assert mod.MIN_NEGATIVE_COVERAGE == 0.95
    assert mod.MAX_NEGATIVE_GAP == 5


def test_stock_merger_routes_original_then_successor() -> None:
    terms = _terms()
    assert mod._required_symbols(
        day="2020-06-01",
        ticker="OLD",
        terms=terms,
        effective_date="2020-06-15",
    ) == ("OLD",)
    assert mod._required_symbols(
        day="2020-06-15",
        ticker="OLD",
        terms=terms,
        effective_date="2020-06-15",
    ) == ("NEW",)


def test_cash_merger_needs_no_market_bar_after_effective_date() -> None:
    terms = _terms(terminal="", quantity=0.0, cash=12.5, kind="CASH_MERGER")
    assert mod._required_symbols(
        day="2020-06-14",
        ticker="OLD",
        terms=terms,
        effective_date="2020-06-15",
    ) == ("OLD",)
    assert mod._required_symbols(
        day="2020-06-15",
        ticker="OLD",
        terms=terms,
        effective_date="2020-06-15",
    ) == ()


def test_adjusted_stock_dividend_stays_on_same_market_series() -> None:
    terms = _terms(
        kind="STOCK_DIVIDEND_QUANTITY",
        terminal="OLD",
        quantity=1.2,
    )
    assert mod._required_symbols(
        day="2020-06-20",
        ticker="OLD",
        terms=terms,
        effective_date="",
    ) == ("OLD",)
    assert mod._needs_effective_date(terms, "OLD") is False


def test_multi_component_requires_every_leg_after_effective_date() -> None:
    terms = _terms(
        decision="TRANSFORMED_MULTI_COMPONENT_CONSIDERATION",
        kind="SPAC_UNIT",
        terminal="",
        quantity=0.0,
        basket=[
            {"symbol": "ABC", "quantity": 1.0},
            {"symbol": "ABC WS", "quantity": 1.0},
        ],
    )
    assert mod._required_symbols(
        day="2020-06-15",
        ticker="OLD.U",
        terms=terms,
        effective_date="2020-06-15",
    ) == ("ABC", "ABC WS")


def test_discontinuity_is_unobservable_on_and_after_effective_date() -> None:
    terms = _terms(
        decision="DISCONTINUOUS_NO_COMPLETE_VALUATION",
        kind="BANKRUPTCY_REORG_UNVALUED_WARRANT",
        terminal="",
        quantity=0.0,
    )
    assert mod._required_symbols(
        day="2020-11-18",
        ticker="OLD",
        terms=terms,
        effective_date="2020-11-19",
    ) == ("OLD",)
    assert mod._required_symbols(
        day="2020-11-19",
        ticker="OLD",
        terms=terms,
        effective_date="2020-11-19",
    ) is None


def test_missing_run_is_consecutive_not_total() -> None:
    sessions = [f"2020-01-{day:02d}" for day in range(1, 9)]
    observable = [True, False, False, True, False, False, False, True]
    maximum, first, last = mod._missing_stats(sessions, observable)
    assert maximum == 3
    assert first == "2020-01-02"
    assert last == "2020-01-07"


def test_negative_feasibility_reasons_fail_closed() -> None:
    assert mod._reason_codes(
        mandatory_unvalued=False,
        deterministic_effective_date=True,
        coverage_ratio=0.96,
        max_missing_run=5,
    ) == ["NEGATIVE_LABEL_FEASIBLE"]

    reasons = mod._reason_codes(
        mandatory_unvalued=True,
        deterministic_effective_date=False,
        coverage_ratio=0.90,
        max_missing_run=8,
    )
    assert reasons == [
        "MANDATORY_UNVALUED_CONSIDERATION",
        "EFFECTIVE_DATE_UNDETERMINED",
        "PATH_COVERAGE_BELOW_95_PCT",
        "INTERNAL_GAP_GT_5",
    ]
