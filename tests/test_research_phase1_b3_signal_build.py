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

def _definition() -> dict[str, object]:
    return {
        "b3DefinitionFrozen": True,
        "developmentPerformanceComputed": False,
        "primaryWindowCalendarDays": 30,
        "definitionId": "B3_TEST",
    }


def _row(issuer: str, accession: str, side: str, accepted: str) -> dict[str, object]:
    is_buy = side == "BUY"
    return {
        "issuer": {"cik": issuer},
        "transaction": {
            "shares": "10",
            "pricePerShare": "5",
        },
        "lifecycle": {
            "validFrom": accepted,
            "validTo": None,
        },
        "researchReconciliation": {
            "b3QualifiedSide": side,
            "economicEventAt": accepted,
            "companyEconomicKey": f"{issuer}|{accession}|NON_DERIVATIVE|1",
        },
        "_testBuy": is_buy,
    }


def test_signal_builder_streams_issuer_contiguous_rows(tmp_path: Path) -> None:
    definition = tmp_path / "definition.json"
    definition.write_text(json.dumps(_definition()))
    revisions = tmp_path / "rows.jsonl"
    rows = [
        _row("0000000001", "a", "BUY", "2019-01-02T12:00:00+00:00"),
        _row("0000000001", "b", "SALE", "2019-01-03T12:00:00+00:00"),
        _row("0000000002", "c", "BUY", "2019-02-01T12:00:00+00:00"),
    ]
    revisions.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    summary = mod.build(
        revisions_path=revisions,
        definition_path=definition,
        output=tmp_path / "out",
    )

    assert summary["rawCandidateCount"] >= 2
    assert summary["distinctIssuers"] == 2
    assert summary["returnsRead"] is False
    assert summary["oosOpened"] is False


def test_signal_builder_rejects_noncontiguous_issuer_input(tmp_path: Path) -> None:
    definition = tmp_path / "definition.json"
    definition.write_text(json.dumps(_definition()))
    revisions = tmp_path / "rows.jsonl"
    rows = [
        _row("0000000001", "a", "BUY", "2019-01-02T12:00:00+00:00"),
        _row("0000000002", "b", "BUY", "2019-01-03T12:00:00+00:00"),
        _row("0000000001", "c", "BUY", "2019-01-04T12:00:00+00:00"),
    ]
    revisions.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    try:
        mod.build(
            revisions_path=revisions,
            definition_path=definition,
            output=tmp_path / "out",
        )
    except ValueError as exc:
        assert "not issuer-contiguous" in str(exc)
    else:
        raise AssertionError("noncontiguous issuer input must fail closed")

