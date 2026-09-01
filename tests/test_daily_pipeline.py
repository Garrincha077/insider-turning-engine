from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from insider_turning_engine.ingestion.sec.parser import parse_sec_xml
from insider_turning_engine.pipeline.daily import DailyPipelineError, run_daily_pipeline

FIXTURES = Path(__file__).parent / "fixtures"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(
    tmp_path: Path,
    *,
    future: bool = False,
    sec_batch: bool = False,
    valid_sec_batch: bool = False,
) -> Path:
    transaction = {
        "issuer_cik": "0000123456",
        "owner_cik": "0000654321",
        "transaction_date": "2026-08-20",
        "knowledge_at": "2026-08-20T20:00:00Z" if not future else "2026-09-01T00:00:00Z",
        "accepted_at": "2026-08-20T20:00:00Z",
        "code": "P",
        "table_type": "NON_DERIVATIVE",
        "lifecycle_status": "ACTIVE",
    }
    inputs = {
        "canonicalTransactions": ("canonical.json", [transaction]),
        "marketBars": ("market.json", []),
        "identities": (
            "identities.json",
            [
                {
                    "cik": "0000123456",
                    "ticker": "ACME",
                    "knowledge_at": "2026-01-01T00:00:00Z",
                }
            ],
        ),
        "priorState": ("prior-state.json", []),
        "qualityEvidence": ("quality.json", {}),
    }
    if valid_sec_batch:
        parsed = parse_sec_xml(
            (FIXTURES / "form4_non_derivative.xml").read_bytes(),
            {
                "accession_number": "0001234567-26-000001",
                "source_url": "https://www.sec.gov/Archives/edgar/data/test.xml",
                "accepted_at": datetime(2026, 8, 21, 12, tzinfo=UTC),
                "observed_at": datetime(2026, 8, 21, 12, tzinfo=UTC),
                "run_id": "run_daily_pipeline_20260831",
            },
        )
        inputs["canonicalTransactions"] = ("canonical.json", [])
        inputs["secBatch"] = (
            "sec-batch.json",
            [record.canonical_dump() for record in parsed.records],
        )
    elif sec_batch:
        inputs["secBatch"] = ("sec-batch.json", [transaction])
    manifest_inputs: dict[str, dict[str, str]] = {}
    for name, (filename, value) in inputs.items():
        path = tmp_path / filename
        _write_json(path, value)
        manifest_inputs[name] = {"path": filename, "sha256": _digest(path)}
    manifest = tmp_path / "daily-manifest.json"
    _write_json(
        manifest,
        {
            "schemaVersion": "1.0.0",
            "runId": "run_daily_pipeline_20260831",
            "asOf": "2026-08-31T20:00:00Z",
            "outputRoot": "output",
            "inputs": manifest_inputs,
        },
    )
    return manifest


def test_daily_pipeline_replay_is_byte_identical_and_holds_missing_components(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)

    first = run_daily_pipeline(manifest)
    files = sorted(first.output_root.rglob("*"))
    before = {
        path.relative_to(first.output_root): path.read_bytes() for path in files if path.is_file()
    }
    second = run_daily_pipeline(manifest)
    after = {
        path.relative_to(second.output_root): path.read_bytes()
        for path in sorted(second.output_root.rglob("*"))
        if path.is_file()
    }

    assert first.as_mapping() == second.as_mapping()
    assert before == after
    assert first.signals[0]["total_score"] is None
    assert "STALE_DATA_HOLD" in first.signals[0]["reason_codes"]
    assert first.alerts == ()


def test_daily_pipeline_rejects_future_knowledge_before_writing(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path, future=True)

    with pytest.raises(DailyPipelineError, match="later than as_of"):
        run_daily_pipeline(manifest)
    assert not (tmp_path / "output").exists()


def test_sec_batch_error_never_creates_commit_marker(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path, sec_batch=True)

    with pytest.raises(DailyPipelineError, match="model-valid canonical"):
        run_daily_pipeline(manifest)
    assert not (tmp_path / "output" / "staging" / "sec-batch-committed.sha256").exists()


def test_valid_sec_batch_is_durably_merged_before_commit_marker(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path, valid_sec_batch=True)
    result = run_daily_pipeline(manifest)
    snapshot = result.output_root / "snapshots" / result.run_id

    assert result.effective_transactions == 2
    assert pl.read_parquet(snapshot / "canonical" / "transactions.parquet").height == 2
    assert pl.read_parquet(
        snapshot / "canonical" / "effective-transactions.parquet"
    ).height == 2
    assert (snapshot / "staging" / "sec-batch-committed.sha256").is_file()
    publication = json.loads((result.output_root / "manifest.json").read_text("utf-8"))
    assert publication["runId"] == result.run_id
    assert all(
        item["path"].startswith(f"snapshots/{result.run_id}/")
        for item in publication["artifacts"]
    )
