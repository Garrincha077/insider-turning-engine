"""Immutable, checksum-verified GitHub Release storage for SEC acquisition.

Every distinct checkpoint is a separate non-latest prerelease. No asset is
overwritten, and an interrupted upload never replaces a previous good version.
Authentication is inherited by gh from Actions/host configuration, never printed.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from .checkpoint import MAX_BYTES, decode_checkpoint, encode_checkpoint


class ReleaseCheckpointStore:
    def __init__(self, repository: str, *, target: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("invalid GitHub repository")
        if not re.fullmatch(r"[a-f0-9]{40}", target):
            raise ValueError("checkpoint release target must be a full commit SHA")
        self.repository = repository
        self.target = target
        self._inventory: list[dict[str, Any]] | None = None

    def _gh(self, *args: str) -> str:
        try:
            result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("GitHub checkpoint operation timed out") from exc
        if result.returncode:
            # Provider output can contain credential-bearing URLs or configuration.
            raise RuntimeError("GitHub checkpoint operation failed; previous releases preserved")
        return result.stdout

    def _releases(self) -> list[dict[str, Any]]:
        if self._inventory is None:
            pages = json.loads(self._gh(
                "api", f"repos/{self.repository}/releases?per_page=100", "--paginate", "--slurp",
            ))
            if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
                raise ValueError("invalid GitHub release inventory")
            self._inventory = [item for page in pages for item in page]
        return self._inventory

    @staticmethod
    def _prefix(day: date) -> str:
        # Bump this namespace if the portable checkpoint/parser contract changes.
        return f"sec-day-v1-{day.isoformat()}-"

    def _download(self, release: dict[str, Any], *, day: date) -> dict[str, Any]:
        tag = release["tag_name"]
        prefix = self._prefix(day)
        if not re.fullmatch(re.escape(prefix) + r"[a-f0-9]{64}", tag):
            raise ValueError("invalid checkpoint release tag")
        name = f"checkpoint-{tag.removeprefix(prefix)}.json.gz"
        assets = release["assets"]
        if (release["draft"] or not release["prerelease"] or len(assets) != 1
            or assets[0]["name"] != name or assets[0]["state"] != "uploaded"
            or not 0 < assets[0]["size"] <= MAX_BYTES):
            raise ValueError("incomplete or unexpected checkpoint release assets")
        with tempfile.TemporaryDirectory(prefix="ite-sec-download-") as temporary:
            self._gh("release", "download", tag, "--repo", self.repository,
                     "--pattern", name, "--dir", temporary)
            path = Path(temporary) / name
            if path.is_symlink() or path.stat().st_size != assets[0]["size"]:
                raise ValueError("downloaded checkpoint size mismatch")
            return decode_checkpoint(name, path.read_bytes(), day=day)

    def latest(self, day: date) -> dict[str, Any] | None:
        releases = [item for item in self._releases()
                    if item["tag_name"].startswith(self._prefix(day)) and not item["draft"]]
        if not releases:
            return None
        # Do not silently fall back from corrupt newest evidence to older progress.
        return self._download(max(releases, key=lambda item: int(item["id"])), day=day)

    def persist(self, checkpoint: dict[str, Any]) -> dict[str, str]:
        day = date.fromisoformat(checkpoint["day"])
        name, content = encode_checkpoint(checkpoint)
        digest = name.removeprefix("checkpoint-").removesuffix(".json.gz")
        tag = self._prefix(day) + digest
        existing = next((item for item in self._releases() if item["tag_name"] == tag), None)
        if existing is None:
            with tempfile.TemporaryDirectory(prefix="ite-sec-upload-") as temporary:
                path = Path(temporary) / name
                path.write_bytes(content)
                self._gh(
                    "release", "create", tag, str(path), "--repo", self.repository,
                    "--target", self.target, "--prerelease", "--latest=false",
                    "--title", f"SEC acquisition checkpoint {day}", "--notes",
                    "Normalized SEC acquisition evidence only. May be incomplete or quarantined. "
                    "Not signal history, a validated score or a production cursor commit.",
                )
            existing = json.loads(self._gh(
                "api", f"repos/{self.repository}/releases/tags/{tag}",
            ))
            if self._inventory is not None:
                self._inventory.append(existing)
        verified = self._download(existing, day=day)
        if encode_checkpoint(verified) != (name, content):
            raise ValueError("remote checkpoint differs from local acquisition")
        return {"tag": tag, "sha256": digest, "storageStatus": "VERIFIED",
                "url": f"https://github.com/{self.repository}/releases/tag/{tag}"}
