import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from insider_turning_engine.domain.daily_manifest import load_daily_input_manifest


def _manifest(tmp_path: Path, *, overrides: dict | None = None) -> Path:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    names = ["canonical.json", "market.json", "identities.json", "state.json", "quality.json"]
    artifacts = {}
    for key, name in zip(
        ("canonicalTransactions", "marketBars", "identities", "priorState", "qualityEvidence"),
        names,
        strict=True,
    ):
        path = input_dir / name
        path.write_text(key, encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        artifacts[key] = {"path": str(path.relative_to(tmp_path)), "sha256": f"sha256:{digest}"}
    payload = {
        "schemaVersion": "1.0.0",
        "runId": "run_daily_manifest_test",
        "asOf": "2026-08-31T20:00:00+00:00",
        "outputRoot": "output",
        "inputs": artifacts,
    }
    if overrides:
        payload.update(overrides)
    manifest = tmp_path / "daily.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    return manifest


def test_manifest_loads_and_normalizes_as_of_without_creating_output(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    result = load_daily_input_manifest(manifest_path)
    assert result.as_of == datetime(2026, 8, 31, 20, tzinfo=UTC)
    assert result.resolved_output_root() == (tmp_path / "output").resolve()
    assert not (tmp_path / "output").exists()


def test_manifest_rejects_hash_mismatch_before_output_mutation(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    target = tmp_path / "inputs" / "market.json"
    target.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_daily_input_manifest(manifest_path)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    ("path", "message"),
    [("../escape.json", "escapes"), ("inputs/./canonical.json", "duplicate")],
)
def test_manifest_rejects_traversal_and_duplicate_resolved_paths(
    tmp_path: Path, path: str, message: str
) -> None:
    manifest_path = _manifest(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if message == "escapes":
        payload["inputs"]["marketBars"]["path"] = path
    else:
        payload["inputs"]["marketBars"]["path"] = path
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_daily_input_manifest(manifest_path, verify_files=False)


def test_manifest_rejects_output_root_overlapping_input(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path, overrides={"outputRoot": "inputs"})
    with pytest.raises(ValueError, match="overlaps"):
        load_daily_input_manifest(manifest_path, verify_files=False)


def test_manifest_rejects_output_escape_and_non_close_timestamp(tmp_path: Path) -> None:
    escaped = _manifest(tmp_path, overrides={"outputRoot": "../escape"})
    with pytest.raises(ValueError, match="outputRoot escapes"):
        load_daily_input_manifest(escaped, verify_files=False)

    off_close_root = tmp_path / "off-close"
    off_close_root.mkdir()
    off_close = _manifest(
        off_close_root,
        overrides={"asOf": "2026-08-31T19:59:59Z"},
    )
    with pytest.raises(ValueError, match="16:00 America/New_York"):
        load_daily_input_manifest(off_close, verify_files=False)
