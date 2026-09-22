from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod=importlib.import_module("research_market_alpaca_raw_feature_context_extension")


def _write_source(path: Path) -> None:
    rows=[
        {
            "timestamps":{"knowledgeAt":"2021-05-01T12:00:00Z"},
            "issuer":{"ticker":"AAA"},
        },
        {
            "timestamps":{"knowledgeAt":"2022-06-01T12:00:00Z"},
            "issuer":{"ticker":"BBB"},
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows)+"\n",encoding="utf-8")


def test_extension_years_are_frozen() -> None:
    assert mod.MIN_YEAR==2021
    assert mod.MAX_YEAR==2022
    assert mod.SEALED_YEAR==2023


def test_2021_scope_includes_2021_and_2022_symbols(tmp_path: Path) -> None:
    source=tmp_path/"source.jsonl"
    _write_source(source)
    symbols,diag=mod._load_context_symbols(source,2021)
    assert symbols==["AAA","BBB"]
    assert diag["sourceKnowledgeYears"]==[2021,2022]


def test_2022_scope_is_2022_only(tmp_path: Path) -> None:
    source=tmp_path/"source.jsonl"
    _write_source(source)
    symbols,diag=mod._load_context_symbols(source,2022)
    assert symbols==["BBB"]
    assert diag["sourceKnowledgeYears"]==[2022]


def test_rejects_2023(tmp_path: Path) -> None:
    source=tmp_path/"source.jsonl"
    _write_source(source)
    with pytest.raises(ValueError,match="2021-2022"):
        mod._load_context_symbols(source,2023)
