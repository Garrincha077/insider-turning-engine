import json
import sqlite3

import pytest

from insider_turning_engine.notifications import workflow_status as workflow
from insider_turning_engine.notifications.models import SendResult


def _report(**changes):
    results = {"build": "success", "deploy": "success", "digest": "success", **changes}
    return workflow.status_report("owner/repo", "1234", results, digest_expected=True)


def test_success_never_sends_and_intentional_digest_skip_is_not_failure(tmp_path):
    report = workflow.status_report("owner/repo", "1234",
        {"build": "success", "deploy": "success", "digest": "skipped"}, digest_expected=False)
    assert report["status"] == "SUCCESS" and report["text"] == ""
    assert workflow.send_notice(report, outbox=tmp_path / "ledger",
        save=lambda: pytest.fail("state mutation"), send=lambda _: pytest.fail("network")) \
        == "NOT_NEEDED"
    assert not (tmp_path / "ledger").exists()


def test_failed_refresh_and_digest_have_distinct_actionable_messages():
    report = _report(build="cancelled", deploy="skipped", digest="skipped")
    assert report["status"] == "FAILED"
    assert "Previous public snapshot retained" in report["text"]
    assert "https://github.com/owner/repo/actions/runs/1234" in report["text"]
    assert "Dashboard updated" in _report(digest="failure")["text"]


@pytest.mark.parametrize("result", [SendResult.sent("123"), SendResult.uncertain("timeout"),
                                   SendResult.failed("unavailable")])
def test_notice_claim_is_durable_before_send_and_replays_never_send(tmp_path, result):
    path = tmp_path / "alerts.sqlite"
    calls = []

    def save():
        with sqlite3.connect(path) as db:
            status = db.execute("SELECT status FROM workflow_notices").fetchone()[0]
        calls.append(status)

    def send(text):
        assert calls == ["CLAIMED"]
        calls.append("SEND")
        return result

    report = _report(build="failure", deploy="skipped", digest="skipped")
    assert workflow.send_notice(report, outbox=path, save=save, send=send) == result.status.value
    assert calls == ["CLAIMED", "SEND", result.status.value]
    assert workflow.send_notice(report, outbox=path, save=lambda: pytest.fail("save"),
                                send=lambda _: pytest.fail("retry")) == "ALREADY_CLAIMED"


def test_failed_claim_persistence_never_contacts_provider_or_retries(tmp_path):
    report = _report(build="failure", deploy="skipped", digest="skipped")
    path = tmp_path / "alerts.sqlite"
    with pytest.raises(RuntimeError, match="storage"):
        workflow.send_notice(report, outbox=path,
            save=lambda: (_ for _ in ()).throw(RuntimeError("storage")),
            send=lambda _: pytest.fail("network before claim"))
    assert workflow.send_notice(report, outbox=path, save=lambda: pytest.fail("retry"),
                                send=lambda _: pytest.fail("retry")) == "ALREADY_CLAIMED"


def test_notice_preview_is_offline_and_writes_safe_report_and_summary(tmp_path, monkeypatch):
    report, summary = tmp_path / "status.json", tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "1234")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    for name, result in {"BUILD": "failure", "DEPLOY": "skipped", "DIGEST": "skipped"}.items():
        monkeypatch.setenv(f"RESULT_{name}", result)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "never-public-token")
    monkeypatch.setattr(workflow, "restore", lambda *_: pytest.fail("preview restore"))
    monkeypatch.setattr(workflow.httpx, "post", lambda *_: pytest.fail("preview network"))
    monkeypatch.setattr("sys.argv", ["status", "--output", str(report)])
    workflow.main()
    assert json.loads(report.read_text())["notificationStatus"] == "PREVIEW"
    assert "never-public-token" not in report.read_text()
    assert "| build | failure |" in summary.read_text()


def test_invalid_source_fields_are_rejected():
    with pytest.raises(ValueError, match="workflow"):
        workflow.status_report("not/a/repository", "1234", {}, digest_expected=False)
