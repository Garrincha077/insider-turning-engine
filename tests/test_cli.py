"""Smoke tests for the command-line surface and safe dry-run defaults."""

import json
from types import SimpleNamespace

from typer.testing import CliRunner

from insider_turning_engine.cli import app

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


def test_fixture_only_daily_run_has_no_network_dependency() -> None:
    result = runner.invoke(app, ["daily", "--fixture-only"])
    assert result.exit_code == 0
    assert '"status": "SUCCEEDED"' in result.stdout
    assert '"marketBars"' in result.stdout


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
