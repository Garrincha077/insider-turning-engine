import hashlib
import io
import json
import sqlite3
import subprocess
import tarfile
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
from test_research_publication import _publication

from insider_turning_engine.notifications import pipeline_watchdog as watchdog
from insider_turning_engine.notifications import publication_recovery as recovery

NOW = datetime(2026, 10, 7, 17, tzinfo=UTC)
SHA = "a" * 40


def _run(**changes):
    return {"id": 123, "repository": {"full_name": "owner/repo"},
            "head_repository": {"full_name": "owner/repo"}, "head_branch": "main",
            "path": ".github/workflows/pages.yml", "event": "schedule", "head_sha": SHA,
            "status": "completed", "conclusion": "failure", "run_attempt": 1,
            "created_at": (NOW - timedelta(hours=1)).isoformat(), **changes}


def _environment(**changes):
    return {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main",
            "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_SHA": SHA, "GITHUB_RUN_ID": "123", "GITHUB_EVENT_NAME": "schedule",
            **changes}


def _site(path):
    path.mkdir()
    (path / "index.html").write_text("<html>validated build</html>")
    _publication(path / "data")
    recovery.seal_publication(path, _environment())
    return path


def _zip(entries):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        for name, content, kind in entries:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.size = len(content) if kind == tarfile.REGTYPE else 0
            if kind in {tarfile.SYMTYPE, tarfile.LNKTYPE}:
                info.linkname = "../../outside"
            archive.addfile(info, io.BytesIO(content) if kind == tarfile.REGTYPE else None)
    compressed = io.BytesIO()
    with zipfile.ZipFile(compressed, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("artifact.tar", raw.getvalue())
    return compressed.getvalue()


def _site_zip(site):
    return _zip([(f"./{p.relative_to(site).as_posix()}", p.read_bytes(), tarfile.REGTYPE)
                 for p in site.rglob("*") if p.is_file()])


def test_only_original_recent_failed_main_build_can_be_recovered():
    recovery.require_recoverable_source(_run(), [{"name": "build", "conclusion": "success"}],
                                        "owner/repo", SHA, now=NOW)


@pytest.mark.parametrize("change", [
    {"head_repository": {"full_name": "attacker/fork"}},
    {"repository": {"full_name": "other/repo"}}, {"head_branch": "untrusted"},
    {"path": ".github/workflows/ci.yml"}, {"event": "pull_request"},
    {"run_attempt": 2}, {"status": "in_progress"}, {"conclusion": "success"},
    {"head_sha": "b" * 40}, {"created_at": (NOW - timedelta(hours=25)).isoformat()},
    {"created_at": (NOW + timedelta(seconds=1)).isoformat()},
    {"created_at": "2026-10-07T16:00:00"},
])
def test_untrusted_stale_future_or_rerun_source_is_refused(change):
    with pytest.raises(ValueError):
        recovery.require_recoverable_source(_run(**change),
            [{"name": "build", "conclusion": "success"}], "owner/repo", SHA, now=NOW)


@pytest.mark.parametrize("jobs", [[], [{"name": "build", "conclusion": "failure"}],
    [{"name": "build", "conclusion": "success"}] * 2,
    [{"name": "build", "conclusion": "success"}, {"name": "deploy", "conclusion": "success"}],
])
def test_unvalidated_build_or_digest_only_failure_never_republishes(jobs):
    with pytest.raises(ValueError):
        recovery.require_recoverable_source(_run(), jobs, "owner/repo", SHA, now=NOW)


@pytest.mark.parametrize("event,refresh,send,expected", [
    ("schedule", "", "", True), ("push", "", "", False),
    ("workflow_dispatch", "true", "true", True),
    ("workflow_dispatch", "true", "false", False),
    ("workflow_dispatch", "false", "true", False),
])
def test_proof_preserves_original_delivery_intent(tmp_path, event, refresh, send, expected):
    site = _site(tmp_path / "site")
    proof = recovery.seal_publication(site, _environment(
        GITHUB_EVENT_NAME=event, REFRESH_DATA=refresh, SEND_DIGEST=send))
    assert proof.digestExpected is expected
    assert proof.manifestSha256 == hashlib.sha256(
        (site / "data/manifest.json").read_bytes()).hexdigest()


@pytest.mark.parametrize("change", [{"GITHUB_REF": "refs/heads/dev"},
    {"GITHUB_ACTIONS": "false"}, {"GITHUB_RUN_ATTEMPT": "2"}])
def test_local_fork_and_rerun_cannot_seal(tmp_path, change):
    with pytest.raises(ValueError, match="trusted main"):
        recovery.seal_publication(tmp_path, _environment(**change))


def test_pages_zip_restores_regular_files_and_revalidates_actual_snapshot(tmp_path):
    site = _site(tmp_path / "original")
    output = tmp_path / "recovered"
    recovery.extract_pages_artifact(_site_zip(site), output)
    manifest = json.loads((site / "data/manifest.json").read_bytes())
    proof = recovery.validate_recovered_publication(output, _run(), manifest)
    assert proof.sourceRunId == "123"
    assert (site / "data/research-v2.json").read_bytes() == (
        output / "data/research-v2.json").read_bytes()


@pytest.mark.parametrize("name,kind", [("../../outside", tarfile.REGTYPE),
    ("/absolute", tarfile.REGTYPE), ("C:/drive", tarfile.REGTYPE),
    ("back\\slash", tarfile.REGTYPE), ("link", tarfile.SYMTYPE),
    ("hardlink", tarfile.LNKTYPE), ("device", tarfile.CHRTYPE),
])
def test_archive_paths_links_and_devices_are_refused_before_any_write(tmp_path, name, kind):
    output = tmp_path / "output"
    payload = _zip([("index.html", b"first", tarfile.REGTYPE), (name, b"bad", kind)])
    with pytest.raises(ValueError, match="unsafe"):
        recovery.extract_pages_artifact(payload, output)
    assert not output.exists()


def test_duplicate_missing_proof_oversize_and_existing_output_are_refused(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="duplicate"):
        recovery.extract_pages_artifact(_zip([
            ("./index.html", b"a", tarfile.REGTYPE), ("index.html", b"b", tarfile.REGTYPE)]),
            tmp_path / "duplicate")
    payload = _zip([("index.html", b"hello", tarfile.REGTYPE)])
    with pytest.raises(ValueError, match="proof missing"):
        recovery.extract_pages_artifact(payload, tmp_path / "missing")
    monkeypatch.setattr(recovery, "MAX_SITE_BYTES", 2)
    with pytest.raises(ValueError, match="exceeds limit"):
        recovery.extract_pages_artifact(payload, tmp_path / "huge")
    with pytest.raises(ValueError, match="fresh output"):
        recovery.extract_pages_artifact(payload, tmp_path)


@pytest.mark.parametrize("change", [{"id": 234}, {"head_sha": "b" * 40},
    {"event": "push"}, {"run_attempt": 2}, {"repository": {"full_name": "other/repo"}}])
def test_proof_cannot_be_used_for_different_source(tmp_path, change):
    site = _site(tmp_path / "site")
    manifest = json.loads((site / "data/manifest.json").read_bytes())
    with pytest.raises(ValueError, match="lineage"):
        recovery.validate_recovered_publication(site, _run(**change), manifest)


def test_newer_public_snapshot_and_tampered_files_block_recovery(tmp_path):
    site = _site(tmp_path / "site")
    manifest = json.loads((site / "data/manifest.json").read_bytes())
    with pytest.raises(ValueError, match="newer"):
        recovery.validate_recovered_publication(site, _run(),
            {**manifest, "asOf": "2030-01-01T00:00:00Z"})
    (site / "index.html").write_text("changed after validation")
    with pytest.raises(ValueError, match="lineage"):
        recovery.validate_recovered_publication(site, _run(), manifest)
    (site / "index.html").write_text("<html>validated build</html>")
    (site / "data/research-v2.json").write_text("{}")
    with pytest.raises(ValueError, match="size mismatch|hash mismatch"):
        recovery.validate_recovered_publication(site, _run(), manifest)


def test_recovery_reservation_is_durable_and_never_repeated(tmp_path):
    ledger = tmp_path / "ledger.sqlite"
    saves = []

    def save():
        with sqlite3.connect(ledger) as db:
            saves.append(db.execute("SELECT source_run FROM publication_recoveries").fetchone()[0])

    assert recovery.claim_recovery("123", "456", "a" * 64, outbox=ledger, save=save)
    assert saves == ["123"]
    assert not recovery.claim_recovery("123", "789", "a" * 64, outbox=ledger,
                                       save=lambda: pytest.fail("duplicate save"))


def test_uncertain_reservation_persistence_never_authorizes_retry(tmp_path):
    ledger = tmp_path / "ledger.sqlite"
    with pytest.raises(RuntimeError, match="storage"):
        recovery.claim_recovery("123", "456", "a" * 64, outbox=ledger,
            save=lambda: (_ for _ in ()).throw(RuntimeError("storage")))
    assert not recovery.claim_recovery("123", "456", "a" * 64, outbox=ledger,
                                       save=lambda: pytest.fail("retry"))


def test_failed_or_timed_out_github_read_never_leaks_stderr(monkeypatch):
    monkeypatch.setattr(recovery.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(
        a, 1, b"private-output", b"private-authentication"))
    with pytest.raises(RuntimeError) as error:
        recovery.gh_bytes("repos/owner/repo")
    assert "private" not in str(error.value)
    monkeypatch.setattr(recovery.subprocess, "run", lambda *a, **kw: (
        _ for _ in ()).throw(subprocess.TimeoutExpired("private-argument", 180)))
    with pytest.raises(RuntimeError, match="no automatic restart"):
        recovery.gh_bytes("repos/owner/repo")


def test_prepare_rechecks_api_artifact_checksum_and_claim_before_ready(tmp_path, monkeypatch):
    site = _site(tmp_path / "site")
    payload = _site_zip(site)
    run = _run(created_at=datetime.now(UTC).isoformat())
    artifact = {"name": "github-pages", "expired": False, "size_in_bytes": len(payload),
                "id": 789, "digest": "sha256:" + hashlib.sha256(payload).hexdigest()}

    def api(path):
        if "/jobs?" in path:
            return {"jobs": [{"name": "build", "conclusion": "success"}]}
        if "/artifacts?" in path:
            return {"artifacts": [artifact]}
        if "git/ref" in path:
            return {"object": {"sha": SHA}}
        return run

    for key, value in _environment(GITHUB_RUN_ID="456").items():
        monkeypatch.setenv(key, value)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(recovery, "gh_json", api)
    monkeypatch.setattr(recovery, "gh_bytes", lambda _: payload)
    manifest = json.loads((site / "data/manifest.json").read_bytes())
    monkeypatch.setattr(watchdog, "public_status", lambda: (
        {**manifest, "_content_sha256": "0" * 64}, {}))
    monkeypatch.setattr(watchdog, "public_index_hash", lambda: "0" * 64)
    monkeypatch.setattr(recovery, "restore", lambda *a: None)
    saved = []
    monkeypatch.setattr(recovery, "persist", lambda *a: saved.append("DURABLE"))
    assert recovery.prepare_recovery("123", tmp_path / "recovered") == {
        "ready": "true", "published": "false", "digest_expected": "true"}
    assert saved == ["DURABLE"]
    artifact["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="checksum"):
        recovery.prepare_recovery("123", tmp_path / "corrupt")
    assert not (tmp_path / "corrupt").exists()
    artifact["digest"] = "sha256:" + hashlib.sha256(payload).hexdigest()
    proof = recovery.PublicationProof.model_validate_json(
        (site / "publication-proof.json").read_bytes())
    monkeypatch.setattr(watchdog, "public_status", lambda: (
        {**manifest, "_content_sha256": proof.manifestSha256}, {}))
    monkeypatch.setattr(watchdog, "public_index_hash", lambda: proof.indexSha256)
    monkeypatch.setattr(recovery, "restore", lambda *a: pytest.fail("already public: no mutation"))
    assert recovery.prepare_recovery("123", tmp_path / "already") == {
        "ready": "false", "published": "true", "digest_expected": "true"}
    assert saved == ["DURABLE"]


def test_public_status_checks_manifest_settings_hash_once(tmp_path, monkeypatch):
    import httpx

    site = _site(tmp_path / "site")
    client_type = httpx.Client
    requested = []

    def handler(request):
        name = request.url.path.rsplit("/", 1)[-1]
        requested.append(name)
        return httpx.Response(200, content=(site / "data" / name).read_bytes())

    monkeypatch.setattr(watchdog.httpx, "Client", lambda **kw: client_type(
        transport=httpx.MockTransport(handler), **kw))
    manifest, settings = watchdog.public_status()
    assert settings and manifest["_content_sha256"] == hashlib.sha256(
        (site / "data/manifest.json").read_bytes()).hexdigest()
    assert requested == ["manifest.json", "settings-status.json"]
