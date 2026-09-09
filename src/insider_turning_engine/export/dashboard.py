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
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from insider_turning_engine.domain.scoring_lock import ScoringLockError, load_scoring_lock


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
    "companySeries": ("ticker", "date", "price", "cost", "mansfield"),
}
_OPTIONAL_ROW_KEYS = {"sourceReferences", "sourceReference", "reasonCodes"}
_STATE_NAMES = {"FALLING", "INSIDER_ACCUMULATION", "BASE_FORMING", "EARLY_TURN", "CONFIRMED_TURN"}
_DASHBOARD_STATUSES = {"VALIDATED", "EXPERIMENTAL", "STALE"}
_SCHEMAS_ROOT = Path(__file__).resolve().parents[3] / "schemas"


@lru_cache(maxsize=2)
def _schema_validator(filename: str) -> Draft202012Validator:
    """Load and check one trusted publication schema exactly once."""

    try:
        schema = json.loads((_SCHEMAS_ROOT / filename).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        raise DashboardExportError(f"publication schema is invalid: {filename}") from exc
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate_schema(value: Any, filename: str, label: str) -> None:
    error = next(iter(_schema_validator(filename).iter_errors(value)), None)
    if error is not None:
        raise DashboardExportError(f"{label} violates JSON Schema at {error.json_path}")


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
    destination.parent.mkdir(parents=True, exist_ok=True)
    _recover_directory(destination)
    if per_ticker is not None:
        chunk_by_ticker = per_ticker

    dashboard = _make_dashboard(data, score_version, generated_at, status)
    _validate_dashboard(dashboard)
    dashboard_bytes = _canonical_bytes(dashboard)
    generated = dashboard["generatedAt"]
    as_of_text = _instant(as_of if as_of is not None else generated)
    publication_run_id = run_id or f"run_{hashlib.sha256(dashboard_bytes).hexdigest()[:32]}"
    _validate_identifier(publication_run_id, "run_id", "run_")

    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    try:
        _write_bytes(temporary / "dashboard.json", dashboard_bytes)
        files: list[dict[str, Any]] = [_file_record(temporary, "dashboard.json")]
        settings_status = data.get("settingsStatus") or _default_settings_status(generated)
        if not isinstance(settings_status, Mapping):
            raise DashboardExportError("settingsStatus must be an object")
        settings_status = cast(dict[str, Any], _json_ready(dict(settings_status)))
        _validate_settings_status(settings_status)
        _write_bytes(temporary / "settings-status.json", _canonical_bytes(settings_status))
        files.append(_file_record(temporary, "settings-status.json"))

        if chunk_by_ticker:
            tickers = sorted(
                {str(row["ticker"]) for row in dashboard["candidates"] if row["ticker"]}
            )
            for ticker in tickers:
                chunk = next(row for row in dashboard["candidates"] if row["ticker"] == ticker)
                rel = Path("tickers") / f"{_safe_filename(ticker)}.json"
                _write_bytes(temporary / rel, _canonical_bytes(chunk))
                files.append(_file_record(temporary, rel.as_posix()))

        signal_files, signal_refs = _write_signal_snapshots(temporary, data, publication_run_id)
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
        settings_record = next(
            record for record in files if record["path"] == "settings-status.json"
        )
        artifacts.append(
            {
                "kind": "SETTINGS_STATUS",
                "uri": "settings-status.json",
                "contentHash": f"sha256:{settings_record['sha256']}",
                "mediaType": "application/json",
            }
        )
        manifest = _make_manifest(
            data,
            dashboard,
            publication_run_id,
            as_of_text,
            signal_refs,
            artifacts,
            files,
        )
        _write_bytes(temporary / "manifest.json", _canonical_bytes(manifest))
        validate_dashboard_directory(temporary)
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


def _default_settings_status(generated_at: str) -> dict[str, Any]:
    channel = {
        "enabled": False,
        "configured": False,
        "recipientMasked": None,
        "lastTestAt": None,
        "lastSuccessAt": None,
        "failureCount": 0,
    }
    return {
        "schemaVersion": "1.0.0",
        "generatedAt": generated_at,
        "environment": "local",
        "alertsAllowed": False,
        "blockingReasons": ["SETTINGS_STATUS_NOT_PROVIDED"],
        "policy": {
            "deliveryEnabled": False,
            "minimumSeverity": "WATCH",
            "alertTypes": ["MAJOR_INSIDER_BUY", "STEALTH_ACCUMULATION", "TURNING"],
            "cooldownDays": 14,
            "timezone": "Europe/Zagreb",
            "quietHours": None,
        },
        "channels": {"telegram": dict(channel), "email": dict(channel)},
    }


def _validate_settings_status(value: Mapping[str, Any]) -> None:
    _assert_finite(value)
    _validate_schema(value, "settings-status.schema.json", "settings status")
    if value["alertsAllowed"]:
        enabled = [item for item in value["channels"].values() if item["enabled"]]
        if (
            value["environment"] != "production"
            or not value["policy"]["deliveryEnabled"]
            or value["blockingReasons"]
            or not enabled
            or any(not item["configured"] for item in enabled)
        ):
            raise DashboardExportError("settings readiness is inconsistent")


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
    # JSON object ordering is not semantic, and canonical serialization sorts
    # keys before the publication is read back from disk.
    if set(value) != set(_DASHBOARD_KEYS):
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
    supplied_quality = data.get("quality")
    quality = (
        dict(supplied_quality)
        if isinstance(supplied_quality, Mapping)
        else _default_quality()
    )
    try:
        methodology_complete = load_scoring_lock().methodology_complete
    except ScoringLockError:
        methodology_complete = False
    quality["methodologyComplete"] = methodology_complete
    if not methodology_complete:
        issues = list(quality.get("issues") or ())
        if "SCORING_METHODOLOGY_INCOMPLETE" not in issues:
            issues.append("SCORING_METHODOLOGY_INCOMPLETE")
        quality["issues"] = issues
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
            "activeTransactionCount": len(dashboard["filings"]),
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
    _assert_finite(value)
    _validate_schema(value, "dashboard-manifest.schema.json", "dashboard manifest")
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
    if value["schemaVersion"] != "1.0.0" or value["scoreVersion"] != "scoring.v1":
        raise DashboardExportError("manifest versions do not match frozen contracts")
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
    signal_keys = {
        "snapshotId",
        "issuerCik",
        "ticker",
        "state",
        "totalScore",
        "uri",
        "contentHash",
    }
    seen_signal_ids: set[str] = set()
    seen_signal_uris: set[str] = set()
    for signal in value["signals"]:
        if not isinstance(signal, Mapping) or set(signal) != signal_keys:
            raise DashboardExportError("invalid manifest signal reference")
        snapshot_id = str(signal["snapshotId"])
        issuer_cik = str(signal["issuerCik"])
        uri = str(signal["uri"])
        score = signal["totalScore"]
        if (
            snapshot_id in seen_signal_ids
            or uri in seen_signal_uris
            or not snapshot_id.startswith("sig_")
            or not 20 <= len(snapshot_id) <= 68
            or any(
                character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                for character in snapshot_id[4:]
            )
        ):
            raise DashboardExportError("manifest signal identity and URI must be unique")
        if len(issuer_cik) != 10 or not issuer_cik.isdigit():
            raise DashboardExportError("manifest signal issuer CIK is invalid")
        ticker = signal["ticker"]
        if ticker is not None and (
            not isinstance(ticker, str)
            or not 1 <= len(ticker) <= 15
            or ticker[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            or any(
                character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for character in ticker
            )
        ):
            raise DashboardExportError("manifest signal ticker is invalid")
        if signal["state"] not in _STATE_NAMES:
            raise DashboardExportError("manifest signal state is invalid")
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
            or not 0 <= float(score) <= 100
        ):
            raise DashboardExportError("manifest signal score is invalid")
        expected_hash = file_hashes.get(uri)
        if expected_hash is None or signal["contentHash"] != f"sha256:{expected_hash}":
            raise DashboardExportError("manifest signal hash does not match a file record")
        seen_signal_ids.add(snapshot_id)
        seen_signal_uris.add(uri)
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


def validate_dashboard_directory(
    directory: str | os.PathLike[str], *, require_settings: bool = False
) -> Mapping[str, Any]:
    """Validate one complete, closed-world dashboard publication directory."""

    root = Path(directory).resolve()
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise DashboardExportError("dashboard manifest is missing or invalid") from exc
    if not isinstance(manifest, Mapping):
        raise DashboardExportError("dashboard manifest must be an object")
    _validate_manifest(manifest)

    expected_paths = {str(record["path"]) for record in manifest["files"]}
    actual_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if actual_paths != expected_paths:
        raise DashboardExportError("dashboard directory contains unreferenced or missing files")
    for record in manifest["files"]:
        target = (root / str(record["path"])).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise DashboardExportError("manifest file escapes dashboard directory") from exc
        content = target.read_bytes()
        if len(content) != record["size"]:
            raise DashboardExportError("manifest file size mismatch")
        if hashlib.sha256(content).hexdigest() != record["sha256"]:
            raise DashboardExportError("manifest file hash mismatch")
        if target.suffix == ".json":
            try:
                json.loads(content)
            except (UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
                raise DashboardExportError("manifest references invalid JSON") from exc

    signal_by_uri = {str(signal["uri"]): signal for signal in manifest["signals"]}
    for uri, reference in signal_by_uri.items():
        snapshot = json.loads((root / uri).read_text(encoding="utf-8"))
        _validate_signal_snapshot(snapshot, expected_run_id=str(manifest["runId"]))
        issuer = snapshot["issuer"]
        total = snapshot["scores"]["total"]["score"]
        state = snapshot["state"]["current"]
        if (
            snapshot["snapshotId"] != reference["snapshotId"]
            or issuer["cik"] != reference["issuerCik"]
            or issuer.get("ticker") != reference["ticker"]
            or state != reference["state"]
            or total != reference["totalScore"]
        ):
            raise DashboardExportError("manifest signal reference disagrees with its snapshot")

    dashboard_path = root / "dashboard.json"
    if "dashboard.json" not in expected_paths:
        raise DashboardExportError("manifest must reference dashboard.json")
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    if not isinstance(dashboard, Mapping):
        raise DashboardExportError("dashboard.json must contain an object")
    _validate_dashboard(dashboard)
    if dashboard["scoreVersion"] != manifest["scoreVersion"]:
        raise DashboardExportError("dashboard and manifest score versions disagree")
    if (dashboard["status"] == "VALIDATED") != (manifest["status"] == "SUCCEEDED"):
        raise DashboardExportError("dashboard and manifest publication status disagree")
    settings_path = root / "settings-status.json"
    if "settings-status.json" not in expected_paths and require_settings:
        raise DashboardExportError("manifest must reference settings-status.json")
    if "settings-status.json" not in expected_paths:
        return manifest  # Historical v1 snapshots predate the settings extension.
    settings_status = json.loads(settings_path.read_text(encoding="utf-8"))
    if not isinstance(settings_status, Mapping):
        raise DashboardExportError("settings-status.json must contain an object")
    _validate_settings_status(settings_status)
    if settings_status["alertsAllowed"] and (
        manifest["status"] != "SUCCEEDED"
        or manifest["quality"]["disposition"] != "PASS"
    ):
        raise DashboardExportError("settings cannot enable alerts for a non-PASS snapshot")
    return manifest


def dashboard_publication_policy(manifest: Mapping[str, Any]) -> tuple[bool, bool]:
    """Return ``(pages_allowed, alerts_allowed)`` for a validated manifest.

    A methodologically degraded/experimental snapshot may remain visible only
    when its operational inputs are healthy. Stale benchmarks, invalid
    canonical data, or any below-threshold measurement block Pages entirely.
    External alerts additionally require the manifest's full PASS disposition.
    """

    _validate_manifest(manifest)
    quality = manifest["quality"]
    operationally_healthy = (
        quality["canonicalValid"] is True
        and quality["methodologyComplete"] is True
        and quality["benchmarkFresh"] is True
        and all(
            quality[name]["result"] == "PASS"
            for name in ("parseSuccess", "marketCoverage", "coreBranchCoverage")
        )
    )
    pages_allowed = operationally_healthy and quality["disposition"] in {
        "PASS",
        "DEGRADED",
    }
    alerts_allowed = (
        pages_allowed and quality["disposition"] == "PASS" and manifest["status"] == "SUCCEEDED"
    )
    return pages_allowed, alerts_allowed


def dashboard_experimental_publication_policy(
    manifest: Mapping[str, Any],
) -> tuple[bool, bool]:
    """Authorize only the real-data live preview, never external alerts."""

    _validate_manifest(manifest)
    quality = manifest["quality"]
    universe = manifest["universe"]
    issues = set(quality["issues"])
    pages_allowed = (
        manifest["status"] == "DEGRADED"
        and quality["canonicalValid"] is True
        and quality["benchmarkFresh"] is True
        and quality["parseSuccess"]["result"] == "PASS"
        and quality["marketCoverage"]["result"] == "PASS"
        and "LIVE_EXPERIMENTAL_ROLLING_WINDOW" in issues
        and "SCORING_METHODOLOGY_INCOMPLETE" in issues
        and universe["issuerCount"] > 0
        and universe["activeTransactionCount"] > 0
        and universe["signalCount"] > 0
    )
    return pages_allowed, False


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
        "canonicalValid": False,
        "methodologyComplete": False,
        "benchmarkFresh": False,
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
        "canonicalValid",
        "methodologyComplete",
        "benchmarkFresh",
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
    canonical_valid = value["canonicalValid"]
    methodology_complete = value["methodologyComplete"]
    benchmark_fresh = value["benchmarkFresh"]
    if (
        not isinstance(canonical_valid, bool)
        or not isinstance(methodology_complete, bool)
        or not isinstance(benchmark_fresh, bool)
    ):
        raise DashboardExportError(
            "quality validity, methodology, and freshness evidence must be boolean"
        )
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
        counts_valid = (
            isinstance(denominator, int)
            and not isinstance(denominator, bool)
            and denominator >= 0
            and isinstance(numerator, int)
            and not isinstance(numerator, bool)
            and 0 <= numerator <= denominator
        )
        evaluated = denominator > 0 if counts_valid else False
        rate_valid = (
            evaluated
            and isinstance(rate, (int, float))
            and not isinstance(rate, bool)
            and math.isfinite(float(rate))
            and 0.0 <= float(rate) <= 1.0
            and abs(float(rate) - numerator / denominator) <= 1e-9
        )
        expected_result = (
            "PASS"
            if rate_valid and float(rate) >= threshold
            else ("FAIL" if rate_valid else "NOT_EVALUATED")
        )
        if (
            not counts_valid
            or (evaluated and not rate_valid)
            or (not evaluated and rate is not None)
            or measurement["result"] != expected_result
        ):
            raise DashboardExportError(f"incoherent quality measurement: {name}")
        passed = expected_result == "PASS"
        all_passed = all_passed and passed
    issues = value["issues"]
    if not isinstance(issues, list) or any(not isinstance(issue, str) for issue in issues):
        raise DashboardExportError("quality issues must be a string list")
    if disposition == "PASS" and (
        not all_passed
        or not canonical_valid
        or not methodology_complete
        or not benchmark_fresh
        or issues
    ):
        raise DashboardExportError("PASS quality requires complete passing evidence")
    if disposition != "PASS" and not issues:
        raise DashboardExportError("non-PASS quality must explain its issues")
    if status == "SUCCEEDED" and disposition != "PASS":
        raise DashboardExportError("SUCCEEDED manifest requires PASS quality")
    if status == "DEGRADED" and disposition == "PASS":
        raise DashboardExportError("DEGRADED manifest cannot claim PASS quality")


def _write_signal_snapshots(
    directory: Path, data: Mapping[str, Any], run_id: str
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
        _validate_signal_snapshot(snapshot, expected_run_id=run_id)
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


def _validate_signal_snapshot(value: Any, *, expected_run_id: str) -> None:
    """Enforce the immutable score identity at the publication boundary.

    The checked-in JSON Schema remains the complete structural contract. This
    guard duplicates only the security-critical invariants needed by the
    dependency-light workflow validator.
    """

    _assert_finite(value)
    _validate_schema(value, "signal-snapshot.schema.json", "signal snapshot")
    required = {
        "schemaVersion",
        "snapshotId",
        "issuer",
        "asOf",
        "generatedAt",
        "versions",
        "scores",
        "state",
        "alerts",
        "qualityFlags",
        "provenance",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise DashboardExportError("signal snapshot does not match the frozen top-level schema")
    if value["schemaVersion"] != "1.0.0" or value["versions"] != {
        "scoring": "scoring.v1",
        "stateModel": "state.v1",
    }:
        raise DashboardExportError("signal snapshot versions do not match frozen contracts")
    provenance = value["provenance"]
    if not isinstance(provenance, Mapping) or provenance.get("runId") != expected_run_id:
        raise DashboardExportError("signal snapshot runId does not match its manifest")
    try:
        scoring = load_scoring_lock()
    except ScoringLockError as exc:
        raise DashboardExportError(f"scoring.v1 lock is invalid: {exc}") from exc
    if (
        provenance.get("scoreConfigHash") != scoring.config_hash
        or provenance.get("scoreLineage") != scoring.lineage
        or provenance.get("methodologyHash") != scoring.methodology_hash
        or provenance.get("methodologyStatus") != scoring.status.value
    ):
        raise DashboardExportError("signal snapshot scoring provenance is not locked scoring.v1")
    frozen_raw = provenance.get("scoreFrozenAt")
    frozen_at = (
        _parse_aware_instant(frozen_raw, "scoreFrozenAt") if frozen_raw is not None else None
    )
    if frozen_at != scoring.frozen_at:
        raise DashboardExportError("signal snapshot scoreFrozenAt does not match scoring.v1 lock")
    generated_at = _parse_aware_instant(value["generatedAt"], "generatedAt")
    _parse_aware_instant(value["asOf"], "asOf")
    if frozen_at is not None and frozen_at > generated_at:
        raise DashboardExportError("signal snapshot score was frozen after it was generated")


def _parse_aware_instant(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise DashboardExportError(f"signal snapshot {label} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DashboardExportError(f"signal snapshot {label} is invalid") from exc
    if parsed.tzinfo is None:
        raise DashboardExportError(f"signal snapshot {label} must include a timezone")
    return parsed.astimezone(UTC)


def _file_record(directory: Path, relative: str) -> dict[str, Any]:
    content = (directory / relative).read_bytes()
    return {
        "path": relative.replace("\\", "/"),
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _replace_directory(temporary: Path, destination: Path) -> None:
    backup = destination.parent / f".{destination.name}.previous"
    _recover_directory(destination)
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


def _recover_directory(destination: Path) -> None:
    """Restore the last publication after a hard stop between directory swaps."""

    backup = destination.parent / f".{destination.name}.previous"
    if not backup.exists():
        return
    if not destination.exists():
        os.replace(backup, destination)
        return
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


__all__ = [
    "DashboardExport",
    "DashboardExportError",
    "export_dashboard",
    "validate_dashboard_directory",
]
