"""Versioned, content-addressed inputs for the bounded daily run."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from insider_turning_engine.domain.time import us_equity_session_close

SCHEMA_VERSION = "1.0.0"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^run_[A-Za-z0-9_-]{8,64}$")
_REQUIRED_INPUTS = (
    "canonicalTransactions",
    "marketBars",
    "identities",
    "priorState",
    "qualityEvidence",
)
_OPTIONAL_INPUTS = ("secBatch", "backtestReport")


def _as_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} path must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or Path(value).drive:
        raise ValueError(f"{label} path must be relative to the manifest")
    if "\x00" in value:
        raise ValueError(f"{label} path contains a NUL byte")
    return value


@dataclass(frozen=True, slots=True)
class InputArtifact:
    """A manifest-relative file and its SHA-256 content address."""

    path: str
    sha256: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], label: str) -> InputArtifact:
        data = _as_mapping(value, label)
        unknown = set(data) - {"path", "sha256"}
        if unknown:
            raise ValueError(f"{label} has unknown fields: {sorted(unknown)}")
        path = _relative_path(data.get("path"), label)
        digest = data.get("sha256")
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise ValueError(f"{label} sha256 must match sha256:<64 lowercase hex>")
        return cls(path=path, sha256=digest)

    def as_mapping(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class DailyInputManifest:
    """Validated metadata and artifacts for one point-in-time daily run."""

    schema_version: str
    run_id: str
    as_of: datetime
    output_root: str
    inputs: dict[str, InputArtifact]
    manifest_path: Path

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        manifest_path: Path,
        verify_files: bool = True,
    ) -> DailyInputManifest:
        data = _as_mapping(value, "daily input manifest")
        required = {"schemaVersion", "runId", "asOf", "outputRoot", "inputs"}
        missing = required - set(data)
        if missing:
            raise ValueError(f"daily input manifest missing required fields: {sorted(missing)}")
        unknown = set(data) - required
        if unknown:
            raise ValueError(f"daily input manifest has unknown fields: {sorted(unknown)}")
        if data["schemaVersion"] != SCHEMA_VERSION:
            raise ValueError("daily input manifest schemaVersion must be 1.0.0")
        run_id = data["runId"]
        if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
            raise ValueError("daily input manifest runId must be a safe run_ identifier")
        raw_as_of = data["asOf"]
        if not isinstance(raw_as_of, str):
            raise ValueError("daily input manifest asOf must be an ISO timestamp")
        try:
            as_of = datetime.fromisoformat(raw_as_of.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("daily input manifest asOf must be an ISO timestamp") from exc
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("daily input manifest asOf must be timezone-aware")
        as_of_utc = as_of.astimezone(UTC)
        if as_of_utc != us_equity_session_close(as_of_utc.date()):
            raise ValueError("daily input manifest asOf must be 16:00 America/New_York")
        as_of = as_of_utc
        output_root_value = _relative_path(data["outputRoot"], "outputRoot")
        root_manifest = manifest_path.expanduser().resolve()
        root = root_manifest.parent
        output_root = (root / output_root_value).resolve(strict=False)
        try:
            output_root.relative_to(root)
        except ValueError as exc:
            raise ValueError("outputRoot escapes the manifest directory") from exc
        if output_root == root_manifest:
            raise ValueError("outputRoot must not be the manifest file")

        raw_inputs = _as_mapping(data["inputs"], "daily input manifest inputs")
        expected = set(_REQUIRED_INPUTS) | set(_OPTIONAL_INPUTS)
        missing_inputs = set(_REQUIRED_INPUTS) - set(raw_inputs)
        if missing_inputs:
            raise ValueError(f"daily input manifest missing inputs: {sorted(missing_inputs)}")
        unknown_inputs = set(raw_inputs) - expected
        if unknown_inputs:
            raise ValueError(f"daily input manifest has unknown inputs: {sorted(unknown_inputs)}")

        inputs: dict[str, InputArtifact] = {}
        resolved_paths: dict[str, str] = {}
        for name, raw_artifact in raw_inputs.items():
            artifact = InputArtifact.from_mapping(raw_artifact, f"inputs.{name}")
            resolved = (root / artifact.path).resolve(strict=False)
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"inputs.{name} path escapes the manifest directory") from exc
            identity = str(resolved).casefold() if os.name == "nt" else str(resolved)
            if identity in resolved_paths:
                other = resolved_paths[identity]
                raise ValueError(f"duplicate input path for {name} and {other}")
            resolved_paths[identity] = name
            overlaps = (
                output_root == resolved
                or output_root in resolved.parents
                or resolved in output_root.parents
            )
            if overlaps:
                raise ValueError(f"outputRoot overlaps input {name}")
            if verify_files:
                if not resolved.is_file():
                    raise ValueError(f"input file does not exist: {artifact.path}")
                digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
                if f"sha256:{digest}" != artifact.sha256:
                    raise ValueError(f"input hash mismatch: {artifact.path}")
            inputs[name] = artifact
        return cls(SCHEMA_VERSION, run_id, as_of, output_root_value, inputs, root_manifest)

    @classmethod
    def load(cls, path: Path, *, verify_files: bool = True) -> DailyInputManifest:
        manifest_path = path.expanduser().resolve()
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"daily input manifest is unreadable: {exc}") from exc
        return cls.from_mapping(value, manifest_path=manifest_path, verify_files=verify_files)

    def resolved_output_root(self) -> Path:
        return (self.manifest_path.parent / self.output_root).resolve(strict=False)

    def resolved_input(self, name: str) -> Path:
        return (self.manifest_path.parent / self.inputs[name].path).resolve(strict=False)

    def as_mapping(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "runId": self.run_id,
            "asOf": self.as_of.isoformat(),
            "outputRoot": self.output_root,
            "inputs": {name: artifact.as_mapping() for name, artifact in self.inputs.items()},
        }


def load_daily_input_manifest(path: Path, *, verify_files: bool = True) -> DailyInputManifest:
    """Load and validate a daily manifest without creating output directories."""

    return DailyInputManifest.load(path, verify_files=verify_files)


validate_daily_input_manifest = load_daily_input_manifest


__all__ = [
    "SCHEMA_VERSION",
    "InputArtifact",
    "DailyInputManifest",
    "load_daily_input_manifest",
    "validate_daily_input_manifest",
]
