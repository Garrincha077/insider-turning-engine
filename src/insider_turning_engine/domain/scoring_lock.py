"""Validation for the checked-in scoring methodology lock.

The lock is a content attestation, not a Git-history attestation. It binds
the scoring configuration and every explicit methodology source by its exact
repository-relative path and SHA-256 digest.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPOSITORY_ROOT / "config" / "scoring.v1.yaml"
DEFAULT_LOCK = REPOSITORY_ROOT / "config" / "scoring.v1.lock.json"
_HASH_PREFIX = "sha256:"
_SCHEMA_VERSION = "1.1.0"


class ScoringLockError(ValueError):
    """Raised when the config and methodology lock do not agree exactly."""


class ScoringLockStatus(StrEnum):
    """Lifecycle state for a scoring methodology lock."""

    CANDIDATE = "CANDIDATE"
    FROZEN = "FROZEN"


@dataclass(frozen=True, slots=True)
class MethodologyFile:
    """One source file covered by the methodology attestation."""

    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ScoringLock:
    """Validated scoring methodology attestation.

    ``methodology_complete`` is deliberately computed from validated lock
    state. It is never accepted as an input claim.
    """

    score_version: str
    status: ScoringLockStatus
    config_path: str
    config_hash: str
    lineage: str
    methodology_files: tuple[MethodologyFile, ...]
    methodology_hash: str
    component_contract_complete: bool
    frozen_at: datetime | None
    frozen_at_iso: str | None

    @property
    def methodology_complete(self) -> bool:
        """Whether this is a complete, frozen, exact methodology attestation."""

        return self.status is ScoringLockStatus.FROZEN and self.component_contract_complete

    @property
    def source_commit(self) -> str:
        """Deprecated compatibility shim; source commits are not lock evidence."""

        return ""


def _sha256(path: Path) -> str:
    return _HASH_PREFIX + hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_relative_path(path: Path, *, field: str) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ScoringLockError(f"{field} must be inside the repository") from exc


def _resolve_repo_file(raw_path: Any, *, field: str) -> tuple[Path, str]:
    if not isinstance(raw_path, str) or not raw_path:
        raise ScoringLockError(f"{field} path must be a non-empty string")
    candidate = Path(raw_path)
    if candidate.is_absolute() or "\\" in raw_path:
        raise ScoringLockError(f"{field} path must be repository-relative POSIX")
    resolved = (REPOSITORY_ROOT / candidate).resolve()
    normalized = _repo_relative_path(resolved, field=field)
    if normalized != raw_path:
        raise ScoringLockError(f"{field} path must be canonical repository-relative POSIX")
    if not resolved.is_file():
        raise ScoringLockError(f"{field} source file is missing: {raw_path}")
    return resolved, normalized


def _methodology_digest(files: Sequence[MethodologyFile]) -> str:
    """Hash canonical ordered methodology descriptors, not incidental JSON layout."""

    payload = json.dumps(
        [{"path": item.path, "sha256": item.sha256} for item in files],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    return _HASH_PREFIX + hashlib.sha256(payload).hexdigest()


def _parse_canonical_utc(value: Any) -> tuple[datetime, str]:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ScoringLockError("scoring lock frozenAt must be a canonical UTC timestamp")
    try:
        frozen_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScoringLockError("scoring lock frozenAt is invalid") from exc
    if (
        frozen_at.tzinfo is None
        or frozen_at.astimezone(UTC).isoformat().replace("+00:00", "Z") != value
    ):
        raise ScoringLockError("scoring lock frozenAt must be a canonical UTC timestamp")
    return frozen_at.astimezone(UTC), value


def load_scoring_lock(
    config_path: str | Path = DEFAULT_CONFIG,
    lock_path: str | Path = DEFAULT_LOCK,
    *,
    expected_score_version: str = "scoring.v1",
    config_lineage_path: str | None = None,
) -> ScoringLock:
    """Return an exact, content-validated scoring methodology lock."""

    config = Path(config_path)
    lock = Path(lock_path)
    try:
        config_resolved = config.resolve(strict=True)
    except OSError as exc:
        raise ScoringLockError(f"scoring config is unreadable: {config}") from exc
    try:
        lineage_path = _repo_relative_path(config_resolved, field="scoreConfig")
    except ScoringLockError:
        # A caller may use a temporary config, but cannot lie about its
        # deterministic filename lineage through the compatibility argument.
        lineage_path = config_resolved.name
    if config_lineage_path is not None and config_lineage_path != lineage_path:
        raise ScoringLockError("scoring lock config path does not match the loaded config")
    if not lineage_path:
        raise ScoringLockError("scoring lock config path must be a non-empty string")
    config_hash = _sha256(config_resolved)
    lineage = f"{lineage_path}@{config_hash}"
    try:
        raw = json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScoringLockError(f"scoring lock is unreadable: {lock}") from exc
    if not isinstance(raw, Mapping):
        raise ScoringLockError("scoring lock must be a JSON object")

    required = {
        "schemaVersion",
        "scoreVersion",
        "status",
        "scoreConfig",
        "scoreConfigHash",
        "methodologyFiles",
        "methodologyHash",
        "componentContractComplete",
    }
    optional = {"frozenAt"}
    if set(raw).difference(required | optional) or not required.issubset(raw):
        raise ScoringLockError("scoring lock fields do not match the v1.1 contract")
    if raw["schemaVersion"] != _SCHEMA_VERSION or raw["scoreVersion"] != expected_score_version:
        raise ScoringLockError("scoring lock schema/version does not match scoring.v1")
    try:
        status = ScoringLockStatus(raw["status"])
    except (TypeError, ValueError) as exc:
        raise ScoringLockError("scoring lock status must be CANDIDATE or FROZEN") from exc
    if raw["scoreConfig"] != lineage_path:
        raise ScoringLockError("scoring lock config path does not match the loaded config")
    if raw["scoreConfigHash"] != config_hash:
        raise ScoringLockError("scoring lock hash does not match the loaded config bytes")
    if not isinstance(raw["componentContractComplete"], bool):
        raise ScoringLockError("scoring lock componentContractComplete must be boolean")

    methodology_raw = raw["methodologyFiles"]
    if not isinstance(methodology_raw, list) or not methodology_raw:
        raise ScoringLockError("scoring lock methodologyFiles must be a non-empty list")
    lock_resolved = lock.resolve()
    methodology_files: list[MethodologyFile] = []
    for index, item in enumerate(methodology_raw):
        field = f"methodologyFiles[{index}]"
        if not isinstance(item, Mapping) or set(item) != {"path", "sha256"}:
            raise ScoringLockError(f"{field} must contain only path and sha256")
        source, source_path = _resolve_repo_file(item["path"], field=field)
        if source == lock_resolved:
            raise ScoringLockError("the scoring lock cannot attest to itself")
        expected_hash = item["sha256"]
        if not isinstance(expected_hash, str) or not expected_hash.startswith(_HASH_PREFIX):
            raise ScoringLockError(f"{field} sha256 must be a sha256 digest")
        if _sha256(source) != expected_hash:
            raise ScoringLockError(f"{field} hash does not match source bytes: {source_path}")
        methodology_files.append(MethodologyFile(source_path, expected_hash))
    if tuple(item.path for item in methodology_files) != tuple(
        sorted(item.path for item in methodology_files)
    ) or len({item.path for item in methodology_files}) != len(methodology_files):
        raise ScoringLockError("scoring lock methodologyFiles must be unique and path-sorted")
    methodology_files_tuple = tuple(methodology_files)
    expected_methodology_hash = _methodology_digest(methodology_files_tuple)
    if raw["methodologyHash"] != expected_methodology_hash:
        raise ScoringLockError("scoring lock methodologyHash does not match methodologyFiles")

    frozen_at: datetime | None = None
    frozen_at_iso: str | None = None
    if status is ScoringLockStatus.FROZEN:
        if "frozenAt" not in raw:
            raise ScoringLockError("a FROZEN scoring lock requires frozenAt")
        frozen_at, frozen_at_iso = _parse_canonical_utc(raw["frozenAt"])
    elif "frozenAt" in raw:
        raise ScoringLockError("a CANDIDATE scoring lock must not include frozenAt")

    return ScoringLock(
        score_version=expected_score_version,
        status=status,
        config_path=lineage_path,
        config_hash=config_hash,
        lineage=lineage,
        methodology_files=methodology_files_tuple,
        methodology_hash=expected_methodology_hash,
        component_contract_complete=raw["componentContractComplete"],
        frozen_at=frozen_at,
        frozen_at_iso=frozen_at_iso,
    )


__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_LOCK",
    "MethodologyFile",
    "ScoringLock",
    "ScoringLockError",
    "ScoringLockStatus",
    "load_scoring_lock",
]
