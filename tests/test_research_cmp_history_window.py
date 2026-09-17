from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import research_cmp_history_window as window


FIELDS = list(window.REQUIRED_FIELDS)


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _row(*, year: int, month: int, filed: str, owner: str = "0000000001") -> dict[str, str]:
    return {
        "ownerCik": owner,
        "tradeYear": str(year),
        "tradeMonth": str(month),
        "firstFiledDate": filed,
        "distinctAccessions": "1",
        "ownerTransactionRows": "1",
        "purchaseRows": "1",
        "saleRows": "0",
    }


def test_bounded_view_excludes_irrelevant_and_impossible_future_dates(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "bounded"
    _write(
        source / "cmp-owner-month-2013.csv",
        [
            _row(year=2013, month=2, filed="2013-02-14"),
            _row(year=2012, month=12, filed="2013-01-10", owner="0000000002"),
            _row(year=2023, month=8, filed="2013-08-01", owner="0000000003"),
            _row(year=2014, month=11, filed="2013-11-25", owner="0000000004"),
            _row(year=2013, month=12, filed="2013-02-14", owner="0000000005"),
        ],
    )

    summary = window.run(source_root=source, output_root=output)

    with (output / "cmp-owner-month-2013.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [(row["tradeYear"], row["tradeMonth"]) for row in rows] == [("2013", "2")]
    assert summary["totals"] == {
        "IMPOSSIBLE_FUTURE_TRADE_MONTH": 2,
        "KEEP": 1,
        "OUTSIDE_PREDECLARED_CLASSIFIER_HISTORY": 2,
    }
    persisted = json.loads((output / "window-summary.json").read_text(encoding="utf-8"))
    assert persisted["oosOpened"] is False
    assert persisted["productionScoringChanged"] is False


def test_same_filing_month_is_allowed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "bounded"
    _write(source / "cmp-owner-month-2019.csv", [_row(year=2019, month=2, filed="2019-02-05")])

    window.run(source_root=source, output_root=output)

    with (output / "cmp-owner-month-2019.csv").open(encoding="utf-8", newline="") as stream:
        assert len(list(csv.DictReader(stream))) == 1


def test_sealed_filing_date_is_hard_failure(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "bounded"
    _write(source / "cmp-owner-month-2019.csv", [_row(year=2019, month=2, filed="2023-01-05")])

    with pytest.raises(ValueError, match="sealed OOS filing date"):
        window.run(source_root=source, output_root=output)
