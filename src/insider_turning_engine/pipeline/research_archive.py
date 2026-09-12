"""Immutable daily factual snapshots; operational state follows verified storage."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import tempfile
from pathlib import Path
from typing import Any

from insider_turning_engine.domain.research import ResearchSnapshot
from insider_turning_engine.export.research_policy import validate_publication
from insider_turning_engine.ingestion.sec.release_store import ReleaseCheckpointStore

MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024


def decode_snapshot(payload: bytes, digest: str) -> ResearchSnapshot:
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise ValueError("snapshot archive exceeds size limit")
    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
        raw = stream.read(MAX_SNAPSHOT_BYTES + 1)
    if len(raw) > MAX_SNAPSHOT_BYTES or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("snapshot archive checksum or size mismatch")
    return ResearchSnapshot.model_validate_json(raw)


class ResearchArchive(ReleaseCheckpointStore):
    def publish(self, directory: Path) -> dict[str, str]:
        validate_publication(directory)
        raw = (directory / "research-v2.json").read_bytes()
        research = ResearchSnapshot.model_validate_json(raw)
        if len(raw) > MAX_SNAPSHOT_BYTES:
            raise ValueError("snapshot exceeds archive limit")
        digest = hashlib.sha256(raw).hexdigest()
        name = f"research-{digest}.json.gz"
        tag = f"research-day-v2-{research.as_of.date()}-{digest}"
        existing = next((row for row in self._releases() if row["tag_name"] == tag), None)
        if existing is None:
            with tempfile.TemporaryDirectory(prefix="ite-research-upload-") as temporary:
                path = Path(temporary) / name
                path.write_bytes(gzip.compress(raw, mtime=0))
                self._gh("release", "create", tag, str(path), "--repo", self.repository,
                         "--target", self.target, "--prerelease", "--latest=false",
                         "--title", f"Daily research snapshot {research.as_of.date()}", "--notes",
                         "Source-linked SEC facts with explicit coverage. Experimental scores; "
                         "not historical model validation or permission to send alerts.")
            existing = json.loads(self._gh("api", f"repos/{self.repository}/releases/tags/{tag}"))
        self._verify(existing, name=name, digest=digest, expected=research)
        return {"tag": tag, "sha256": digest, "storageStatus": "VERIFIED", "runId": research.run_id,
                "url": f"https://github.com/{self.repository}/releases/tag/{tag}"}

    def _verify(self, release: dict[str, Any], *, name: str, digest: str,
                expected: ResearchSnapshot) -> None:
        assets = release["assets"]
        if (release["draft"] or not release["prerelease"] or len(assets) != 1
                or assets[0]["name"] != name or assets[0]["state"] != "uploaded"
                or not 0 < assets[0]["size"] <= MAX_SNAPSHOT_BYTES):
            raise ValueError("incomplete research archive")
        with tempfile.TemporaryDirectory(prefix="ite-research-readback-") as temporary:
            self._gh("release", "download", release["tag_name"], "--repo", self.repository,
                     "--pattern", name, "--dir", temporary)
            path = Path(temporary) / name
            if path.is_symlink() or path.stat().st_size != assets[0]["size"]:
                raise ValueError("research archive size mismatch")
            if decode_snapshot(path.read_bytes(), digest) != expected:
                raise ValueError("research archive readback mismatch")
