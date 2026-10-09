import json
import sqlite3
from datetime import UTC, datetime

import pytest
from test_publication_recovery import NOW, _environment, _run

from insider_turning_engine.notifications import pipeline_watchdog as watchdog

MARKET_OK = {"quality": {"marketCoverage": {"numerator": 80, "denominator": 100},
                          "benchmarkFresh": True}}


def _api(run, jobs):
    def fetch(path):
        if "/jobs?" in path:
            return {"jobs": jobs}
        if "/runs?" in path:
            return {"workflow_runs": [run]}
        return run
    return fetch


def test_completed_internal_error_without_downstream_jobs_is_recoverable(monkeypatch):
    monkeypatch.setattr(watchdog, "gh_json", _api(_run(),
        [{"name": "build", "conclusion": "success"}]))
    plan = watchdog.inspect_source("owner/repo", "123")
    assert plan["recover"] and plan["status"] == "FAILED"
    assert plan["results"] == {"build": "success", "deploy": "skipped", "digest": "skipped"}


@pytest.mark.parametrize("change,status", [
    ({"status": "in_progress"}, "WAIT"), ({"conclusion": "cancelled"}, "IGNORED"),
    ({"head_repository": {"full_name": "attacker/fork"}}, "UNTRUSTED_SOURCE"),
    ({"run_attempt": 2}, "FAILED"),
])
def test_live_cancelled_fork_or_rerun_never_recovers(monkeypatch, change, status):
    monkeypatch.setattr(watchdog, "gh_json", _api(_run(**change),
        [{"name": "build", "conclusion": "success"}]))
    plan = watchdog.inspect_source("owner/repo", "123")
    assert not plan["recover"] and plan["status"] == status


def test_digest_failure_does_not_redeploy_or_retry_telegram(monkeypatch):
    jobs = [{"name": name, "conclusion": result} for name, result in {
        "build": "success", "deploy": "success", "digest": "failure"}.items()]
    monkeypatch.setattr(watchdog, "gh_json", _api(_run(), jobs))
    plan = watchdog.inspect_source("owner/repo", "123")
    assert not plan["recover"] and plan["digest_expected"]


def test_fallback_waits_for_live_job_and_handles_missing_source(monkeypatch):
    monkeypatch.setattr(watchdog, "gh_json", _api(_run(status="queued"), []))
    assert watchdog.inspect_source("owner/repo", None)["status"] == "WAIT"
    monkeypatch.setattr(watchdog, "gh_json", lambda _: {"workflow_runs": []})
    assert watchdog.inspect_source("owner/repo", None)["status"] == "MISSING_RUN"
    with pytest.raises(ValueError, match="source run"):
        watchdog.inspect_source("owner/repo", "123\noutput=true")


def test_completed_recovery_intentional_skip_is_success_but_expected_digest_is_failure(tmp_path):
    plan = {"status": "FAILED", "source_run": "123", "explicit_source": True}
    common = {"repository": "owner/repo", "recovery_deployed": True,
              "recovery_digest": "skipped", "now": NOW, "outbox": tmp_path / "ledger"}
    assert watchdog.report_health(plan, digest_expected=False, **common)["status"] == "SUCCESS"
    report = watchdog.report_health(plan, digest_expected=True, **common)
    assert report["status"] == "FAILED" and "Dashboard updated" in report["text"]


def test_no_notification_or_mutation_while_waiting(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "456")
    for state in ("WAIT", "IGNORED", "UNTRUSTED_SOURCE"):
        report = watchdog.report_health({"status": state}, repository="owner/repo",
            recovery_deployed=False, recovery_digest="skipped", digest_expected=True,
            now=NOW, outbox=tmp_path / "missing")
        assert report["text"] == "" and report["status"] == "WAIT"
    assert not (tmp_path / "missing").exists()


def test_fallback_requires_current_sec_day_and_durable_sent_not_preview(tmp_path, monkeypatch):
    plan = {"status": "SUCCESS", "source_run": "123", "explicit_source": False,
            "results": {"build": "success", "deploy": "success", "digest": "success"}}
    day = "2026-10-06"
    monkeypatch.setattr(watchdog, "public_status", lambda: (MARKET_OK, {"digest": {
        "secDay": day, "status": "READY", "deliveryHistory": [{"status": "SENT"}]}}))
    ledger = tmp_path / "ledger.sqlite"
    common = {"repository": "owner/repo", "recovery_deployed": False,
              "recovery_digest": "skipped", "digest_expected": True, "now": NOW, "outbox": ledger}
    assert watchdog.report_health(plan, **common)["status"] == "FAILED"
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TABLE factual_digest_claims (channel TEXT, sec_day TEXT, status TEXT)")
        db.execute("INSERT INTO factual_digest_claims VALUES ('telegram', ?, 'UNCERTAIN')", (day,))
    assert watchdog.report_health(plan, **common)["status"] == "FAILED"
    with sqlite3.connect(ledger) as db:
        db.execute("UPDATE factual_digest_claims SET status='SENT'")
    assert watchdog.report_health(plan, **common)["status"] == "SUCCESS"
    monkeypatch.setattr(watchdog, "public_status",
                        lambda: ({}, {"digest": {"secDay": "2026-10-05"}}))
    assert watchdog.report_health(plan, **common)["status"] == "FAILED"


def test_inspection_never_restores_state_or_contacts_telegram(tmp_path, monkeypatch):
    for key, value in _environment(GITHUB_RUN_ID="456").items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "outputs"))
    monkeypatch.setattr(watchdog, "gh_json", _api(_run(),
        [{"name": "build", "conclusion": "success"}]))
    monkeypatch.setattr(watchdog, "restore", lambda *_: pytest.fail("state mutation"))
    monkeypatch.setattr(watchdog.httpx, "post", lambda *_: pytest.fail("Telegram send"))
    plan = tmp_path / "plan.json"
    monkeypatch.setattr("sys.argv", ["watchdog", "inspect", "--source-run", "123",
                                   "--plan", str(plan)])
    watchdog.main()
    assert json.loads(plan.read_text())["recover"]
    assert "source_run=123\n" in (tmp_path / "outputs").read_text()


def test_fallback_evaluates_morning_cycle_not_a_later_short_session_close():
    assert watchdog.expected_digest_day(datetime(2026, 11, 27, 18, tzinfo=UTC)) == "2026-11-25"
    assert watchdog.expected_digest_day(NOW) == "2026-10-06"
    assert watchdog.expected_digest_day(datetime(2026, 10, 7, 3, tzinfo=UTC)) == "2026-10-05"


def test_successful_recovery_digest_job_is_not_proof_of_sent(tmp_path, monkeypatch):
    plan = {"status": "FAILED", "source_run": "123", "explicit_source": True}
    ledger = tmp_path / "ledger.sqlite"
    monkeypatch.setattr(watchdog, "public_status",
                        lambda: (MARKET_OK, {"digest": {"secDay": "2026-10-06"}}))
    common = {"repository": "owner/repo", "recovery_deployed": True,
              "recovery_digest": "success", "digest_expected": True, "now": NOW,
              "outbox": ledger}
    assert watchdog.report_health(plan, **common)["status"] == "FAILED"
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TABLE factual_digest_claims (channel TEXT, sec_day TEXT, status TEXT)")
        db.execute("INSERT INTO factual_digest_claims VALUES ('telegram', '2026-10-06', 'CLAIMED')")
    assert watchdog.report_health(plan, **common)["status"] == "FAILED"
    with sqlite3.connect(ledger) as db:
        db.execute("UPDATE factual_digest_claims SET status='SENT'")
    assert watchdog.report_health(plan, **common)["status"] == "SUCCESS"


@pytest.mark.parametrize("numerator,denominator,benchmark,warning", [
    (80, 100, True, None), (89, 100, True, None), (79, 100, True, "below the 80%"),
    (80, 100, False, "benchmarks"), (0, 0, True, "invalid"),
    (True, 100, True, "invalid"), (101, 100, True, "invalid"),
])
def test_watchdog_daily_use_target_is_80_not_predictive_90(
    numerator, denominator, benchmark, warning,
):
    value = watchdog.daily_market_warning({"quality": {
        "marketCoverage": {"numerator": numerator, "denominator": denominator,
                           "rate": 1.0, "threshold": 0.9},
        "benchmarkFresh": benchmark}})
    assert value is None if warning is None else warning in value


def test_green_deploy_and_sent_digest_do_not_hide_low_market_coverage(tmp_path, monkeypatch):
    manifest = {"quality": {"marketCoverage": {"numerator": 1380, "denominator": 1846},
                            "benchmarkFresh": True}}
    monkeypatch.setattr(watchdog, "public_status",
                        lambda: (manifest, {"digest": {"secDay": "2026-10-06"}}))
    monkeypatch.setattr(watchdog, "digest_sent", lambda *args: True)
    plan = {"status": "SUCCESS", "source_run": "123", "explicit_source": True,
            "results": {"build": "success", "deploy": "success", "digest": "success"}}
    report = watchdog.report_health(plan, repository="owner/repo", recovery_deployed=False,
        recovery_digest="skipped", digest_expected=True, now=NOW, outbox=tmp_path / "missing")
    assert report["status"] == "FAILED"
    assert "74.76%" in report["text"] and "digest was sent" in report["text"]
    assert not (tmp_path / "missing").exists()
