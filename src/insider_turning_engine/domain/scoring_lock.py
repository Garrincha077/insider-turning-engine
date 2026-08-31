"""Dependency-free validation of the checked-in scoring v1 attestation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPOSITORY_ROOT / "config" / "scoring.v1.yaml"
DEFAULT_LOCK = REPOSITORY_ROOT / "config" / "scoring.v1.lock.json"


class ScoringLockError(ValueError):
    """Raised when the config and immutable lock do not agree exactly."""


@dataclass(frozen=True, slots=True)
class ScoringLock:
    score_version: str
    config_path: str
    config_hash: str
    lineage: str
    frozen_at: datetime
    frozen_at_iso: str
    source_commit: str


def load_scoring_lock(
    config_path: str | Path = DEFAULT_CONFIG,
    lock_path: str | Path = DEFAULT_LOCK,
    *,
    expected_score_version: str = "scoring.v1",
    config_lineage_path: str | None = None,
) -> ScoringLock:
    """Return a validated lock bound to the exact config bytes."""

    config = Path(config_path)
    lock = Path(lock_path)
    lineage_path = config_lineage_path
    if lineage_path is None:
        try:
            lineage_path = config.resolve().relative_to(REPOSITORY_ROOT).as_posix()
        except ValueError:
            lineage_path = config.name
    config_hash = "sha256:" + hashlib.sha256(config.read_bytes()).hexdigest()
    lineage = f"{lineage_path}@{config_hash}"
    try:
        raw = json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScoringLockError(f"scoring lock is unreadable: {lock}") from exc
    required = {
        "schemaVersion",
        "scoreVersion",
        "scoreConfig",
        "scoreConfigHash",
        "scoreLineage",
        "frozenAt",
        "sourceCommit",
    }
    if not isinstance(raw, Mapping) or set(raw) != required:
        raise ScoringLockError("scoring lock fields do not match the v1 contract")
    if raw["schemaVersion"] != "1.0.0" or raw["scoreVersion"] != expected_score_version:
        raise ScoringLockError("scoring lock schema/version does not match scoring.v1")
    if raw["scoreConfig"] != lineage_path:
        raise ScoringLockError("scoring lock config path does not match the loaded config")
    if raw["scoreConfigHash"] != config_hash:
        raise ScoringLockError("scoring lock hash does not match the loaded config bytes")
    if raw["scoreLineage"] != lineage:
        raise ScoringLockError("scoring lock lineage does not match the loaded config")
    frozen_raw = raw["frozenAt"]
    if not isinstance(frozen_raw, str) or not frozen_raw.endswith("Z"):
        raise ScoringLockError("scoring lock frozenAt must be a canonical UTC timestamp")
    try:
        frozen_at = datetime.fromisoformat(frozen_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScoringLockError("scoring lock frozenAt is invalid") from exc
    if (
        frozen_at.tzinfo is None
        or frozen_at.astimezone(UTC).isoformat().replace("+00:00", "Z") != frozen_raw
    ):
        raise ScoringLockError("scoring lock frozenAt must be a canonical UTC timestamp")
    source_commit = raw["sourceCommit"]
    if not isinstance(source_commit, str) or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ScoringLockError("scoring lock sourceCommit must be a full Git commit hash")
    return ScoringLock(
        score_version=expected_score_version,
        config_path=lineage_path,
        config_hash=config_hash,
        lineage=lineage,
        frozen_at=frozen_at.astimezone(UTC),
        frozen_at_iso=frozen_raw,
        source_commit=source_commit,
    )


__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_LOCK",
    "ScoringLock",
    "ScoringLockError",
    "load_scoring_lock",
]
