"""Contract tests for the static dashboard publication boundary."""

import hashlib
import json
from pathlib import Path

import polars as pl
import pytest

from insider_turning_engine.export.dashboard import (
    DashboardExportError,
    _manifest_digest,
    _validate_manifest,
    export_dashboard,
)

ROOT = Path(__file__).parents[1]


def _candidate() -> dict[str, object]:
    return {
        "ticker": "ABC",
        "issuerCik": "0000000001",
        "company": "ABC Corp",
        "sector": "Technology",
        "total": 91,
        "insider": 90,
        "divergence": 88,
        "turn": 80,
        "cluster": 87,
        "marketRs": 1.2,
        "sectorRs": 0.8,
        "insiderCost": 10.5,
        "currentPrice": 9.9,
        "state": "EARLY_TURN",
        "reasons": ["CLUSTER_BUY", "NO_RELEVANT_SALES"],
        "sourceReferences": {"accession": "0000000001-26-000001"},
    }


def _data() -> dict[str, object]:
    return {
        "schemaVersion": "1.0.0",
        "scoreVersion": "scoring.v1",
        "generatedAt": "2026-08-30T00:00:00Z",
        "status": "VALIDATED",
        "marketPulse": 72,
        "pulsePercentile": 88,
        "pulseHistory": [{"date": "2026-08-30", "market": 72, "technology": 70, "financials": 66}],
        "candidates": [_candidate()],
        "filings": [],
        "backtest": [],
        "companySeries": [],
        "quality": {
            "disposition": "PASS",
            "parseSuccess": {
                "numerator": 100,
                "denominator": 100,
                "rate": 1.0,
                "threshold": 0.995,
                "result": "PASS",
            },
            "marketCoverage": {
                "numerator": 100,
                "denominator": 100,
                "rate": 1.0,
                "threshold": 0.9,
                "result": "PASS",
            },
            "coreBranchCoverage": {
                "numerator": 90,
                "denominator": 100,
                "rate": 0.9,
                "threshold": 0.85,
                "result": "PASS",
            },
            "issues": [],
        },
    }


def test_exports_exact_dashboard_shape_and_manifest_checksums(tmp_path: Path) -> None:
    result = export_dashboard(
        _data(), tmp_path / "data", run_id="run_1234567890123456", chunk_by_ticker=True
    )
    dashboard = json.loads(result.dashboard_path.read_text(encoding="utf-8"))
    assert set(dashboard) == {
        "schemaVersion",
        "scoreVersion",
        "generatedAt",
        "status",
        "marketPulse",
        "pulsePercentile",
        "pulseHistory",
        "candidates",
        "filings",
        "backtest",
        "companySeries",
    }
    assert dashboard["candidates"][0]["reasons"] == ["CLUSTER_BUY", "NO_RELEVANT_SALES"]
    assert dashboard["candidates"][0]["sourceReferences"]["accession"] == "0000000001-26-000001"
    assert (result.output_dir / "tickers" / "ABC.json").is_file()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    for record in manifest["files"]:
        content = (result.output_dir / record["path"]).read_bytes()
        assert len(content) == record["size"]
        assert hashlib.sha256(content).hexdigest() == record["sha256"]


def test_manifest_schema_exposes_exporter_content_address_contract() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "dashboard-manifest.schema.json").read_text(encoding="utf-8")
    )
    assert {"scoreVersion", "files"} <= set(schema["required"])
    assert schema["properties"]["scoreVersion"] == {"const": "scoring.v1"}
    assert schema["properties"]["files"]["items"] == {"$ref": "#/$defs/fileRecord"}
    assert schema["$defs"]["fileRecord"]["required"] == ["path", "size", "sha256"]


def test_checked_in_sample_is_explicitly_degraded_and_content_addressed() -> None:
    root = ROOT / "app" / "public" / "data"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    dashboard = json.loads((root / "dashboard.json").read_text(encoding="utf-8"))

    assert manifest["status"] == "DEGRADED"
    assert manifest["quality"]["disposition"] == "DEGRADED"
    assert "ILLUSTRATIVE_SAMPLE" in manifest["quality"]["issues"]
    assert dashboard["status"] == "EXPERIMENTAL"
    for record in manifest["files"]:
        content = (root / record["path"]).read_bytes()
        assert len(content) == record["size"]
        assert hashlib.sha256(content).hexdigest() == record["sha256"]


def test_missing_quality_evidence_is_blocked_and_not_validated(tmp_path: Path) -> None:
    data = _data()
    data.pop("quality")
    data["status"] = "EXPERIMENTAL"
    result = export_dashboard(data, tmp_path / "blocked", run_id="run_1234567890123456")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "DEGRADED"
    assert manifest["quality"]["disposition"] == "BLOCKED"
    assert manifest["quality"]["parseSuccess"]["result"] == "NOT_EVALUATED"


def test_dataframe_input_and_repeat_are_byte_deterministic(tmp_path: Path) -> None:
    first = _data()
    first["candidates"] = pl.DataFrame([_candidate()])
    first["filings"] = pl.DataFrame([])
    output = tmp_path / "data"
    export_dashboard(first, output, run_id="run_1234567890123456")
    before = {path.name: path.read_bytes() for path in output.iterdir() if path.is_file()}
    export_dashboard(first, output, run_id="run_1234567890123456")
    after = {path.name: path.read_bytes() for path in output.iterdir() if path.is_file()}
    assert before == after


def test_rejects_non_finite_data_and_preserves_previous_snapshot(tmp_path: Path) -> None:
    output = tmp_path / "data"
    export_dashboard(_data(), output, run_id="run_1234567890123456")
    previous = (output / "dashboard.json").read_bytes()
    bad = _data()
    bad["marketPulse"] = float("nan")
    with pytest.raises(DashboardExportError, match="non-finite"):
        export_dashboard(bad, output, run_id="run_1234567890123457")
    assert (output / "dashboard.json").read_bytes() == previous


def test_missing_required_metric_is_rejected_without_creating_output(tmp_path: Path) -> None:
    data = _data()
    del data["marketPulse"]
    with pytest.raises(DashboardExportError, match="marketPulse"):
        export_dashboard(data, tmp_path / "data")
    assert not (tmp_path / "data").exists()


def test_manifest_artifact_must_match_content_addressed_file(tmp_path: Path) -> None:
    result = export_dashboard(_data(), tmp_path / "data", run_id="run_1234567890123456")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["contentHash"] = "sha256:" + "0" * 64
    manifest["manifestId"] = "mft_" + _manifest_digest(manifest)[:32]
    with pytest.raises(DashboardExportError, match="artifact hash"):
        _validate_manifest(manifest)
