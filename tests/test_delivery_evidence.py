import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from insider_turning_engine.notifications import (
    SendResult,
    SQLiteOutbox,
    build_settings_status,
    load_notification_policy,
)
from insider_turning_engine.notifications.state_store import persist, restore


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare")
    project = tmp_path / "project"
    project.mkdir()
    git(project, "init")
    git(project, "remote", "add", "origin", str(remote))
    return project


def test_intent_is_durable_separate_from_signal_cooldown(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    ledger = SQLiteOutbox(path)
    ledger.prepare_delivery_test("gh_1", "telegram")
    ledger.close()
    ledger = SQLiteOutbox(path)
    try:
        assert ledger.test_history()[0]["status"] == "UNCERTAIN"
        assert ledger.history() == ()
        assert ledger.claim_delivery_test("gh_1", "telegram")
        assert not ledger.claim_delivery_test("gh_1", "telegram")
        ledger.record_delivery_test("telegram", SendResult.sent("receipt"), test_id="gh_1")
        assert len(ledger.test_history()) == 1
        assert ledger.test_history()[0]["status"] == "SENT"
        with pytest.raises(sqlite3.IntegrityError):
            ledger.prepare_delivery_test("gh_1", "telegram")
    finally:
        ledger.close()


def test_git_state_roundtrip_and_concurrent_writer_rejected(repo: Path, tmp_path: Path) -> None:
    store, path = tmp_path / "first", tmp_path / "first.sqlite"
    restore(repo, store, path)
    ledger = SQLiteOutbox(path)
    ledger.prepare_delivery_test("gh_1", "telegram")
    ledger.close()
    persist(store, path)
    (store / "watermarks.json").write_text('{"sec":"unchanged"}')
    git(store, "add", "watermarks.json")
    git(store, "commit", "-m", "Existing SEC state")
    git(store, "push", "origin", "HEAD:refs/heads/state")
    for name in ("second", "third"):
        restore(repo, tmp_path / name, tmp_path / f"{name}.sqlite")
        ledger = SQLiteOutbox(tmp_path / f"{name}.sqlite")
        ledger.prepare_delivery_test(name, "telegram")
        ledger.close()
    persist(tmp_path / "second", tmp_path / "second.sqlite")
    with pytest.raises(RuntimeError, match="no state was overwritten"):
        persist(tmp_path / "third", tmp_path / "third.sqlite")
    restore(repo, tmp_path / "last", tmp_path / "last.sqlite")
    assert json.loads((tmp_path / "last/watermarks.json").read_text()) == {"sec": "unchanged"}
    ledger = SQLiteOutbox(tmp_path / "last.sqlite")
    try:
        assert len(ledger.test_history()) == 2
    finally:
        ledger.close()


def test_settings_separates_test_success_and_signal_delivery(tmp_path: Path) -> None:
    ledger = SQLiteOutbox(tmp_path / "ledger.sqlite")
    ledger.prepare_delivery_test("gh_1", "telegram")
    assert ledger.claim_delivery_test("gh_1", "telegram")
    ledger.record_delivery_test("telegram", SendResult.sent("private-provider-id"), test_id="gh_1")
    try:
        status = build_settings_status(
            load_notification_policy(), environment="production", alerts_allowed=False,
            blocking_reasons=(), secrets={},
            test_history=[dict(row) for row in ledger.test_history()],
        )
    finally:
        ledger.close()
    channel = status["channels"]["telegram"]
    assert channel["lastTestStatus"] == "SENT"
    assert channel["lastSuccessAt"] is None
    assert channel["testFailureCount"] == 0
    assert status["deliveryHistory"][0]["kind"] == "TEST"
    assert "private-provider-id" not in json.dumps(status)


def test_corrupt_restore_does_not_create_an_empty_ledger(repo: Path, tmp_path: Path) -> None:
    store, path = tmp_path / "first", tmp_path / "ledger.sqlite"
    restore(repo, store, path)
    path.write_bytes(b"corrupt")
    with pytest.raises(sqlite3.DatabaseError):
        persist(store, path)
    assert git(repo, "ls-remote", "origin", "refs/heads/state") == ""
