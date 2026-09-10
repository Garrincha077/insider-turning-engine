"""Focused contract tests for deterministic live-input preparation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from insider_turning_engine.cli import app
from insider_turning_engine.ingestion.sec.parser import parse_sec_xml
from insider_turning_engine.pipeline.live_inputs import (
    LiveInputPreparationError,
    plan_live_market,
    prepare_live_inputs,
)

FIXTURES = Path(__file__).parent / "fixtures"
RUN_ID = "run_live_inputs_20260831"
AS_OF = datetime(2026, 8, 31, 20, tzinfo=UTC)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _canonical_row() -> dict[str, object]:
    parsed = parse_sec_xml(
        (FIXTURES / "form4_non_derivative.xml").read_bytes(),
        {
            "accession_number": "0001234567-26-000001",
            "source_url": "https://www.sec.gov/Archives/edgar/data/test.xml",
            "accepted_at": datetime(2026, 8, 21, 12, tzinfo=UTC),
            "observed_at": datetime(2026, 8, 21, 12, tzinfo=UTC),
            "run_id": RUN_ID,
        },
    )
    assert not parsed.quarantines
    return parsed.records[0].canonical_dump()


def _inputs(tmp_path: Path) -> dict[str, Path]:
    canonical = tmp_path / "canonical.json"
    sec = tmp_path / "update-sec.json"
    state = tmp_path / "state.json"
    bars = tmp_path / "market.json"
    market_quality = tmp_path / "market-quality.json"
    _write_json(canonical, [_canonical_row()])
    _write_json(sec, {"records": [], "quarantines": [], "failures": []})
    _write_json(state, [{"issuer_cik": "0001999001", "state": "FALLING"}])
    _write_json(bars, [])
    _write_json(
        market_quality,
        {
            "schemaVersion": "1.0.0",
            "asOf": "2026-08-31",
            "failures": {},
            "coveragePass": True,
            "benchmarkFresh": True,
        },
    )
    return {
        "canonical": canonical,
        "sec": sec,
        "state": state,
        "bars": bars,
        "market_quality": market_quality,
    }


def _identity() -> list[dict[str, str]]:
    return [
        {
            "cik": "0001999001",
            "ticker": "ACME",
            "exchange": "NASDAQ",
            "security_type": "Common Stock",
            "country": "US",
            "sic": "1311",
            "knowledge_at": "2026-08-01T00:00:00Z",
        },
        {
            "cik": "0001999001",
            "ticker": "FUTURE",
            "exchange": "NASDAQ",
            "security_type": "Common Stock",
            "knowledge_at": "2026-09-01T00:00:00Z",
        },
    ]


def test_preparation_writes_replayable_relative_manifest_and_derived_evidence(
    tmp_path: Path,
) -> None:
    paths = _inputs(tmp_path)
    plan = plan_live_market(
        canonical_sources=[paths["canonical"]], sec_envelope=paths["sec"],
        identity_rows=_identity(), as_of=AS_OF,
    )
    coverage = tmp_path / "coverage.json"
    _write_json(coverage, {"totals": {"covered_branches": 7, "num_branches": 8}})

    result = prepare_live_inputs(
        canonical_sources=[paths["canonical"]],
        sec_envelope=paths["sec"],
        identity_rows=_identity(),
        prior_state_file=paths["state"],
        market_bars_file=paths["bars"],
        market_quality_file=paths["market_quality"],
        core_coverage_file=coverage,
        as_of=AS_OF,
        run_id=RUN_ID,
        work_root=tmp_path / "work",
    )

    manifest = json.loads(result.manifest_path.read_text("utf-8"))
    evidence = json.loads(result.quality_evidence_path.read_text("utf-8"))
    assert result.active_issuers == ("0001999001",)
    assert result.symbols == ("ACME",)
    assert result.benchmarks == ("SPY", "XLE")
    assert tuple(plan["symbols"]) == result.symbols
    assert tuple(plan["benchmarks"]) == result.benchmarks
    assert all(not Path(item["path"]).is_absolute() for item in manifest["inputs"].values())
    assert evidence["sec"] == {
        "failureCount": 0,
        "quarantineCount": 0,
        "recordCount": 1,
        "status": "PASS",
    }
    assert evidence["coreBranchCoverage"] == {
        "denominator": 8,
        "numerator": 7,
        "rate": 0.875,
        "status": "EVALUATED",
    }
    assert json.loads(result.identities_path.read_text("utf-8"))[0]["ticker"] == "ACME"


def test_official_exchange_identity_uses_independent_filing_security_title(
    tmp_path: Path,
) -> None:
    paths = _inputs(tmp_path)
    _write_json(paths["canonical"], [])
    _write_json(
        paths["sec"],
        {"records": [_canonical_row()], "quarantines": [], "failures": []},
    )
    identity = [
        {
            "cik": "0001999001",
            "ticker": "ACME",
            "name": "ACME Holdings",
            "exchange": "NASDAQ",
            "knowledge_at": "2026-08-01T00:00:00Z",
            "provenance": {"mapping_status": "current"},
        }
    ]

    result = prepare_live_inputs(
        canonical_sources=[paths["canonical"]],
        sec_envelope=paths["sec"],
        identity_rows=identity,
        prior_state_file=paths["state"],
        market_bars_file=paths["bars"],
        market_quality_file=paths["market_quality"],
        as_of=AS_OF,
        run_id=RUN_ID,
        work_root=tmp_path / "work",
    )

    prepared_history = json.loads(result.canonical_path.read_text("utf-8"))
    prepared_batch = json.loads(result.sec_batch_path.read_text("utf-8"))
    selected = json.loads(result.identities_path.read_text("utf-8"))
    assert prepared_history == []
    assert len(prepared_batch["records"]) == 1
    assert result.symbols == ("ACME",)
    assert selected[0]["security_type_source"] == "sec_filing_non_derivative_title"
    assert selected[0]["security_title_evidence"] == "Common Stock"


def test_sec_failure_fails_before_a_prepared_bundle_is_published(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    _write_json(paths["sec"], {"records": [], "quarantines": [], "failures": [{"message": "no"}]})

    with pytest.raises(LiveInputPreparationError, match="quarantine or failure"):
        prepare_live_inputs(
            canonical_sources=[paths["canonical"]],
            sec_envelope=paths["sec"],
            identity_rows=_identity(),
            prior_state_file=paths["state"],
            market_bars_file=paths["bars"],
            market_quality_file=paths["market_quality"],
            as_of=AS_OF,
            run_id=RUN_ID,
            work_root=tmp_path / "work",
        )


def test_cli_market_to_daily_bridge_is_offline_and_fail_closed(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    identities = tmp_path / "identities.json"
    _write_json(identities, _identity())
    runner = CliRunner()
    shared = ["--canonical", str(paths["canonical"]), "--sec-batch", str(paths["sec"]),
              "--identities", str(identities), "--as-of", AS_OF.isoformat()]
    plan_dir = tmp_path / "plan"
    result = runner.invoke(app, ["plan-live-market", *shared, "--output-dir", str(plan_dir)])
    assert result.exit_code == 0, result.output
    assert (plan_dir / "symbols.txt").read_text().strip() == "ACME"
    assert (plan_dir / "benchmarks.txt").read_text().splitlines() == ["SPY", "XLE"]
    market_path = tmp_path / "market.parquet"
    quality = tmp_path / "actual-quality.json"
    result = runner.invoke(app, ["update-market", "--csv-path", str(FIXTURES / "daily_market.csv"),
                                "--as-of", "2026-08-31", "--output", str(market_path),
                                "--quality-output", str(quality)])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["prepare-live-inputs", *shared,
                                "--prior-state", str(paths["state"]),
                                "--market-bars", str(market_path), "--market-quality", str(quality),
                                "--run-id", RUN_ID, "--work-root", str(tmp_path / "prepared")])
    assert result.exit_code == 0, result.output
    manifest = json.loads(result.stdout)["manifest"]
    result = runner.invoke(app, ["daily", "--execute", "--input-manifest", manifest])
    assert result.exit_code == 0, result.output
    output = json.loads(result.stdout)
    assert output["alerts"] == []


@pytest.mark.parametrize("invalid", ["future", "missing_price", "zero_shares"])
def test_market_plan_never_requests_ineligible_activity(tmp_path: Path, invalid: str) -> None:
    paths = _inputs(tmp_path)
    row = _canonical_row()
    if invalid == "future":
        row["timestamps"]["knowledgeAt"] = "2026-09-01T00:00:00Z"
    elif invalid == "missing_price":
        row["transaction"]["pricePerShare"] = None
    else:
        row["transaction"]["shares"] = "0"
    _write_json(paths["canonical"], [row])
    plan = plan_live_market(canonical_sources=[paths["canonical"]], sec_envelope=paths["sec"],
                            identity_rows=_identity(), as_of=AS_OF)
    assert plan["symbols"] == []
    assert not (tmp_path / "work" / RUN_ID).exists()


def test_missing_coverage_is_explicitly_not_evaluated(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    result = prepare_live_inputs(
        canonical_sources=[paths["canonical"]],
        sec_envelope=paths["sec"],
        identity_rows=_identity(),
        prior_state_file=paths["state"],
        market_bars_file=paths["bars"],
        market_quality_file=paths["market_quality"],
        as_of=AS_OF,
        run_id=RUN_ID,
        work_root=tmp_path / "work",
    )
    evidence = json.loads(result.quality_evidence_path.read_text("utf-8"))
    assert evidence["coreBranchCoverage"] == {
        "denominator": None,
        "numerator": None,
        "rate": None,
        "status": "NOT_EVALUATED",
    }


def test_preparation_keeps_both_revisions_of_a_linked_amendment(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    original = parse_sec_xml(
        (FIXTURES / "form4_original.xml").read_bytes(),
        {
            "accession_number": "0001234567-26-000010",
            "source_url": "https://www.sec.gov/Archives/edgar/data/test.xml",
            "accepted_at": datetime(2026, 8, 20, tzinfo=UTC),
            "observed_at": datetime(2026, 8, 20, tzinfo=UTC),
            "run_id": RUN_ID,
        },
    ).records[0]
    amendment = parse_sec_xml(
        (FIXTURES / "form4_amendment.xml").read_bytes(),
        {
            "accession_number": "0001234567-26-000011",
            "source_url": "https://www.sec.gov/Archives/edgar/data/test.xml",
            "accepted_at": datetime(2026, 8, 22, tzinfo=UTC),
            "observed_at": datetime(2026, 8, 22, tzinfo=UTC),
            "amends_accession_number": original.source.accession_number,
            "run_id": RUN_ID,
        },
    ).records[0]
    _write_json(paths["canonical"], [original.canonical_dump(), amendment.canonical_dump()])

    result = prepare_live_inputs(
        canonical_sources=[paths["canonical"]],
        sec_envelope=paths["sec"],
        identity_rows=_identity(),
        prior_state_file=paths["state"],
        market_bars_file=paths["bars"],
        market_quality_file=paths["market_quality"],
        as_of=AS_OF,
        run_id=RUN_ID,
        work_root=tmp_path / "work",
    )

    prepared = json.loads(result.canonical_path.read_text("utf-8"))
    assert len(prepared) == 2
    assert {row["source"]["accessionNumber"] for row in prepared} == {
        "0001234567-26-000010",
        "0001234567-26-000011",
    }
