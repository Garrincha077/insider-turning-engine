"""Immutable public issuer-identity history, excluding raw SEC payloads and secrets."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from insider_turning_engine.pipeline.identity_observations import merge_observations

from .identity import COMPANY_TICKERS_EXCHANGE_URL
from .incremental import SEC_SUBMISSIONS_URL
from .release_store import ReleaseCheckpointStore

PREFIX = "sec-identity-v1-"
MAX_BYTES = 64 * 1024 * 1024
_FIELDS = {
    "schema_version", "source", "run_id", "cik", "knowledge_at", "ingested_at", "valid_from",
    "valid_to", "identity_status", "ticker", "current_mapping", "survivorship_caveat",
    "quality_flags", "provenance", "name", "exchange", "sic", "country", "sector_etf",
}
_PROVENANCE = {
    "exchange_url", "exchange_hash", "exchange_observed_at", "metadata_url", "metadata_hash",
    "metadata_observed_at", "sector_mapping_hash", "sector_mapping_version", "country_evidence",
    "exclusion_reasons",
}


def encode_identity_history(rows: list[dict[str, Any]]) -> tuple[str, bytes]:
    ordered = merge_observations(rows, [])
    for row in ordered:
        evidence = row.get("provenance")
        if (set(row) - _FIELDS or not isinstance(evidence, dict)
            or set(evidence) - _PROVENANCE
            or evidence.get("exchange_url") != COMPANY_TICKERS_EXCHANGE_URL
            or evidence.get("metadata_url") != SEC_SUBMISSIONS_URL.format(cik=row["cik"])):
            raise ValueError("identity history contains unexpected fields or source URLs")
        for key in ("exchange_hash", "metadata_hash", "sector_mapping_hash"):
            value = evidence.get(key)
            if value is None and key == "metadata_hash" and row["identity_status"] == "UNRESOLVED":
                continue
            if not isinstance(value, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", value):
                raise ValueError("identity source checksum missing or malformed")
    raw = json.dumps({"schemaVersion": "1.0.0", "observations": ordered},
                     sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError("identity history exceeds size limit; shard before continuing")
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as stream:
        stream.write(raw)
    content = buffer.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    return f"identities-{digest}.json.gz", content


def decode_identity_history(name: str, content: bytes) -> list[dict[str, Any]]:
    digest = hashlib.sha256(content).hexdigest()
    if len(content) > MAX_BYTES or name != f"identities-{digest}.json.gz":
        raise ValueError("identity archive checksum/size mismatch")
    with gzip.GzipFile(fileobj=io.BytesIO(content)) as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("expanded identity archive exceeds size limit")
    value = json.loads(raw)
    if (not isinstance(value, dict) or set(value) != {"schemaVersion", "observations"}
        or value["schemaVersion"] != "1.0.0" or not isinstance(value["observations"], list)
        or any(not isinstance(row, dict) for row in value["observations"])):
        raise ValueError("invalid identity archive contract")
    rows: list[dict[str, Any]] = value["observations"]
    if encode_identity_history(rows) != (name, content):
        raise ValueError("identity history is not canonical")
    return rows


class ReleaseIdentityStore:
    def __init__(self, repository: str, *, target: str) -> None:
        self.transport = ReleaseCheckpointStore(repository, target=target)

    def _download(self, release: dict[str, Any]) -> list[dict[str, Any]]:
        tag = release["tag_name"]
        if not re.fullmatch(PREFIX + r"[a-f0-9]{64}", tag):
            raise ValueError("invalid identity release tag")
        name = f"identities-{tag.removeprefix(PREFIX)}.json.gz"
        assets = release["assets"]
        if (release["draft"] or not release["prerelease"] or len(assets) != 1
            or assets[0]["name"] != name or assets[0]["state"] != "uploaded"
            or not 0 < assets[0]["size"] <= MAX_BYTES):
            raise ValueError("incomplete identity release")
        with tempfile.TemporaryDirectory(prefix="ite-identity-download-") as temporary:
            self.transport._gh("release", "download", tag, "--repo", self.transport.repository,
                               "--pattern", name, "--dir", temporary)
            path = Path(temporary) / name
            if path.is_symlink() or path.stat().st_size != assets[0]["size"]:
                raise ValueError("identity download size mismatch")
            return decode_identity_history(name, path.read_bytes())

    def latest(self) -> list[dict[str, Any]] | None:
        matches = [item for item in self.transport._releases()
                   if item["tag_name"].startswith(PREFIX) and not item["draft"]]
        return self._download(max(matches, key=lambda item: int(item["id"]))) if matches else None

    def persist(self, rows: list[dict[str, Any]]) -> dict[str, str]:
        self.transport._inventory = None
        previous = self.latest() or []
        combined = merge_observations(previous, rows)
        if merge_observations(rows, []) != combined:
            raise ValueError("identity publication would discard prior observations")
        name, content = encode_identity_history(rows)
        tag = PREFIX + hashlib.sha256(content).hexdigest()
        existing = next((item for item in self.transport._releases()
                         if item["tag_name"] == tag), None)
        if existing is None:
            with tempfile.TemporaryDirectory(prefix="ite-identity-upload-") as temporary:
                path = Path(temporary) / name
                path.write_bytes(content)
                self.transport._gh(
                    "release", "create", tag, str(path), "--repo", self.transport.repository,
                    "--target", self.transport.target, "--prerelease", "--latest=false",
                    "--title", "SEC point-in-time identity observations", "--notes",
                    "Public issuer metadata only; no raw/cache payloads or credentials. "
                    "Current observations, not historical identity or signal validation.",
                )
            existing = json.loads(self.transport._gh(
                "api", f"repos/{self.transport.repository}/releases/tags/{tag}",
            ))
            if self.transport._inventory is not None:
                self.transport._inventory.append(existing)
        if encode_identity_history(self._download(existing)) != (name, content):
            raise ValueError("remote identity evidence differs from local history")
        return {"storageStatus": "VERIFIED", "tag": tag,
                "url": f"https://github.com/{self.transport.repository}/releases/tag/{tag}"}
