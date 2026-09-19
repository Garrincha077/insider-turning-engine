from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_signal_build")


def test_signal_builder_requires_frozen_definition(tmp_path: Path) -> None:
    definition = tmp_path / "definition.json"
    definition.write_text(json.dumps({
        "b3DefinitionFrozen": False,
        "developmentPerformanceComputed": False,
    }))
    revisions = tmp_path / "rows.jsonl"
    revisions.write_text("")
    try:
        mod.build(revisions_path=revisions, definition_path=definition, output=tmp_path / "out")
    except ValueError as exc:
        assert "must be frozen" in str(exc)
    else:
        raise AssertionError("unfrozen B3 definition must be rejected")
