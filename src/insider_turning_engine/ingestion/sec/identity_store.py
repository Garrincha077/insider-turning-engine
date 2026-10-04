"""Immutable public issuer-identity history, excluding raw SEC payloads and secrets."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from insider_turning_engine.normalization.identity import _EXCLUDED_TEXT
from insider_turning_engine.pipeline.identity_observations import (
    _COMMON,
    merge_observations,
)

from .identity import COMPANY_TICKERS_EXCHANGE_URL
from .incremental import SEC_SUBMISSIONS_URL
from .release_store import ReleaseCheckpointStore

PREFIX = "sec-identity-v1-"
SHARDED_PREFIX = "sec-identity-v2-"
MAX_BYTES = 64 * 1024 * 1024
CHUNK_TARGET_BYTES = 8 * 1024 * 1024
MAX_SHARDS = 256
MAX_MANIFEST_BYTES = 128 * 1024
MAX_BUNDLE_BYTES = 1024 * 1024 * 1024
_FIELDS = {
    "schema_version", "source", "run_id", "cik", "knowledge_at", "ingested_at", "valid_from",
    "valid_to", "identity_status", "ticker", "current_mapping", "survivorship_caveat",
    "quality_flags", "provenance", "name", "exchange", "sic", "country", "sector_etf",
}
_PROVENANCE = {
    "exchange_url", "exchange_hash", "exchange_observed_at", "metadata_url", "metadata_hash",
    "metadata_observed_at", "sector_mapping_hash", "sector_mapping_version", "country_evidence",
    "exclusion_reasons", "common_stock_listing_evidence",
}


def _validate_listing_proof(row: dict[str, Any], proof: Any) -> None:
    """Allow only bounded public SEC corroboration, never arbitrary nested data."""
    keys = {"issuer_cik", "ticker", "accession", "source_url", "source_hash",
            "accepted_at", "knowledge_at", "security_title"}
    if (not isinstance(proof, dict) or set(proof) != keys
        or any(not isinstance(value, str) for value in proof.values())
        or proof["issuer_cik"] != row["cik"]
        or not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}", proof["ticker"])
        or (row["ticker"] is not None and proof["ticker"] != row["ticker"])
        or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", proof["accession"])
        or not re.fullmatch(r"sha256:[a-f0-9]{64}", proof["source_hash"])
        or not 0 < len(proof["security_title"]) <= 500
        or not _COMMON.search(proof["security_title"])
        or _EXCLUDED_TEXT.search(proof["security_title"])):
        raise ValueError("invalid common-stock listing proof")
    url = urlparse(proof["source_url"])
    if (len(proof["source_url"]) > 2000 or url.scheme != "https" or url.netloc != "www.sec.gov"
        or not url.path.startswith("/Archives/edgar/data/") or url.query or url.fragment):
        raise ValueError("invalid listing proof source URL")
    known = datetime.fromisoformat(proof["knowledge_at"])
    accepted = datetime.fromisoformat(proof["accepted_at"])
    observed = datetime.fromisoformat(row["knowledge_at"])
    if (known.tzinfo is None or accepted.tzinfo is None or not accepted <= known <= observed
        or accepted < observed - timedelta(days=365)):
        raise ValueError("invalid listing proof availability timestamp")


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
        has_proof = "common_stock_listing_evidence" in evidence
        if has_proof != ("COMMON_STOCK_LISTING_CONFIRMED" in row["quality_flags"]):
            raise ValueError("listing proof flag/evidence mismatch")
        if has_proof:
            _validate_listing_proof(row, evidence["common_stock_listing_evidence"])
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


def encode_identity_bundle(rows: list[dict[str, Any]]) -> tuple[str, dict[str, bytes]]:
    """Deterministic bounded chunks; never truncate or retime identity history."""
    ordered = merge_observations(rows, [])
    if not ordered:
        name, content = encode_identity_history([])
        return PREFIX + hashlib.sha256(content).hexdigest(), {name: content}
    buckets: dict[int, list[dict[str, Any]]] = {}
    for row in ordered:
        buckets.setdefault(int(row["cik"]) % 16, []).append(row)
    files: dict[str, bytes] = {}
    shards = []
    expanded_total = 0
    for bucket, members in sorted(buckets.items()):
        parts: list[list[dict[str, Any]]] = [[]]
        size = 0
        for row in members:
            row_size = len(json.dumps(row, sort_keys=True, separators=(",", ":"),
                                      allow_nan=False).encode()) + 1
            if parts[-1] and size + row_size > CHUNK_TARGET_BYTES:
                parts.append([])
                size = 0
            parts[-1].append(row)
            size += row_size
        for part, records in enumerate(parts):
            name, content = encode_identity_history(records)
            expanded = len(gzip.decompress(content))
            expanded_total += expanded
            files[name] = content
            shards.append({"bucket": bucket, "part": part, "file": name,
                           "sha256": hashlib.sha256(content).hexdigest(),
                           "byteLength": len(content), "expandedBytes": expanded,
                           "observationCount": len(records)})
    if (not files or len(shards) > MAX_SHARDS or expanded_total > MAX_BUNDLE_BYTES
        or len(files) != len(shards)):
        raise ValueError("identity bundle exceeds bounded shard inventory")
    if len(files) == 1:
        name, content = next(iter(files.items()))
        return PREFIX + hashlib.sha256(content).hexdigest(), {name: content}
    manifest = json.dumps({"schemaVersion": "2.0.0", "sharding": "cik-modulo-16",
                           "chunkTargetBytes": CHUNK_TARGET_BYTES,
                           "observationCount": len(ordered), "expandedBytes": expanded_total,
                           "shards": shards}, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode()
    if len(manifest) > MAX_MANIFEST_BYTES:
        raise ValueError("identity shard manifest exceeds size limit")
    digest = hashlib.sha256(manifest).hexdigest()
    files[f"identity-manifest-{digest}.json"] = manifest
    return SHARDED_PREFIX + digest, files


def decode_identity_bundle(tag: str, files: dict[str, bytes]) -> list[dict[str, Any]]:
    if not re.fullmatch(SHARDED_PREFIX + r"[a-f0-9]{64}", tag):
        raise ValueError("invalid sharded identity release tag")
    name = f"identity-manifest-{tag.removeprefix(SHARDED_PREFIX)}.json"
    raw = files.get(name, b"")
    if (not 0 < len(raw) <= MAX_MANIFEST_BYTES
        or hashlib.sha256(raw).hexdigest() != tag.removeprefix(SHARDED_PREFIX)):
        raise ValueError("identity manifest checksum/size mismatch")
    manifest = json.loads(raw)
    if (not isinstance(manifest, dict) or manifest.get("schemaVersion") != "2.0.0"
        or manifest.get("sharding") != "cik-modulo-16"
        or not isinstance(manifest.get("shards"), list)
        or not 1 <= len(manifest["shards"]) <= MAX_SHARDS):
        raise ValueError("invalid identity shard manifest")
    rows = []
    expected = {name}
    expanded_total = 0
    for shard in manifest["shards"]:
        if (not isinstance(shard, dict)
            or set(shard) != {"bucket", "part", "file", "sha256", "byteLength",
                              "expandedBytes", "observationCount"}
            or type(shard["bucket"]) is not int or not 0 <= shard["bucket"] < 16
            or type(shard["part"]) is not int or shard["part"] < 0
            or any(type(shard[field]) is not int or shard[field] <= 0
                   for field in ("byteLength", "expandedBytes", "observationCount"))
            or not isinstance(shard["file"], str)
            or not re.fullmatch(r"identities-[a-f0-9]{64}\.json\.gz", shard["file"])
            or shard["file"] in expected
            or shard["expandedBytes"] > MAX_BYTES):
            raise ValueError("invalid identity shard inventory")
        expected.add(shard["file"])
        expanded_total += shard["expandedBytes"]
        if expanded_total > MAX_BUNDLE_BYTES:
            raise ValueError("expanded identity bundle exceeds size limit")
        content = files.get(shard["file"], b"")
        if (len(content) != shard["byteLength"]
            or hashlib.sha256(content).hexdigest() != shard["sha256"]):
            raise ValueError("identity shard checksum/size mismatch")
        decoded = decode_identity_history(shard["file"], content)
        actual_expanded = len(json.dumps({"schemaVersion": "1.0.0", "observations": decoded},
                                        sort_keys=True, separators=(",", ":"),
                                        allow_nan=False).encode())
        if (len(decoded) != shard["observationCount"]
            or actual_expanded != shard["expandedBytes"]
            or any(int(row["cik"]) % 16 != shard["bucket"] for row in decoded)):
            raise ValueError("identity shard issuer/row inventory mismatch")
        rows.extend(decoded)
    if set(files) != expected or encode_identity_bundle(rows) != (tag, files):
        raise ValueError("identity bundle is not canonical or has extra/missing assets")
    return merge_observations(rows, [])


class ReleaseIdentityStore:
    def __init__(self, repository: str, *, target: str) -> None:
        self.transport = ReleaseCheckpointStore(repository, target=target)

    def _download(self, release: dict[str, Any], *, allow_draft: bool = False,
                  ) -> list[dict[str, Any]]:
        tag = release["tag_name"]
        if tag.startswith(SHARDED_PREFIX):
            return self._download_sharded(release, allow_draft=allow_draft)
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

    def _download_sharded(self, release: dict[str, Any], *, allow_draft: bool,
                          ) -> list[dict[str, Any]]:
        tag, assets = release["tag_name"], release["assets"]
        if (not re.fullmatch(SHARDED_PREFIX + r"[a-f0-9]{64}", tag)
            or (release["draft"] and not allow_draft) or not release["prerelease"]
            or not 2 <= len(assets) <= MAX_SHARDS + 1):
            raise ValueError("incomplete sharded identity release")
        manifest_name = f"identity-manifest-{tag.removeprefix(SHARDED_PREFIX)}.json"
        inventory: dict[str, int] = {}
        for asset in assets:
            name = asset["name"]
            limit = MAX_MANIFEST_BYTES if name == manifest_name else MAX_BYTES
            if (name in inventory or asset["state"] != "uploaded"
                or not 0 < asset["size"] <= limit
                or (name != manifest_name
                    and not re.fullmatch(r"identities-[a-f0-9]{64}\.json\.gz", name))):
                raise ValueError("invalid identity release asset inventory")
            inventory[name] = asset["size"]
        if manifest_name not in inventory or sum(inventory.values()) > MAX_BUNDLE_BYTES:
            raise ValueError("identity release asset budget exceeded")
        with tempfile.TemporaryDirectory(prefix="ite-identity-shards-") as temporary:
            self.transport._gh("release", "download", tag, "--repo", self.transport.repository,
                               "--dir", temporary)
            files = {}
            for name, size in inventory.items():
                path = Path(temporary) / name
                if path.is_symlink() or path.stat().st_size != size:
                    raise ValueError("identity download size mismatch")
                files[name] = path.read_bytes()
            return decode_identity_bundle(tag, files)

    def latest(self) -> list[dict[str, Any]] | None:
        matches = [item for item in self.transport._releases()
                   if item["tag_name"].startswith((PREFIX, SHARDED_PREFIX)) and not item["draft"]]
        return self._download(max(matches, key=lambda item: (
            item["tag_name"].startswith(SHARDED_PREFIX), int(item["id"])))) if matches else None

    def persist(self, rows: list[dict[str, Any]]) -> dict[str, str]:
        self.transport._inventory = None
        previous = self.latest() or []
        combined = merge_observations(previous, rows)
        if merge_observations(rows, []) != combined:
            raise ValueError("identity publication would discard prior observations")
        tag, files = encode_identity_bundle(rows)
        existing = next((item for item in self.transport._releases()
                         if item["tag_name"] == tag), None)
        sharded = tag.startswith(SHARDED_PREFIX)
        if existing is None:
            with tempfile.TemporaryDirectory(prefix="ite-identity-upload-") as temporary:
                for name, content in files.items():
                    (Path(temporary) / name).write_bytes(content)
                first = next(name for name in files if name.startswith("identity-manifest-")) \
                    if sharded else next(iter(files))
                self.transport._gh(
                    "release", "create", tag, str(Path(temporary) / first),
                    *(("--draft",) if sharded else ()), "--repo", self.transport.repository,
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
        if sharded and existing["draft"]:
            present = {asset["name"] for asset in existing["assets"]}
            if not present <= set(files):
                raise ValueError("identity draft contains unexpected assets")
            missing = sorted(set(files) - present)
            with tempfile.TemporaryDirectory(prefix="ite-identity-parts-") as temporary:
                for name in missing:
                    (Path(temporary) / name).write_bytes(files[name])
                for index in range(0, len(missing), 16):
                    self.transport._gh("release", "upload", tag,
                                       *(str(Path(temporary) / name)
                                         for name in missing[index:index + 16]),
                                       "--repo", self.transport.repository)
            existing = json.loads(self.transport._gh(
                "api", f"repos/{self.transport.repository}/releases/tags/{tag}"))
            if encode_identity_bundle(self._download(existing, allow_draft=True)) != (tag, files):
                raise ValueError("remote identity draft differs from local history")
            self.transport._gh("release", "edit", tag, "--draft=false",
                               "--repo", self.transport.repository)
            existing = json.loads(self.transport._gh(
                "api", f"repos/{self.transport.repository}/releases/tags/{tag}"))
        if encode_identity_bundle(self._download(existing)) != (tag, files):
            raise ValueError("remote identity evidence differs from local history")
        self.transport._inventory = None  # A draft's cached inventory is no longer authoritative.
        return {"storageStatus": "VERIFIED", "tag": tag,
                "url": f"https://github.com/{self.transport.repository}/releases/tag/{tag}"}
