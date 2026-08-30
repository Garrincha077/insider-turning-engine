"""Deterministic, all-or-nothing publication of dashboard data.

The web application deliberately consumes a small JSON projection rather than
the engine's canonical transaction or signal stores.  This module keeps that
boundary explicit: callers may provide ordinary mappings or Polars data
frames, while the published directory contains only validated dashboard
artifacts and their content-addressed manifest.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast


class DashboardExportError(ValueError):
    """Raised when a dashboard projection cannot be published safely."""


@dataclass(frozen=True)
class DashboardExport:
    """Paths and manifest returned after a successful publication."""

    output_dir: Path
    dashboard_path: Path
    manifest_path: Path
    manifest: Mapping[str, Any]


_DASHBOARD_KEYS = (
    "schemaVersion",
    "scoreVersion",
    "generatedAt",
    "status",
    "marketPulse",
    "pulsePercentile",
    "pulseHistory",
    "candidates",
    "filings",
    "backtest",
    "companySeries",
)
_ROW_KEYS: dict[str, tuple[str, ...]] = {
    "pulseHistory": ("date", "market", "technology", "financials"),
    "candidates": (
        "ticker",
        "issuerCik",
        "company",
        "sector",
        "total",
        "insider",
        "divergence",
        "turn",
        "cluster",
        "marketRs",
        "sectorRs",
        "insiderCost",
        "currentPrice",
        "state",
        "reasons",
    ),
    "filings": ("ticker", "owner", "role", "side", "value", "filedAt", "accession"),
    "backtest": ("horizon", "fullEngine", "clusterBuy", "simpleRatio"),
    "companySeries": ("date", "price", "cost", "mansfield"),
}
_OPTIONAL_ROW_KEYS = {"sourceReferences", "sourceReference", "reasonCodes"}
_STATE_NAMES = {"FALLING", "INSIDER_ACCUMULATION", "BASE_FORMING", "EARLY_TURN", "CONFIRMED_TURN"}
_DASHBOARD_STATUSES = {"VALIDATED", "EXPERIMENTAL", "STALE"}


def export_dashboard(
    data: Mapping[str, Any] | Any,
    output_dir: str | os.PathLike[str] | Mapping[str, Any] | None = None,
    *,
    run_id: str | None = None,
    generated_at: str | datetime | None = None,
    as_of: str | datetime | None = None,
    score_version: str = "scoring.v1",
    status: str = "EXPERIMENTAL",
    chunk_by_ticker: bool = False,
    per_ticker: bool | None = None,
) -> DashboardExport:
    """Validate and atomically publish ``dashboard.json`` and its manifest.

    ``data`` is a mapping whose table values may be sequences of mappings or
    Polars ``DataFrame`` instances.  For convenience, callers using the
    conventional ``export_dashboard(output_dir, data)`` ordering are accepted
    as well.  The output directory is replaced only after every staged file
    and its manifest have been validated and flushed to disk.
    """

    if isinstance(data, (str, os.PathLike)) and isinstance(output_dir, Mapping):
        data, output_dir = output_dir, data
    if not isinstance(data, Mapping):
        raise DashboardExportError("dashboard input must be a mapping")
    if output_dir is None or isinstance(output_dir, Mapping):
        raise DashboardExportError("output_dir is required")
    destination = Path(output_dir)
    if per_ticker is not None:
        chunk_by_ticker = per_ticker

    dashboard = _make_dashboard(data, score_version, generated_at, status)
    _validate_dashboard(dashboard)
    dashboard_bytes = _canonical_bytes(dashboard)
    generated = dashboard["generatedAt"]
    as_of_text = _instant(as_of if as_of is not None else generated)
    publication_run_id = run_id or f"run_{hashlib.sha256(dashboard_bytes).hexdigest()[:32]}"
    _validate_identifier(publication_run_id, "run_id", "run_")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    try:
        _write_bytes(temporary / "dashboard.json", dashboard_bytes)
        files: list[dict[str, Any]] = [_file_record(temporary, "dashboard.json")]

        if chunk_by_ticker:
            tickers = sorted(
                {str(row["ticker"]) for row in dashboard["candidates"] if row["ticker"]}
            )
            for ticker in tickers:
                chunk = next(row for row in dashboard["candidates"] if row["ticker"] == ticker)
                rel = Path("tickers") / f"{_safe_filename(ticker)}.json"
                _write_bytes(temporary / rel, _canonical_bytes(chunk))
                files.append(_file_record(temporary, rel.as_posix()))

        signal_files, signal_refs = _write_signal_snapshots(temporary, data)
        files.extend(signal_files)
        artifacts = [
            {
                "kind": "SIGNAL_INDEX",
                "uri": record["path"],
                "contentHash": f"sha256:{record['sha256']}",
                "mediaType": "application/json",
            }
            for record in files
            if record["path"] == "dashboard.json" or record["path"].startswith("signals/")
        ]
        manifest = _make_manifest(
            data,
            dashboard,
            publication_run_id,
            as_of_text,
            signal_refs,
            artifacts,
            files,
        )
        _validate_manifest(manifest)
        _write_bytes(temporary / "manifest.json", _canonical_bytes(manifest))
        _replace_directory(temporary, destination)
        temporary = Path()
    finally:
        if temporary != Path() and temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
    return DashboardExport(
        destination,
        destination / "dashboard.json",
        destination / "manifest.json",
        manifest,
    )


def _make_dashboard(
    data: Mapping[str, Any], score_version: str, generated_at: str | datetime | None, status: str
) -> dict[str, Any]:
    generated = _instant(generated_at or "1970-01-01T00:00:00Z")
    value: dict[str, Any] = {
        "schemaVersion": str(data.get("schemaVersion", "1.0.0")),
        "scoreVersion": str(data.get("scoreVersion", score_version)),
        "generatedAt": str(data.get("generatedAt", generated)),
        "status": str(data.get("status", status)),
    }
    for key in ("marketPulse", "pulsePercentile"):
        if key not in data:
            raise DashboardExportError(f"missing required dashboard field: {key}")
        value[key] = data[key]
    for key in ("pulseHistory", "candidates", "filings", "backtest", "companySeries"):
        value[key] = _rows(data.get(key, []), key)
    return cast(dict[str, Any], _json_ready(value))


def _rows(value: Any, field: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if hasattr(value, "to_dicts"):
        value = value.to_dicts()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise DashboardExportError(f"{field} must be a sequence of mappings or a Polars DataFrame")
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise DashboardExportError(f"{field} contains a non-mapping row")
        row = dict(item)
        row = _aliases(row, field)
        rows.append(row)
    if field == "candidates":
        rows.sort(
            key=lambda row: (
                -float(row.get("total", 0)),
                str(row.get("ticker", "")),
            )
        )
    elif field == "filings":
        rows.sort(
            key=lambda row: (
                str(row.get("filedAt", "")),
                str(row.get("ticker", "")),
                str(row.get("accession", "")),
            )
        )
    elif field == "backtest":
        horizon_order = {"1M": 0, "3M": 1, "6M": 2, "12M": 3}
        rows.sort(
            key=lambda row: (
                horizon_order.get(str(row.get("horizon", "")), 99),
                str(row.get("horizon", "")),
            )
        )
    else:
        rows.sort(key=lambda row: str(row.get("date", "")))
    return rows


def _aliases(row: dict[str, Any], field: str) -> dict[str, Any]:
    aliases = {
        "issuer_cik": "issuerCik",
        "market_rs": "marketRs",
        "sector_rs": "sectorRs",
        "insider_cost": "insiderCost",
        "current_price": "currentPrice",
        "filed_at": "filedAt",
        "full_engine": "fullEngine",
        "cluster_buy": "clusterBuy",
        "simple_ratio": "simpleRatio",
        "issuerCIK": "issuerCik",
        "reason_codes": "reasonCodes",
        "source_references": "sourceReferences",
    }
    for source, target in aliases.items():
        if source in row and target not in row:
            row[target] = row.pop(source)
    # A signal snapshot is a useful generic input for a candidate table.
    if field == "candidates" and "scores" in row:
        issuer = row.get("issuer", {})
        scores = row.get("scores", {})
        total = scores.get("total", {})
        row.setdefault("ticker", issuer.get("ticker"))
        row.setdefault("issuerCik", issuer.get("cik"))
        row.setdefault("company", issuer.get("name"))
        row.setdefault("sector", issuer.get("sector"))
        row.setdefault("total", total.get("score"))
        row.setdefault("insider", scores.get("companyInsider", {}).get("score"))
        row.setdefault("divergence", scores.get("divergence", {}).get("score"))
        row.setdefault("turn", scores.get("turn", {}).get("score"))
        row.setdefault("cluster", total.get("components", {}).get("cluster"))
        row.setdefault(
            "state",
            row.get("state", {}).get("current")
            if isinstance(row.get("state"), Mapping)
            else row.get("state"),
        )
        alerts = row.get("alerts", [])
        row.setdefault(
            "reasons", [reason for alert in alerts for reason in alert.get("reasons", [])]
        )
        provenance = row.get("provenance", {})
        if provenance:
            row.setdefault("sourceReferences", provenance)
        allowed = set(_ROW_KEYS["candidates"]) | _OPTIONAL_ROW_KEYS
        row = {key: item for key, item in row.items() if key in allowed}
    return row


def _validate_dashboard(value: Mapping[str, Any]) -> None:
    if tuple(value) != _DASHBOARD_KEYS:
        raise DashboardExportError("dashboard fields do not match app/lib/dashboard-data.ts")
    if value["schemaVersion"] != "1.0.0":
        raise DashboardExportError("unsupported dashboard schemaVersion")
    if value["status"] not in _DASHBOARD_STATUSES:
        raise DashboardExportError(f"invalid dashboard status: {value['status']}")
    for key in _ROW_KEYS:
        rows = value[key]
        if not isinstance(rows, list):
            raise DashboardExportError(f"{key} must be a list")
        for row in rows:
            if set(row) - set(_ROW_KEYS[key]) - _OPTIONAL_ROW_KEYS or not set(
                _ROW_KEYS[key]
            ) <= set(row):
                raise DashboardExportError(f"{key} row has the wrong fields")
            if key == "candidates" and row["state"] not in _STATE_NAMES:
                raise DashboardExportError(f"invalid candidate state: {row['state']}")
            if key == "filings" and row["side"] not in {"BUY", "SELL"}:
                raise DashboardExportError(f"invalid filing side: {row['side']}")
            if key == "candidates" and not isinstance(row["reasons"], list):
                raise DashboardExportError("candidate reasons must be a list")
    _assert_finite(value)


def _make_manifest(
    data: Mapping[str, Any],
    dashboard: Mapping[str, Any],
    run_id: str,
    as_of: str,
    signal_refs: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    quality = data.get("quality")
    if quality is None:
        quality = _default_quality()
    watermarks = data.get("watermarks") or {
        "secAcceptedThrough": None,
        "marketSessionThrough": None,
        "fundamentalsAvailableThrough": None,
    }
    disposition = str(quality.get("disposition", "BLOCKED"))
    if (dashboard["status"] == "VALIDATED") != (disposition == "PASS"):
        raise DashboardExportError(
            "VALIDATED dashboard status requires complete PASS quality evidence"
        )
    publication_succeeded = dashboard["status"] == "VALIDATED" and disposition == "PASS"
    manifest: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "runId": run_id,
        "asOf": as_of,
        "generatedAt": dashboard["generatedAt"],
        "status": "SUCCEEDED" if publication_succeeded else "DEGRADED",
        "scoreVersion": dashboard["scoreVersion"],
        "versions": {
            "scoring": dashboard["scoreVersion"],
            "stateModel": "state.v1",
            "canonicalSchema": "1.0.0",
            "signalSchema": "1.0.0",
        },
        "watermarks": watermarks,
        "universe": {
            "issuerCount": len({r["issuerCik"] for r in dashboard["candidates"]}),
            "activeTransactionCount": 0,
            "signalCount": len(signal_refs) or len(dashboard["candidates"]),
        },
        "quality": quality,
        "signals": signal_refs,
        "artifacts": artifacts,
        "files": files,
    }
    manifest["manifestId"] = "mft_" + _manifest_digest(manifest)[:32]
    return cast(dict[str, Any], _json_ready(manifest))


def _validate_manifest(value: Mapping[str, Any]) -> None:
    required = {
        "schemaVersion",
        "manifestId",
        "runId",
        "asOf",
        "generatedAt",
        "status",
        "scoreVersion",
        "versions",
        "watermarks",
        "universe",
        "quality",
        "signals",
        "files",
        "artifacts",
    }
    missing = required.difference(value)
    if missing:
        raise DashboardExportError(f"manifest missing required fields: {sorted(missing)}")
    _validate_identifier(str(value["manifestId"]), "manifestId", "mft_")
    _validate_identifier(str(value["runId"]), "runId", "run_")
    if value["manifestId"] != "mft_" + _manifest_digest(value)[:32]:
        raise DashboardExportError("manifestId does not address all semantic fields")
    if value["status"] not in {"SUCCEEDED", "DEGRADED"}:
        raise DashboardExportError("invalid manifest status")
    versions = value["versions"]
    if not isinstance(versions, Mapping) or dict(versions) != {
        "scoring": value["scoreVersion"],
        "stateModel": "state.v1",
        "canonicalSchema": "1.0.0",
        "signalSchema": "1.0.0",
    }:
        raise DashboardExportError("manifest versions do not match frozen contracts")
    watermarks = value["watermarks"]
    if not isinstance(watermarks, Mapping) or set(watermarks) != {
        "secAcceptedThrough",
        "marketSessionThrough",
        "fundamentalsAvailableThrough",
    }:
        raise DashboardExportError("manifest watermarks are incomplete")
    universe = value["universe"]
    if not isinstance(universe, Mapping) or set(universe) != {
        "issuerCount",
        "activeTransactionCount",
        "signalCount",
    }:
        raise DashboardExportError("manifest universe counts are incomplete")
    if any(
        isinstance(universe[name], bool)
        or not isinstance(universe[name], int)
        or universe[name] < 0
        for name in universe
    ):
        raise DashboardExportError("manifest universe counts must be non-negative integers")
    _validate_quality(value["quality"], status=str(value["status"]))
    if not isinstance(value["signals"], list):
        raise DashboardExportError("manifest signals must be a list")
    if not isinstance(value["artifacts"], list) or not value["artifacts"]:
        raise DashboardExportError("manifest artifacts must be non-empty")
    if not isinstance(value["files"], list) or not value["files"]:
        raise DashboardExportError("manifest files must be non-empty")
    seen_paths: set[str] = set()
    for file in value["files"]:
        if (
            set(file) != {"path", "size", "sha256"}
            or not isinstance(file["size"], int)
            or file["size"] < 0
        ):
            raise DashboardExportError("invalid manifest file record")
        if len(file["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in file["sha256"]):
            raise DashboardExportError("invalid manifest checksum")
        path = str(file["path"])
        if path.startswith(("/", "\\")) or ".." in Path(path).parts or path in seen_paths:
            raise DashboardExportError("manifest file path must be unique and relative")
        seen_paths.add(path)
    file_hashes = {str(file["path"]): str(file["sha256"]) for file in value["files"]}
    for artifact in value["artifacts"]:
        if not isinstance(artifact, Mapping) or not {
            "kind",
            "uri",
            "contentHash",
            "mediaType",
        } <= set(artifact):
            raise DashboardExportError("invalid manifest artifact record")
        uri = str(artifact["uri"])
        expected_hash = file_hashes.get(uri)
        if expected_hash is None or artifact["contentHash"] != f"sha256:{expected_hash}":
            raise DashboardExportError("manifest artifact hash does not match a file record")
    _assert_finite(value)


def _default_quality() -> dict[str, Any]:
    def measurement(threshold: float) -> dict[str, Any]:
        return {
            "numerator": 0,
            "denominator": 0,
            "rate": None,
            "threshold": threshold,
            "result": "NOT_EVALUATED",
        }

    return {
        "disposition": "BLOCKED",
        "parseSuccess": measurement(0.995),
        "marketCoverage": measurement(0.9),
        "coreBranchCoverage": measurement(0.85),
        "issues": ["QUALITY_EVIDENCE_MISSING"],
    }


def _manifest_digest(value: Mapping[str, Any]) -> str:
    semantic = {key: item for key, item in value.items() if key != "manifestId"}
    return hashlib.sha256(_canonical_bytes(semantic)).hexdigest()


def _validate_quality(value: Any, *, status: str) -> None:
    if not isinstance(value, Mapping):
        raise DashboardExportError("manifest quality must be an object")
    required = {
        "disposition",
        "parseSuccess",
        "marketCoverage",
        "coreBranchCoverage",
        "issues",
    }
    if set(value) != required:
        raise DashboardExportError("manifest quality evidence is incomplete")
    disposition = str(value["disposition"])
    if disposition not in {"PASS", "DEGRADED", "BLOCKED"}:
        raise DashboardExportError("invalid quality disposition")
    expected_thresholds = {
        "parseSuccess": 0.995,
        "marketCoverage": 0.90,
        "coreBranchCoverage": 0.85,
    }
    all_passed = True
    for name, threshold in expected_thresholds.items():
        measurement = value[name]
        if not isinstance(measurement, Mapping) or set(measurement) != {
            "numerator",
            "denominator",
            "rate",
            "threshold",
            "result",
        }:
            raise DashboardExportError(f"invalid quality measurement: {name}")
        if float(measurement["threshold"]) != threshold:
            raise DashboardExportError(f"invalid quality threshold: {name}")
        denominator = measurement["denominator"]
        numerator = measurement["numerator"]
        rate = measurement["rate"]
        passed = (
            isinstance(denominator, int)
            and not isinstance(denominator, bool)
            and denominator > 0
            and isinstance(numerator, int)
            and not isinstance(numerator, bool)
            and 0 <= numerator <= denominator
            and isinstance(rate, (int, float))
            and not isinstance(rate, bool)
            and math.isfinite(float(rate))
            and abs(float(rate) - numerator / denominator) <= 1e-9
            and float(rate) >= threshold
            and measurement["result"] == "PASS"
        )
        all_passed = all_passed and passed
    issues = value["issues"]
    if not isinstance(issues, list) or any(not isinstance(issue, str) for issue in issues):
        raise DashboardExportError("quality issues must be a string list")
    if disposition == "PASS" and (not all_passed or issues):
        raise DashboardExportError("PASS quality requires complete passing evidence")
    if disposition != "PASS" and not issues:
        raise DashboardExportError("non-PASS quality must explain its issues")
    if status == "SUCCEEDED" and disposition != "PASS":
        raise DashboardExportError("SUCCEEDED manifest requires PASS quality")
    if status == "DEGRADED" and disposition == "PASS":
        raise DashboardExportError("DEGRADED manifest cannot claim PASS quality")


def _write_signal_snapshots(
    directory: Path, data: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    snapshots = data.get("signals") or data.get("signalSnapshots") or []
    if hasattr(snapshots, "to_dicts"):
        snapshots = snapshots.to_dicts()
    if not snapshots:
        return [], []
    if not isinstance(snapshots, Sequence):
        raise DashboardExportError("signals must be a sequence")
    if any(not isinstance(snapshot, Mapping) for snapshot in snapshots):
        raise DashboardExportError("signals contains a non-mapping snapshot")
    records: list[dict[str, Any]] = []
    refs: list[dict[str, Any]] = []
    for snapshot in sorted(
        (dict(s) for s in snapshots), key=lambda s: str(s.get("snapshotId", ""))
    ):
        snapshot = _json_ready(snapshot)
        _assert_finite(snapshot)
        snapshot_id = str(snapshot.get("snapshotId", ""))
        if not snapshot_id:
            raise DashboardExportError("signal snapshot is missing snapshotId")
        rel = Path("signals") / f"{_safe_filename(snapshot_id)}.json"
        content = _canonical_bytes(snapshot)
        _write_bytes(directory / rel, content)
        record = _file_record(directory, rel.as_posix())
        records.append(record)
        issuer = snapshot.get("issuer", {})
        total = snapshot.get("scores", {}).get("total", {}).get("score", 0)
        refs.append(
            {
                "snapshotId": snapshot_id,
                "issuerCik": issuer.get("cik"),
                "ticker": issuer.get("ticker"),
                "state": snapshot.get("state", {}).get("current"),
                "totalScore": total,
                "uri": rel.as_posix(),
                "contentHash": f"sha256:{record['sha256']}",
            }
        )
    return records, refs


def _file_record(directory: Path, relative: str) -> dict[str, Any]:
    content = (directory / relative).read_bytes()
    return {
        "path": relative.replace("\\", "/"),
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _replace_directory(temporary: Path, destination: Path) -> None:
    backup = destination.parent / f".{destination.name}.previous"
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True) if backup.is_dir() else backup.unlink()
    moved_old = False
    try:
        if destination.exists():
            os.replace(destination, backup)
            moved_old = True
        os.replace(temporary, destination)
    except Exception:
        if moved_old and not destination.exists() and backup.exists():
            os.replace(backup, destination)
        raise
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True) if backup.is_dir() else backup.unlink()


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (datetime, date)):
        return (
            value.astimezone(UTC).isoformat().replace("+00:00", "Z")
            if isinstance(value, datetime)
            else value.isoformat()
        )
    if isinstance(value, Decimal):
        return float(value) if value % 1 else int(value)
    if hasattr(value, "item") and callable(value.item):
        return _json_ready(value.item())
    return value


def _assert_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_finite(item, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise DashboardExportError(f"non-finite number at {path}")


def _instant(value: str | datetime) -> str:
    if isinstance(value, datetime):
        current = value if value.tzinfo else value.replace(tzinfo=UTC)
        return current.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value)


def _validate_identifier(value: str, label: str, prefix: str) -> None:
    if (
        not value.startswith(prefix)
        or len(value) < len(prefix) + 16
        or len(value) > len(prefix) + 64
    ):
        raise DashboardExportError(f"invalid {label}: {value}")


def _safe_filename(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "._-" else "_" for character in value
    )


__all__ = ["DashboardExport", "DashboardExportError", "export_dashboard"]
