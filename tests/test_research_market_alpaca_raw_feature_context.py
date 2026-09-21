from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_market_alpaca_raw_feature_context")


def _row(year: int, ticker: str | None) -> dict[str, object]:
    return {
        "timestamps": {"knowledgeAt": f"{year}-06-15T15:00:00+00:00"},
        "issuer": {"ticker": ticker},
    }


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_2016_context_includes_2016_and_2017_symbols(tmp_path: Path) -> None:
    source = tmp_path / "sec.jsonl"
    _write(
        source,
        [
            _row(2016, "AAA"),
            _row(2017, "BBB"),
            _row(2018, "CCC"),
        ],
    )
    symbols, diag = mod._load_context_symbols(source, 2016)
    assert symbols == ["AAA", "BBB"]
    assert diag["sourceKnowledgeYears"] == [2016, 2017]


def test_2019_context_includes_2019_and_2020_symbols(tmp_path: Path) -> None:
    source = tmp_path / "sec.jsonl"
    _write(
        source,
        [
            _row(2018, "OLD"),
            _row(2019, "AAA"),
            _row(2020, "BBB"),
            _row(2021, "NEW"),
        ],
    )
    symbols, diag = mod._load_context_symbols(source, 2019)
    assert symbols == ["AAA", "BBB"]
    assert diag["sourceKnowledgeYears"] == [2019, 2020]


def test_2020_context_does_not_open_2021(tmp_path: Path) -> None:
    source = tmp_path / "sec.jsonl"
    _write(source, [_row(2020, "AAA"), _row(2021, "BBB")])
    symbols, diag = mod._load_context_symbols(source, 2020)
    assert symbols == ["AAA"]
    assert diag["sourceKnowledgeYears"] == [2020]


def test_missing_ticker_is_counted_not_invented(tmp_path: Path) -> None:
    source = tmp_path / "sec.jsonl"
    _write(source, [_row(2016, "AAA"), _row(2016, None)])
    symbols, diag = mod._load_context_symbols(source, 2016)
    assert symbols == ["AAA"]
    assert diag["missingTickerRowsInScope"] == 1


def test_out_of_range_year_fails() -> None:
    with pytest.raises(ValueError, match="2016-2020"):
        mod._load_context_symbols(Path("unused"), 2015)


def test_2023_sec_row_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "sec.jsonl"
    _write(source, [_row(2016, "AAA"), _row(2023, "ZZZ")])
    # 2023 is outside the wanted knowledge year and must still fail closed.
    with pytest.raises(ValueError, match="sealed OOS"):
        mod._load_context_symbols(source, 2016)
