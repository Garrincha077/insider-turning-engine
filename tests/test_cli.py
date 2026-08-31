"""Smoke tests for the command-line surface and safe dry-run defaults."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from insider_turning_engine.cli import app
from insider_turning_engine.scoring import ScoreEngine

runner = CliRunner()
COMMANDS = (
    "backfill-sec",
    "update-sec",
    "update-market",
    "build-features",
    "build-signals",
    "backtest",
    "export-dashboard",
    "send-alerts",
    "daily",
)


def test_help_loads_and_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in COMMANDS:
        assert command in result.stdout


def test_each_command_is_safe_to_call_without_external_side_effects() -> None:
    for command in COMMANDS:
        result = runner.invoke(app, [command])

        assert result.exit_code == 0
        assert '"status": "DRY_RUN"' in result.stdout


def test_structured_cli_inputs_reject_non_object_rows(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.json"
    candidates.write_text('[{"issuer_cik": "0000000001"}, null]', encoding="utf-8")
    alert_result = runner.invoke(app, ["send-alerts", "--candidates", str(candidates)])
    assert alert_result.exit_code != 0
    assert "every candidate must be a JSON object" in alert_result.output

    components = tmp_path / "components.json"
    components.write_text('{"total": null}', encoding="utf-8")
    score_result = runner.invoke(app, ["build-signals", "--components", str(components)])
    assert score_result.exit_code != 0
    assert "every component model must contain a JSON object" in score_result.output


def test_fixture_only_daily_run_has_no_network_dependency() -> None:
    result = runner.invoke(app, ["daily", "--fixture-only"])
    assert result.exit_code == 0
    assert '"status": "SUCCEEDED"' in result.stdout
    assert '"marketBars"' in result.stdout


def test_local_sec_update_carries_explicit_run_lineage_and_requires_aware_time(
    tmp_path: Path,
) -> None:
    fixture = Path(__file__).parent / "fixtures" / "form4_original.xml"
    output = tmp_path / "sec.json"
    args = [
        "update-sec",
        "--xml",
        str(fixture),
        "--accession",
        "0001234567-26-000001",
        "--source-url",
        "https://www.sec.gov/Archives/edgar/data/1234567/fixture/ownership.xml",
        "--run-id",
        "run_test_cli_lineage_1234",
        "--output",
        str(output),
    ]
    naive = runner.invoke(app, [*args, "--accepted-at", "2026-08-30T12:00:00"])
    assert naive.exit_code != 0
    assert "must include a timezone" in naive.output

    result = runner.invoke(app, [*args, "--accepted-at", "2026-08-30T12:00:00Z"])
    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["records"]
    assert {record["runId"] for record in payload["records"]} == {"run_test_cli_lineage_1234"}


def test_backtest_uses_explicit_separate_benchmark_streams(tmp_path: Path) -> None:
    sessions: list[date] = []
    cursor = date(2023, 1, 3)
    while len(sessions) < 140:
        if cursor.weekday() < 5:
            sessions.append(cursor)
        cursor += timedelta(days=1)
    market = tmp_path / "market.csv"
    lines = ["date,ticker,open,high,low,close,adj_close,volume"]
    for index, session in enumerate(sessions):
        for ticker, base in (("ACME", 100), ("SPY", 200)):
            price = base + index
            lines.append(
                f"{session.isoformat()},{ticker},{price},{price + 2},{price - 2},"
                f"{price + 1},{price + 1},1000"
            )
    market.write_text("\n".join(lines) + "\n", encoding="utf-8")

    scoring = ScoreEngine()
    common = {
        "ticker": "ACME",
        "signal_type": "TURNING",
        "score": 80,
        "accepted_at": datetime(2023, 1, 4, 14, tzinfo=UTC).isoformat(),
        "score_config_hash": scoring.score_config_hash,
        "score_lineage": scoring.score_lineage,
        "frozen_at": scoring.score_frozen_at.isoformat(),
    }
    events = tmp_path / "events.json"
    events.write_text(
        json.dumps(
            [
                {**common, "signal_id": "full", "exposure_family": "FULL_ENGINE"},
                {**common, "signal_id": "ps", "exposure_family": "SIMPLE_PS"},
            ]
        ),
        encoding="utf-8",
    )
    evidence = tmp_path / "validation-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "parse_success_rate": 0.995,
                "market_coverage": 0.90,
                "core_branch_coverage": 0.85,
                "canonical_valid": True,
                "schema_valid": True,
                "hash_valid": True,
                "temporal_valid": True,
                "benchmark_fresh": False,
                "scoring_methodology_complete": True,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report.json"

    result = runner.invoke(
        app,
        [
            "backtest",
            "--events",
            str(events),
            "--bars",
            str(market),
            "--validation-evidence",
            str(evidence),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "FAIL"
    assert "benchmark freshness" in report["formalReport"]["gate"]["reason"]
    assert report["benchmarkEvents"] == {"simple_ps": 1}
    names = {row["name"] for row in report["formalReport"]["benchmark_table"]}
    assert {"full_engine", "simple_ps"} <= names


def test_backfill_rejects_non_identifying_sec_user_agent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "operator@example.com")
    result = runner.invoke(
        app,
        [
            "backfill-sec",
            "--year",
            "2024",
            "--quarter",
            "1",
            "--cache-dir",
            str(tmp_path / "cache"),
            "--staging-dir",
            str(tmp_path / "stage"),
            "--execute",
        ],
    )
    assert result.exit_code != 0
    assert not (tmp_path / "cache").exists()


def test_send_alerts_preview_retains_candidates_in_outbox(tmp_path) -> None:
    candidates = tmp_path / "candidates.json"
    candidates.write_text(
        json.dumps(
            [
                {
                    "issuer_cik": "0000000001",
                    "alert_type": "TURNING",
                    "trigger_snapshot_id": "snap_preview",
                    "score": 80,
                }
            ]
        ),
        encoding="utf-8",
    )
    outbox = tmp_path / "alerts.sqlite"
    result = runner.invoke(
        app,
        ["send-alerts", "--candidates", str(candidates), "--outbox", str(outbox)],
    )
    assert result.exit_code == 0
    assert outbox.is_file()
    from insider_turning_engine.notifications import SQLiteOutbox

    ledger = SQLiteOutbox(outbox)
    try:
        assert ledger.get_candidate("0000000001:TURNING:snap_preview") is not None
    finally:
        ledger.close()


def test_send_alerts_execute_requires_pass_manifest(tmp_path, monkeypatch) -> None:
    candidates = tmp_path / "candidates.json"
    candidates.write_text(
        json.dumps(
            [
                {
                    "issuer_cik": "0000000001",
                    "alert_type": "TURNING",
                    "trigger_snapshot_id": "snap_execute",
                    "score": 80,
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")

    missing = runner.invoke(
        app,
        ["send-alerts", "--candidates", str(candidates), "--execute"],
    )
    assert missing.exit_code != 0
    assert "--manifest is required" in missing.output

    sample_manifest = Path(__file__).parents[1] / "app" / "public" / "data" / "manifest.json"
    degraded = runner.invoke(
        app,
        [
            "send-alerts",
            "--candidates",
            str(candidates),
            "--manifest",
            str(sample_manifest),
            "--execute",
        ],
    )
    assert degraded.exit_code != 0
    assert "PASS publication manifest" in degraded.output


def test_update_sec_does_not_advance_cursor_after_fetch_failure(tmp_path, monkeypatch) -> None:
    class FailingSource:
        def __init__(self, *args, **kwargs):
            return None

        def fetch(self, *args, **kwargs):
            return SimpleNamespace(
                records=[SimpleNamespace(provider_record_id="filing-1")],
                next_cursor="would-advance",
                quarantines=[],
            )

        def get(self, provider_record_id):
            return SimpleNamespace(status=SimpleNamespace(value="retryable"), message="upstream")

    monkeypatch.setattr("insider_turning_engine.cli.SECIncrementalSource", FailingSource)
    monkeypatch.setenv("SEC_USER_AGENT", "InsiderTurningEngine (+you@example.com)")
    cik_file = tmp_path / "ciks.txt"
    cik_file.write_text("1234567\n", encoding="utf-8")
    cursor_file = tmp_path / "sec.cursor"
    result = runner.invoke(
        app,
        [
            "update-sec",
            "--cik-file",
            str(cik_file),
            "--cursor-file",
            str(cursor_file),
            "--output",
            str(tmp_path / "output.json"),
            "--execute",
        ],
    )
    assert result.exit_code != 0
    assert not cursor_file.exists()
    payload = json.loads((tmp_path / "output.json").read_text(encoding="utf-8"))
    assert payload["failures"][0]["status"] == "retryable"
