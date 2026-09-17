from __future__ import annotations

import importlib
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
_b1 = importlib.import_module("research_phase1_b1")
_annual_classifications = _b1._annual_classifications


def _history(*rows: tuple[str, int, int, str]):
    result = {}
    for owner, year, month, filed in rows:
        result.setdefault(owner, {}).setdefault(year, {})[month] = date.fromisoformat(filed)
    return result


def test_missing_one_prior_year_remains_unclassified() -> None:
    owner = "0000000001"
    history = _history(
        (owner, 2013, 1, "2013-01-10"),
        (owner, 2015, 3, "2015-03-10"),
    )
    labels, _ = _annual_classifications(history, start_year=2016, end_year=2016)
    assert labels[owner, 2016] == "UNCLASSIFIED"


def test_three_years_without_common_month_are_opportunistic() -> None:
    owner = "0000000002"
    history = _history(
        (owner, 2013, 1, "2013-01-10"),
        (owner, 2014, 2, "2014-02-10"),
        (owner, 2015, 3, "2015-03-10"),
    )
    labels, _ = _annual_classifications(history, start_year=2016, end_year=2016)
    assert labels[owner, 2016] == "OPPORTUNISTIC"


def test_common_month_in_all_three_prior_years_is_routine() -> None:
    owner = "0000000003"
    history = _history(
        (owner, 2013, 7, "2013-07-10"),
        (owner, 2014, 7, "2014-07-10"),
        (owner, 2015, 7, "2015-07-10"),
    )
    labels, _ = _annual_classifications(history, start_year=2016, end_year=2016)
    assert labels[owner, 2016] == "ROUTINE"


def test_opportunistic_persists_until_routine_pattern_emerges() -> None:
    owner = "0000000004"
    history = _history(
        (owner, 2013, 1, "2013-01-10"),
        (owner, 2014, 2, "2014-02-10"),
        (owner, 2015, 3, "2015-03-10"),
        (owner, 2016, 3, "2016-03-10"),
        (owner, 2017, 3, "2017-03-10"),
    )
    labels, _ = _annual_classifications(history, start_year=2016, end_year=2018)
    assert labels[owner, 2016] == "OPPORTUNISTIC"
    assert labels[owner, 2017] == "OPPORTUNISTIC"
    assert labels[owner, 2018] == "ROUTINE"


def test_once_routine_always_routine_even_if_later_history_is_sparse() -> None:
    owner = "0000000005"
    history = _history(
        (owner, 2013, 4, "2013-04-10"),
        (owner, 2014, 4, "2014-04-10"),
        (owner, 2015, 4, "2015-04-10"),
    )
    labels, _ = _annual_classifications(history, start_year=2016, end_year=2020)
    assert labels[owner, 2016] == "ROUTINE"
    assert labels[owner, 2020] == "ROUTINE"


def test_filing_on_or_after_year_start_cannot_influence_current_year_label() -> None:
    owner = "0000000006"
    history = _history(
        (owner, 2013, 8, "2013-08-10"),
        (owner, 2014, 8, "2014-08-10"),
        # Transaction belongs to 2015 but was not filed until 2016-01-02.
        (owner, 2015, 8, "2016-01-02"),
    )
    labels, _ = _annual_classifications(history, start_year=2016, end_year=2016)
    assert labels[owner, 2016] == "UNCLASSIFIED"


def test_multiple_months_use_set_intersection_not_trade_counts() -> None:
    owner = "0000000007"
    history = _history(
        (owner, 2013, 2, "2013-02-01"),
        (owner, 2013, 9, "2013-09-01"),
        (owner, 2014, 2, "2014-02-01"),
        (owner, 2014, 10, "2014-10-01"),
        (owner, 2015, 2, "2015-02-01"),
        (owner, 2015, 11, "2015-11-01"),
    )
    labels, _ = _annual_classifications(history, start_year=2016, end_year=2016)
    assert labels[owner, 2016] == "ROUTINE"
