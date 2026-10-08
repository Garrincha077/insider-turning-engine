"""Restore trusted, validated Pages artifacts; never acquire data or retry delivery."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sqlite3
import subprocess
import tarfile
import zipfile
from collections.abc import Callable, Mapping
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from insider_turning_engine.export.research_policy import validate_publication
from insider_turning_engine.ingestion.sec.historical import _write_json

from .state_store import _validate_ledger, persist, restore

MAX_SITE_BYTES = 384 * 1024 * 1024
MAX_ZIP_BYTES = 128 * 1024 * 1024


class PublicationProof(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal["1.0.0"] = "1.0.0"
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    sourceRunId: str = Field(pattern=r"^[0-9]{1,20}$")
    sourceCommit: str = Field(pattern=r"^[a-f0-9]{40}$")
    sourceAttempt: Literal[1] = 1
    event: Literal["schedule", "push", "workflow_dispatch"]
    digestExpected: StrictBool
    snapshotRunId: str
    manifestSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    indexSha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def gh_bytes(path: str) -> bytes:
    try:
        result = subprocess.run(["gh", "api", path], capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise RuntimeError("GitHub read timed out; no automatic restart") from None
    if result.returncode or len(result.stdout) > MAX_ZIP_BYTES:
        raise RuntimeError("GitHub read failed or exceeded limit")
    return result.stdout


def gh_json(path: str) -> dict[str, Any]:
    value = json.loads(gh_bytes(path))
    if not isinstance(value, dict):
        raise ValueError("GitHub object required")
    return value


def source_is_trusted(run: Mapping[str, Any], repository: str) -> bool:
    return bool(
        re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        and run.get("path") == ".github/workflows/pages.yml"
        and run.get("head_branch") == "main"
        and run.get("head_repository", {}).get("full_name", "").lower()
        == repository.lower()
        and run.get("repository", {}).get("full_name", "").lower() == repository.lower()
        and run.get("event") in {"schedule", "push", "workflow_dispatch"}
        and isinstance(run.get("id"), int) and not isinstance(run.get("id"), bool)
        and re.fullmatch(r"[0-9]{1,20}", str(run["id"]))
    )


def require_recoverable_source(
    run: Mapping[str, Any], jobs: list[dict[str, Any]], repository: str,
    main_sha: str, *, now: datetime,
) -> None:
    created = datetime.fromisoformat(str(run.get("created_at", "")).replace("Z", "+00:00"))
    builds = [job for job in jobs if job.get("name") == "build"]
    if (not source_is_trusted(run, repository) or run.get("status") != "completed"
            or run.get("conclusion") != "failure" or run.get("run_attempt") != 1
            or run.get("head_sha") != main_sha or len(builds) != 1
            or builds[0].get("conclusion") != "success"
            or any(job.get("name") == "deploy" and job.get("conclusion") == "success"
                   for job in jobs)
            or now.tzinfo is None or created.tzinfo is None
            or not timedelta(0) <= now - created <= timedelta(hours=24)):
        raise ValueError("source is not eligible for publication recovery")


def seal_publication(directory: Path, environment: Mapping[str, str]) -> PublicationProof:
    if (environment.get("GITHUB_ACTIONS") != "true"
            or environment.get("GITHUB_REF") != "refs/heads/main"
            or environment.get("GITHUB_RUN_ATTEMPT") != "1"):
        raise ValueError("only an original trusted main run may seal publication")
    validate_publication(directory / "data")
    manifest = (directory / "data/manifest.json").read_bytes()
    event = environment["GITHUB_EVENT_NAME"]
    proof = PublicationProof.model_validate({
        "repository": environment["GITHUB_REPOSITORY"],
        "sourceRunId": environment["GITHUB_RUN_ID"], "sourceCommit": environment["GITHUB_SHA"],
        "event": event, "digestExpected": (event == "schedule" or (
            environment.get("REFRESH_DATA") == "true"
            and environment.get("SEND_DIGEST") == "true")),
        "snapshotRunId": json.loads(manifest)["runId"],
        "manifestSha256": hashlib.sha256(manifest).hexdigest(),
        "indexSha256": hashlib.sha256((directory / "index.html").read_bytes()).hexdigest(),
    })
    _write_json(directory / "publication-proof.json", proof.model_dump())
    return proof


def extract_pages_artifact(payload: bytes, directory: Path) -> None:
    """Inspect all paths/types/sizes before writing; never execute or use extractall."""
    if directory.exists() or len(payload) > MAX_ZIP_BYTES:
        raise ValueError("fresh output and bounded archive required")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = archive.infolist()
        if (len(members) != 1 or members[0].filename != "artifact.tar"
                or members[0].file_size > MAX_SITE_BYTES + 10 * 1024 * 1024):
            raise ValueError("unexpected Pages archive")
        tar_bytes = archive.read(members[0])
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as archive:
        files: dict[str, tarfile.TarInfo] = {}
        total = 0
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if (path.is_absolute() or ".." in path.parts or "\\" in member.name
                    or ":" in member.name or not (member.isfile() or member.isdir())
                    or member.size < 0 or member.size > 256 * 1024 * 1024):
                raise ValueError("unsafe Pages archive member")
            if not member.isfile():
                continue
            name = path.as_posix()
            if name in files or name == ".":
                raise ValueError("duplicate Pages archive path")
            files[name] = member
            total += member.size
            if total > MAX_SITE_BYTES or len(files) > 20_000:
                raise ValueError("Pages archive exceeds limit")
        if not {"index.html", "data/manifest.json", "publication-proof.json"} <= files.keys():
            raise ValueError("Pages publication proof missing")
        for name, member in files.items():
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("unreadable Pages archive member")
            content = stream.read(member.size + 1)
            if len(content) != member.size:
                raise ValueError("Pages archive size mismatch")
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)


def validate_recovered_publication(
    directory: Path, run: Mapping[str, Any], public_manifest: Mapping[str, Any],
) -> PublicationProof:
    proof = PublicationProof.model_validate_json(
        (directory / "publication-proof.json").read_bytes())
    manifest = (directory / "data/manifest.json").read_bytes()
    candidate = json.loads(manifest)
    candidate_time = datetime.fromisoformat(candidate["asOf"].replace("Z", "+00:00"))
    public_time = datetime.fromisoformat(public_manifest["asOf"].replace("Z", "+00:00"))
    if (proof.sourceRunId != str(run["id"]) or proof.sourceCommit != run["head_sha"]
            or proof.repository.lower() != run["repository"]["full_name"].lower()
            or proof.event != run["event"] or proof.sourceAttempt != run["run_attempt"]
            or proof.snapshotRunId != candidate["runId"]
            or hashlib.sha256(manifest).hexdigest() != proof.manifestSha256
            or hashlib.sha256((directory / "index.html").read_bytes()).hexdigest()
            != proof.indexSha256
            or candidate_time.tzinfo is None or public_time.tzinfo is None
            or candidate_time < public_time
            or (candidate_time == public_time and candidate["runId"] != public_manifest["runId"])):
        raise ValueError("publication lineage mismatch or newer public snapshot")
    validate_publication(directory / "data")
    return proof


def claim_recovery(
    source_run: str, recovery_run: str, manifest_hash: str, *, outbox: Path,
    save: Callable[[], None],
) -> bool:
    if (not re.fullmatch(r"[0-9]{1,20}", source_run)
            or not re.fullmatch(r"[0-9]{1,20}", recovery_run)
            or not re.fullmatch(r"[a-f0-9]{64}", manifest_hash)):
        raise ValueError("invalid recovery claim")
    if outbox.exists():
        _validate_ledger(outbox)
    outbox.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(outbox)) as db, db:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("CREATE TABLE IF NOT EXISTS publication_recoveries "
                   "(source_run TEXT PRIMARY KEY, recovery_run TEXT NOT NULL, "
                   "manifest_hash TEXT NOT NULL, claim_id TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM publication_recoveries WHERE source_run=?",
                      (source_run,)).fetchone():
            return False
        db.execute("INSERT INTO publication_recoveries VALUES (?, ?, ?, ?)",
                   (source_run, recovery_run, manifest_hash, uuid4().hex))
    save()  # A failed/uncertain reservation never authorizes publication.
    return True


def prepare_recovery(source_run: str, directory: Path) -> dict[str, str]:
    from .pipeline_watchdog import public_index_hash, public_status

    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"
            or not re.fullmatch(r"[0-9]{1,20}", source_run)):
        raise ValueError("trusted original main recovery required")
    repository = os.environ["GITHUB_REPOSITORY"]
    base = f"repos/{repository}"
    run = gh_json(f"{base}/actions/runs/{source_run}")
    jobs = gh_json(f"{base}/actions/runs/{source_run}/jobs?per_page=100")["jobs"]
    main_sha = gh_json(f"{base}/git/ref/heads/main")["object"]["sha"]
    require_recoverable_source(run, jobs, repository, main_sha, now=datetime.now(UTC))
    artifacts = gh_json(f"{base}/actions/runs/{source_run}/artifacts?per_page=100")["artifacts"]
    pages = [row for row in artifacts if row.get("name") == "github-pages"
             and row.get("expired") is False]
    if len(pages) != 1 or not 0 < pages[0].get("size_in_bytes", 0) <= MAX_ZIP_BYTES:
        raise ValueError("one unexpired bounded Pages artifact required")
    artifact = pages[0]
    payload = gh_bytes(f"{base}/actions/artifacts/{artifact['id']}/zip")
    if artifact.get("digest") != "sha256:" + hashlib.sha256(payload).hexdigest():
        raise ValueError("GitHub artifact checksum mismatch")
    extract_pages_artifact(payload, directory)
    public_manifest, _settings = public_status()
    proof = validate_recovered_publication(directory, run, public_manifest)
    if (public_manifest["_content_sha256"] == proof.manifestSha256
            and public_index_hash() == proof.indexSha256):
        return {"ready": "false", "published": "true",
                "digest_expected": str(proof.digestExpected).lower()}
    store, outbox = Path("work/recovery-state"), Path("work/recovery-alerts.sqlite")
    restore(Path.cwd(), store, outbox)
    claimed = claim_recovery(source_run, os.environ["GITHUB_RUN_ID"], proof.manifestSha256,
                             outbox=outbox, save=lambda: persist(store, outbox))
    return {"ready": str(claimed).lower(), "published": "false",
            "digest_expected": str(proof.digestExpected).lower()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["seal", "prepare"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--source-run")
    args = parser.parse_args()
    if args.operation == "seal":
        seal_publication(args.directory, os.environ)
        return
    if args.source_run is None:
        parser.error("prepare requires --source-run")
    outputs = prepare_recovery(args.source_run, args.directory)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        stream.writelines(f"{key}={value}\n" for key, value in outputs.items())
    print(json.dumps(outputs, sort_keys=True))


if __name__ == "__main__":
    main()
