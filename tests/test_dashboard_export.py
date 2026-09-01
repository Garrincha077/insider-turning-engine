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
    dashboard_experimental_publication_policy,
    dashboard_publication_policy,
    export_dashboard,
    validate_dashboard_directory,
)
from insider_turning_engine.scoring import ScoreEngine

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
        "generatedAt": "2026-08-31T00:00:00Z",
        "status": "EXPERIMENTAL",
        "marketPulse": 72,
        "pulsePercentile": 88,
        "pulseHistory": [{"date": "2026-08-31", "market": 72, "technology": 70, "financials": 66}],
        "candidates": [_candidate()],
        "filings": [],
        "backtest": [],
        "companySeries": [],
        "quality": {
            "disposition": "DEGRADED",
            "canonicalValid": True,
            "methodologyComplete": False,
            "benchmarkFresh": True,
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
            "issues": ["SCORING_METHODOLOGY_INCOMPLETE"],
        },
    }


def _signal_snapshot(scoring: ScoreEngine) -> dict[str, object]:
    return {
        "schemaVersion": "1.0.0",
        "snapshotId": "sig_1234567890123456",
        "issuer": {
            "cik": "0000000001",
            "name": "ABC Corp",
            "ticker": "ABC",
            "sector": "Technology",
        },
        "asOf": "2026-08-31T00:00:00Z",
        "generatedAt": "2026-08-31T00:00:00Z",
        "versions": {"scoring": "scoring.v1", "stateModel": "state.v1"},
        "scores": {
            "marketPulse": {
                "score": 70,
                "components": {
                    "transaction": 70,
                    "uniqueInsiders": 70,
                    "dollar": 70,
                    "volume": 70,
                    "companyBreadth": 70,
                    "convictionWeighted": 70,
                },
            },
            "companyInsider": {
                "score": 75,
                "components": {
                    "conviction": 75,
                    "cluster": 75,
                    "opportunistic": 75,
                    "netBuyingAbsenceSales": 75,
                },
            },
            "divergence": {
                "score": 80,
                "components": {
                    "priceWeakness": 80,
                    "insiderActivityPercentile": 80,
                    "accelerationCluster": 80,
                    "absenceRelevantSales": 80,
                },
            },
            "turn": {
                "score": 85,
                "components": {
                    "baseStructure": 85,
                    "ordinaryRsTurn": 85,
                    "mansfieldMarket": 85,
                    "mansfieldSector": 85,
                    "volumeAccumulation": 85,
                    "costBasisReclaim": 85,
                },
            },
            "total": {
                "score": 91,
                "components": {
                    "divergence": 91,
                    "conviction": 91,
                    "cluster": 91,
                    "opportunistic": 91,
                    "base": 91,
                    "ordinaryRs": 91,
                    "mansfieldRs": 91,
                    "volume": 91,
                    "fundamental": None,
                },
                "excludedFactors": ["fundamental"],
            },
        },
        "state": {
            "current": "EARLY_TURN",
            "previous": "BASE_FORMING",
            "changed": True,
            "enteredAt": "2026-08-31T00:00:00Z",
            "evaluationSequence": 1,
            "criteria": {
                "return3m": -0.1,
                "closeBelowMa50": False,
                "drawdownFrom52WeekHigh": -0.25,
                "insiderScore": 75,
                "qualifiedBuyAgeDays": 5,
                "priorAccumulation": True,
                "noNew52WeekLow20Sessions": True,
                "volatilityContraction": True,
                "volumeDryUp": True,
                "ma20Flattening": True,
                "ordinaryRsImprovingFourWeeks": True,
                "mansfieldMarketFourWeekSlope": 0.1,
                "closeAboveMa50DaysLast10": 6,
                "mansfieldMarket": 0.2,
                "costBasisReclaim": True,
                "consecutiveFailures": 0,
                "new52WeekLow": False,
            },
        },
        "alerts": [],
        "qualityFlags": ["LOW_CONFIDENCE"],
        "provenance": {
            "runId": "run_1234567890123456",
            "transactionRevisionIds": [],
            "secAcceptedThrough": None,
            "marketSessionThrough": "2026-08-31",
            "fundamentalsAvailableThrough": None,
            "inputHash": "sha256:" + "1" * 64,
            "scoreConfigHash": scoring.score_config_hash,
            "scoreLineage": scoring.score_lineage,
            "methodologyHash": scoring.methodology_hash,
            "methodologyStatus": scoring.methodology_status,
            "scoreFrozenAt": scoring.score_frozen_at_iso,
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
    assert {"canonicalValid", "methodologyComplete", "benchmarkFresh"} <= set(
        schema["$defs"]["quality"]["required"]
    )
    signal_schema = json.loads(
        (ROOT / "schemas" / "signal-snapshot.schema.json").read_text(encoding="utf-8")
    )
    assert {
        "scoreConfigHash",
        "scoreLineage",
        "methodologyHash",
        "methodologyStatus",
        "scoreFrozenAt",
    } <= set(
        signal_schema["$defs"]["provenance"]["required"]
    )


def test_checked_in_live_snapshot_is_explicitly_degraded_and_content_addressed() -> None:
    root = ROOT / "app" / "public" / "data"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    dashboard = json.loads((root / "dashboard.json").read_text(encoding="utf-8"))

    assert manifest["status"] == "DEGRADED"
    assert manifest["quality"]["disposition"] == "DEGRADED"
    assert "LIVE_EXPERIMENTAL_ROLLING_WINDOW" in manifest["quality"]["issues"]
    assert manifest["universe"]["issuerCount"] > 0
    assert manifest["universe"]["activeTransactionCount"] > 0
    assert dashboard["status"] == "EXPERIMENTAL"
    assert len(dashboard["candidates"]) > 0
    assert len(dashboard["filings"]) > 0
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
    assert manifest["quality"]["canonicalValid"] is False
    assert manifest["quality"]["methodologyComplete"] is False
    assert manifest["quality"]["benchmarkFresh"] is False
    assert dashboard_publication_policy(manifest) == (False, False)


def test_pages_policy_allows_healthy_experimental_but_keeps_alerts_off(
    tmp_path: Path,
) -> None:
    data = _data()
    data["status"] = "EXPERIMENTAL"
    quality = data["quality"]
    assert isinstance(quality, dict)
    quality["disposition"] = "DEGRADED"
    quality["issues"] = ["OOS_INCONCLUSIVE"]
    result = export_dashboard(data, tmp_path / "data", run_id="run_1234567890123456")
    manifest = validate_dashboard_directory(result.output_dir)

    assert dashboard_publication_policy(manifest) == (False, False)


def test_live_experimental_policy_requires_real_rows_and_never_allows_alerts(
    tmp_path: Path,
) -> None:
    data = _data()
    quality = data["quality"]
    assert isinstance(quality, dict)
    quality["issues"] = [
        "LIVE_EXPERIMENTAL_ROLLING_WINDOW",
        "SCORING_METHODOLOGY_INCOMPLETE",
    ]
    data["filings"] = [
        {
            "ticker": "ABC",
            "owner": "Owner",
            "role": "Director",
            "side": "BUY",
            "value": 250_000,
            "filedAt": "2026-08-31T20:00:00Z",
            "accession": "0000000001-26-000001",
        }
    ]
    result = export_dashboard(data, tmp_path / "live", run_id="run_1234567890123456")
    manifest = validate_dashboard_directory(result.output_dir)

    assert manifest["universe"]["activeTransactionCount"] == 1
    assert dashboard_experimental_publication_policy(manifest) == (True, False)

    manifest["quality"]["benchmarkFresh"] = False
    manifest["manifestId"] = "mft_" + _manifest_digest(manifest)[:32]
    assert dashboard_experimental_publication_policy(manifest) == (False, False)


def test_degraded_quality_measurements_must_still_be_coherent(tmp_path: Path) -> None:
    data = _data()
    data["status"] = "EXPERIMENTAL"
    quality = data["quality"]
    assert isinstance(quality, dict)
    quality["disposition"] = "DEGRADED"
    quality["issues"] = ["OOS_INCONCLUSIVE"]
    quality["marketCoverage"] = {
        "numerator": 1,
        "denominator": 100,
        "rate": 1.0,
        "threshold": 0.9,
        "result": "PASS",
    }

    with pytest.raises(DashboardExportError, match="incoherent quality measurement"):
        export_dashboard(data, tmp_path / "data", run_id="run_1234567890123456")


def test_candidate_lock_cannot_be_promoted_by_caller_quality_boolean(tmp_path: Path) -> None:
    data = _data()
    data["status"] = "VALIDATED"
    data["quality"]["disposition"] = "PASS"  # type: ignore[index]
    data["quality"]["methodologyComplete"] = True  # type: ignore[index]
    data["quality"]["issues"] = []  # type: ignore[index]
    with pytest.raises(DashboardExportError, match="JSON Schema|complete passing evidence"):
        export_dashboard(data, tmp_path / "candidate", run_id="run_1234567890123456")


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


def test_export_recovers_previous_directory_before_rejecting_new_input(tmp_path: Path) -> None:
    output = tmp_path / "data"
    export_dashboard(_data(), output, run_id="run_1234567890123456")
    previous = (output / "dashboard.json").read_bytes()
    backup = tmp_path / ".data.previous"
    output.replace(backup)
    bad = _data()
    bad["marketPulse"] = float("nan")

    with pytest.raises(DashboardExportError, match="non-finite"):
        export_dashboard(bad, output, run_id="run_1234567890123457")

    assert (output / "dashboard.json").read_bytes() == previous
    assert not backup.exists()


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


def test_signal_reference_must_be_unique_and_match_file_inventory(tmp_path: Path) -> None:
    scoring = ScoreEngine()
    data = _data()
    data["signals"] = [_signal_snapshot(scoring)]
    result = export_dashboard(data, tmp_path / "signals", run_id="run_1234567890123456")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    bad_hash = dict(manifest)
    bad_hash["signals"] = [dict(manifest["signals"][0])]
    bad_hash["signals"][0]["contentHash"] = "sha256:" + "0" * 64
    bad_hash["manifestId"] = "mft_" + _manifest_digest(bad_hash)[:32]
    with pytest.raises(DashboardExportError, match="signal hash"):
        _validate_manifest(bad_hash)

    duplicate = dict(manifest)
    duplicate["signals"] = [dict(manifest["signals"][0]), dict(manifest["signals"][0])]
    duplicate["signals"][1]["snapshotId"] = "sig_abcdefghijklmnop"
    duplicate["manifestId"] = "mft_" + _manifest_digest(duplicate)[:32]
    with pytest.raises(DashboardExportError, match="unique"):
        _validate_manifest(duplicate)

    forged = _data()
    forged["signals"] = [dict(data["signals"][0])]  # type: ignore[index]
    forged["signals"][0]["provenance"] = dict(  # type: ignore[index]
        forged["signals"][0]["provenance"]  # type: ignore[index]
    )
    forged["signals"][0]["provenance"]["scoreConfigHash"] = (  # type: ignore[index]
        "sha256:" + "0" * 64
    )
    with pytest.raises(DashboardExportError, match="scoring provenance"):
        export_dashboard(forged, tmp_path / "forged", run_id="run_1234567890123456")

    forged_time = _data()
    forged_time["signals"] = [dict(data["signals"][0])]  # type: ignore[index]
    forged_time["signals"][0]["provenance"] = dict(  # type: ignore[index]
        forged_time["signals"][0]["provenance"]  # type: ignore[index]
    )
    forged_time["signals"][0]["provenance"]["scoreFrozenAt"] = (  # type: ignore[index]
        "2015-12-31T20:00:00Z"
    )
    with pytest.raises(DashboardExportError, match="scoring.v1 lock"):
        export_dashboard(forged_time, tmp_path / "forged-time", run_id="run_1234567890123456")


def test_publication_directory_rejects_unreferenced_files(tmp_path: Path) -> None:
    result = export_dashboard(_data(), tmp_path / "data", run_id="run_1234567890123456")
    (result.output_dir / "stale.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(DashboardExportError, match="unreferenced"):
        validate_dashboard_directory(result.output_dir)
