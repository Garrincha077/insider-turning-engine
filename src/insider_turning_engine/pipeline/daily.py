"""Fail-closed, offline daily scoring pipeline.

This module intentionally has no provider, notification, or export calls. It
turns already-materialized manifest inputs into replayable warehouse artifacts
and emits a stale-data hold whenever the locked scoring inputs are incomplete.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, cast

import polars as pl
from pydantic import ValidationError

from insider_turning_engine.domain.models import CanonicalTransaction, QualityStatus, TableType
from insider_turning_engine.features.price import latest_price_facts, price_features
from insider_turning_engine.features.rs import relative_strength_features
from insider_turning_engine.features.technical import Observation, midrank_percentile
from insider_turning_engine.normalization.amendments import resolve_amendments
from insider_turning_engine.pipeline.dashboard_input import build_dashboard_input
from insider_turning_engine.pipeline.scoring import DailyScoringError, assemble_daily_scores
from insider_turning_engine.scoring import ScoreEngine


class DailyPipelineError(ValueError):
    """Raised when manifest inputs cannot support a point-in-time daily run."""


@dataclass(frozen=True, slots=True)
class DailyRunResult:
    run_id: str
    status: str
    output_root: Path
    effective_transactions: int
    signals: tuple[Mapping[str, Any], ...]
    alerts: tuple[Mapping[str, Any], ...]

    def as_mapping(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "status": self.status,
            "outputRoot": str(self.output_root),
            "effectiveTransactions": self.effective_transactions,
            "signals": [_json_value(item) for item in self.signals],
            "alerts": [_json_value(item) for item in self.alerts],
        }


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _canonical_json(value: Any) -> bytes:
    serialized = json.dumps(_json_value(value), sort_keys=True, separators=(",", ":")) + "\n"
    return serialized.encode("utf-8")


def _as_utc(value: Any, *, name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time(23, 59, 59), tzinfo=UTC)
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DailyPipelineError(f"{name} must be an ISO timestamp") from exc
    else:
        raise DailyPipelineError(f"{name} must be a date or timestamp")
    if parsed.tzinfo is None:
        raise DailyPipelineError(f"{name} must be timezone-aware")
    return parsed.astimezone(UTC)


def _artifact_path(inputs: Any, *names: str, required: bool = False) -> Path | None:
    for name in names:
        artifact = inputs.get(name) if hasattr(inputs, "get") else None
        if artifact is None:
            continue
        value = getattr(artifact, "path", artifact)
        path = Path(value)
        if not path.is_file():
            raise DailyPipelineError(f"manifest input {name} is not a file: {path}")
        return path
    if required:
        raise DailyPipelineError(f"manifest is missing required input: {names[0]}")
    return None


def _read_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return [dict(row) for row in pl.read_parquet(path).to_dicts()]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DailyPipelineError(f"cannot read input: {path}") from exc
    stripped = text.strip()
    if not stripped:
        return []
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list) and all(isinstance(row, Mapping) for row in parsed):
        return [dict(cast(Mapping[str, Any], row)) for row in parsed]
    if isinstance(parsed, Mapping):
        wrapped_rows = parsed.get("rows", parsed.get("transactions"))
        if isinstance(wrapped_rows, list) and all(
            isinstance(row, Mapping) for row in wrapped_rows
        ):
            return [dict(cast(Mapping[str, Any], row)) for row in wrapped_rows]
    jsonl_rows: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DailyPipelineError(f"invalid JSONL at {path}:{number}") from exc
        if not isinstance(row, Mapping):
            raise DailyPipelineError(f"JSONL row at {path}:{number} must be an object")
        jsonl_rows.append(dict(row))
    return jsonl_rows


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DailyPipelineError(f"{label} is unreadable or invalid JSON") from exc
    if not isinstance(value, Mapping):
        raise DailyPipelineError(f"{label} must be a JSON object")
    return dict(value)


def _measurement(numerator: int, denominator: int, threshold: float) -> dict[str, Any]:
    if numerator < 0 or denominator < 0 or numerator > denominator:
        raise DailyPipelineError("quality evidence contains invalid measurement counts")
    rate = numerator / denominator if denominator else None
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": rate,
        "threshold": threshold,
        "result": (
            "PASS"
            if rate is not None and rate >= threshold
            else "FAIL"
            if rate is not None
            else "NOT_EVALUATED"
        ),
    }


def _read_sec_batch(path: Path) -> list[dict[str, Any]]:
    """Read a canonical SEC batch and reject an incomplete producer envelope.

    ``update-sec`` deliberately persists records together with its quarantine
    and failure evidence.  Treating that object as a transaction row would
    hide partial ingestion from the canonical commit boundary, so the daily
    consumer validates the envelope before it exposes the record list.
    """

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DailyPipelineError("SEC batch is unreadable or invalid JSON") from exc
    rows: Any
    if isinstance(value, list):
        rows = value
    elif isinstance(value, Mapping):
        failures = value.get("failures", [])
        quarantines = value.get("quarantines", [])
        if not isinstance(failures, list) or not isinstance(quarantines, list):
            raise DailyPipelineError("SEC batch evidence must be arrays")
        if failures or quarantines:
            raise DailyPipelineError("SEC batch contains ingestion or quarantine errors")
        rows = value.get("records")
    else:
        rows = None
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise DailyPipelineError("SEC batch records must be an array of objects")
    return [dict(cast(Mapping[str, Any], row)) for row in rows]


def _canonical_records(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[list[CanonicalTransaction], list[dict[str, Any]]]:
    records: list[CanonicalTransaction] = []
    flattened: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        # Canonical JSON has schemaVersion and is always model-validated. A
        # deliberately flattened fixture is accepted only for the bounded
        # vertical slice and cannot participate in amendment resolution.
        if "schemaVersion" in row or "schema_version" in row:
            try:
                record = CanonicalTransaction.model_validate(row)
            except ValidationError as exc:
                raise DailyPipelineError(
                    f"canonical transaction {index} is invalid: {exc}"
                ) from exc
            records.append(record)
            flattened.append(_flat_record(record))
        else:
            flattened.append(dict(row))
    return records, flattened


def _flat_record(record: CanonicalTransaction) -> dict[str, Any]:
    return {
        "issuer_cik": record.issuer.cik,
        "owner_cik": record.reporting_owner.cik,
        "transaction_date": record.transaction.transaction_date.isoformat(),
        "accepted_at": record.timestamps.accepted_at.isoformat()
        if record.timestamps.accepted_at
        else None,
        "knowledge_at": record.timestamps.knowledge_at.isoformat(),
        "code": record.transaction.code,
        "acquired_disposed": record.transaction.acquired_disposed,
        "table_type": record.security.table_type.value,
        "classification": record.transaction.classification.value,
        "economic_classification": record.transaction.economic_classification.value,
        "value_usd": float(record.transaction.value)
        if record.transaction.value is not None
        else None,
        "shares": (float(record.transaction.shares)
                   if record.transaction.shares is not None else None),
        "price_per_share": (
            float(record.transaction.price_per_share)
            if record.transaction.price_per_share is not None
            else None
        ),
        "post_transaction_shares": (
            float(record.transaction.post_transaction_shares)
            if record.transaction.post_transaction_shares is not None
            else None
        ),
        "rule_10b5_1": record.transaction.rule_10b51.value,
        "lifecycle_status": record.lifecycle.status.value,
        "valid_from": record.lifecycle.valid_from.isoformat(),
        "valid_to": record.lifecycle.valid_to.isoformat() if record.lifecycle.valid_to else None,
        "transaction_id": record.transaction_id,
        "source_row_key": record.source.source_row_key,
        "quality_status": record.quality.status.value,
        "issuer": {"cik": record.issuer.cik, "ticker": record.issuer.ticker},
        "reporting_owner": {"cik": record.reporting_owner.cik},
        "relationship": record.relationship.model_dump(mode="json"),
        "transaction": record.transaction.model_dump(mode="json"),
        "security": record.security.model_dump(mode="json"),
        "timestamps": record.timestamps.model_dump(mode="json"),
        "lifecycle": record.lifecycle.model_dump(mode="json"),
    }


def _instant(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return _as_utc(value, name="knowledge timestamp")
    except DailyPipelineError:
        return None


def _reject_future_rows(rows: Iterable[Mapping[str, Any]], *, as_of: datetime, source: str) -> None:
    for index, row in enumerate(rows):
        for name in ("knowledge_at", "knowledgeAt", "accepted_at", "acceptedAt", "available_at"):
            if name in row and row[name] is not None:
                stamp = _instant(row[name])
                if stamp is None:
                    raise DailyPipelineError(f"{source} row {index} has invalid {name}")
                if stamp > as_of:
                    raise DailyPipelineError(f"{source} row {index} has {name} later than as_of")
        for name in ("transaction_date", "transactionDate", "date"):
            if name in row and row[name] is not None:
                try:
                    event = date.fromisoformat(str(row[name])[:10])
                except ValueError as exc:
                    raise DailyPipelineError(f"{source} row {index} has invalid {name}") from exc
                if event > as_of.date():
                    raise DailyPipelineError(f"{source} row {index} has {name} later than as_of")


def _qualified(row: Mapping[str, Any], *, as_of: datetime) -> bool:
    try:
        event = date.fromisoformat(str(row.get("transaction_date", ""))[:10])
    except ValueError:
        return False
    known = _instant(row.get("knowledge_at", row.get("accepted_at")))
    code = str(row.get("code", "")).upper()
    table = str(row.get("table_type", "NON_DERIVATIVE")).upper()
    status = str(row.get("lifecycle_status", "ACTIVE")).upper()
    return (
        known is not None
        and known <= as_of
        and event <= as_of.date()
        and event >= as_of.date() - timedelta(days=365)
        and code in {"P", "S"}
        and table == TableType.NON_DERIVATIVE.value
        and status == "ACTIVE"
    )


def _ticker_by_cik(rows: Iterable[Mapping[str, Any]], *, as_of: datetime) -> dict[str, str]:
    selected: dict[str, tuple[datetime, str]] = {}
    for row in rows:
        cik = str(row.get("cik", row.get("issuer_cik", ""))).zfill(10)
        ticker = str(row.get("ticker", row.get("symbol", ""))).strip().upper()
        if len(cik) != 10 or not cik.isdigit() or not ticker:
            continue
        if row.get("eligible") is False or row.get("is_operating_company") is False:
            continue
        if row.get("is_spac_shell") is True:
            continue
        exchange = str(row.get("exchange", "")).strip().upper()
        if exchange and exchange not in {
            "NYSE",
            "NASDAQ",
            "NYSE AMERICAN",
            "NYSEAMERICAN",
            "AMEX",
        }:
            continue
        security_type = str(row.get("security_type", row.get("securityType", ""))).upper()
        if security_type and security_type not in {
            "COMMON_STOCK",
            "OPERATING_COMMON_STOCK",
            "COMMON",
        }:
            continue
        known = _instant(row.get("knowledge_at", row.get("accepted_at")))
        if known is None:
            continue
        if known > as_of:
            raise DailyPipelineError("identity mapping knowledge_at later than as_of")
        valid_from = row.get("valid_from", row.get("effective_from"))
        valid_to = row.get("valid_to", row.get("effective_to"))
        if valid_from is not None and date.fromisoformat(str(valid_from)[:10]) > as_of.date():
            continue
        if valid_to is not None and date.fromisoformat(str(valid_to)[:10]) <= as_of.date():
            continue
        previous = selected.get(cik)
        if (
            previous is None
            or known > previous[0]
            or (known == previous[0] and ticker < previous[1])
        ):
            selected[cik] = (known, ticker)
    return {cik: item[1] for cik, item in selected.items()}


def _sector_by_ticker(
    rows: Iterable[Mapping[str, Any]],
    identity: Mapping[str, str],
    *,
    as_of: datetime,
) -> dict[str, str]:
    selected: dict[str, tuple[datetime, str]] = {}
    for row in rows:
        cik = str(row.get("cik", row.get("issuer_cik", ""))).zfill(10)
        ticker = identity.get(cik)
        sector = str(row.get("sector_etf", row.get("sectorEtf", ""))).strip().upper()
        if ticker is None or not sector:
            continue
        known = _instant(row.get("knowledge_at", row.get("accepted_at")))
        if known is None or known > as_of:
            continue
        valid_from = row.get("valid_from", row.get("effective_from"))
        valid_to = row.get("valid_to", row.get("effective_to"))
        if valid_from is not None and date.fromisoformat(str(valid_from)[:10]) > as_of.date():
            continue
        if valid_to is not None and date.fromisoformat(str(valid_to)[:10]) <= as_of.date():
            continue
        current = selected.get(ticker)
        if current is None or (known, sector) > current:
            selected[ticker] = (known, sector)
    return {ticker: item[1] for ticker, item in selected.items()}


def _latest_by_symbol(frame: pl.DataFrame) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or "symbol" not in frame.columns:
        return {}
    return {str(row["symbol"]).upper(): dict(row) for row in frame.to_dicts()}


def _history_percentile(
    frame: pl.DataFrame,
    *,
    symbol: str,
    column: str,
    current: Any,
    as_of: date,
    grain: str,
) -> tuple[float | None, tuple[str, ...]]:
    if column not in frame.columns or current is None:
        return None, ("INSUFFICIENT_COMPONENT_DATA",)
    observations = [
        Observation(row["date"], float(row[column]))
        for row in frame.filter(pl.col("symbol") == symbol).select("date", column).to_dicts()
        if row.get(column) is not None
    ]
    result = midrank_percentile(current, observations, as_of=as_of, grain=grain)
    return result.score, result.reason_codes


def _technical_contexts(
    *,
    price_frame: pl.DataFrame,
    rs_frame: pl.DataFrame,
    identity: Mapping[str, str],
    as_of: datetime,
) -> list[dict[str, Any]]:
    latest_price = _latest_by_symbol(
        price_frame.sort("date").group_by("symbol", maintain_order=True).tail(1)
    )
    latest_rs = _latest_by_symbol(
        rs_frame.sort("date").group_by("symbol", maintain_order=True).tail(1)
    )
    output: list[dict[str, Any]] = []
    for cik, ticker in sorted(identity.items()):
        price = latest_price.get(ticker)
        rs = latest_rs.get(ticker)
        if price is None or rs is None:
            continue
        event_date = price.get("date")
        if not isinstance(event_date, date):
            event_date = date.fromisoformat(str(event_date)[:10])
        ordinary_percentile, ordinary_reasons = _history_percentile(
            rs_frame,
            symbol=ticker,
            column="ordinary_rs_3m_slope_4w",
            current=rs.get("ordinary_rs_3m_slope_4w"),
            as_of=event_date,
            grain="weekly",
        )
        market_percentile, market_reasons = _history_percentile(
            rs_frame,
            symbol=ticker,
            column="mansfield_market_slope_4w",
            current=rs.get("mansfield_market_slope_4w"),
            as_of=event_date,
            grain="weekly",
        )
        sector_percentile, sector_reasons = _history_percentile(
            rs_frame,
            symbol=ticker,
            column="mansfield_sector_slope_4w",
            current=rs.get("mansfield_sector_slope_4w"),
            as_of=event_date,
            grain="weekly",
        )
        volume_percentile, volume_reasons = _history_percentile(
            price_frame,
            symbol=ticker,
            column="signed_volume_ratio_20d",
            current=price.get("signed_volume_ratio_20d"),
            as_of=event_date,
            grain="daily",
        )
        volatility = price.get("volatility_20d")
        prior_volatility = price.get("prior_volatility_20d")
        median_volume = price.get("median_volume_20d")
        prior_median_volume = price.get("prior_median_volume_20d")
        ma20_slope = price.get("ma20_slope_5d")
        close = price.get("close")
        ma20 = price.get("ma20")
        output.append(
            {
                **price,
                **rs,
                "issuer_cik": cik,
                "ticker": ticker,
                "date": event_date,
                "knowledge_at": price.get("available_at", as_of),
                "ordinary_rs_slope_percentile": ordinary_percentile,
                "mansfield_market_slope_percentile": market_percentile,
                "mansfield_sector_slope_percentile": sector_percentile,
                "signed_volume_prior_percentile": volume_percentile,
                "volatility_contraction": (
                    volatility is not None
                    and prior_volatility is not None
                    and float(volatility) <= 0.80 * float(prior_volatility)
                ),
                "volume_dryup": (
                    median_volume is not None
                    and prior_median_volume is not None
                    and float(median_volume) <= 0.80 * float(prior_median_volume)
                ),
                "ma20_flattening": (
                    ma20_slope is not None
                    and close is not None
                    and float(close) > 0
                    and abs(float(ma20_slope)) <= 0.001 * float(close)
                ),
                "close_above_ma20": (
                    close is not None and ma20 is not None and float(close) >= float(ma20)
                ),
                "quality_flags": sorted(
                    {
                        *ordinary_reasons,
                        *market_reasons,
                        *sector_reasons,
                        *volume_reasons,
                    }
                ),
            }
        )
    return output


def _read_prior(path: Path | None) -> dict[str, Mapping[str, Any]]:
    if path is None:
        return {}
    rows = _read_rows(path)
    return {
        str(row.get("issuer_cik", row.get("cik"))): row
        for row in rows
        if row.get("issuer_cik", row.get("cik"))
    }


def _files_equal(left: Path, right: Path) -> bool:
    left_files = sorted(path.relative_to(left) for path in left.rglob("*") if path.is_file())
    right_files = sorted(path.relative_to(right) for path in right.rglob("*") if path.is_file())
    return left_files == right_files and all(
        hashlib.sha256((left / path).read_bytes()).digest()
        == hashlib.sha256((right / path).read_bytes()).digest()
        for path in left_files
    )


def _write_snapshot(
    output_root: Path,
    *,
    run_id: str,
    as_of: datetime,
    artifacts: Mapping[str, bytes],
    parquet_artifacts: Mapping[str, list[dict[str, Any]]],
) -> None:
    """Publish an immutable generation and switch its manifest last."""

    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".daily-stage-", dir=output_root) as temporary:
        stage = Path(temporary)
        for relative, rows in parquet_artifacts.items():
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            pl.DataFrame(rows).write_parquet(target, compression="uncompressed")
        for relative, content in artifacts.items():
            source = stage / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(content)
        snapshot_relative = Path("snapshots") / run_id
        snapshot_target = output_root / snapshot_relative
        snapshot_target.parent.mkdir(parents=True, exist_ok=True)
        if snapshot_target.exists():
            if not _files_equal(stage, snapshot_target):
                raise DailyPipelineError("runId already exists with different output bytes")
        else:
            os.replace(stage, snapshot_target)

    inventory = []
    for path in sorted(snapshot_target.rglob("*")):
        if path.is_file():
            inventory.append(
                {
                    "path": (snapshot_relative / path.relative_to(snapshot_target)).as_posix(),
                    "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    publication = _canonical_json(
        {
            "schemaVersion": "1.0.0",
            "runId": run_id,
            "asOf": as_of,
            "artifacts": inventory,
        }
    )
    temporary_manifest = output_root / ".manifest.json.tmp"
    with temporary_manifest.open("wb") as stream:
        stream.write(publication)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary_manifest, output_root / "manifest.json")


def run_daily_pipeline(manifest_path: Path) -> DailyRunResult:
    """Run the bounded offline daily slice from a verified daily manifest."""

    # Imported here so manifest verification completes before any pipeline IO.
    from insider_turning_engine.domain import daily_manifest

    loader = getattr(
        daily_manifest,
        "load_daily_manifest",
        daily_manifest.load_daily_input_manifest,
    )
    manifest: Any = loader(manifest_path)
    run_id = str(manifest.run_id)
    as_of = _as_utc(manifest.as_of, name="manifest as_of")
    output_root = (
        manifest.resolved_output_root()
        if hasattr(manifest, "resolved_output_root")
        else Path(manifest.output_root)
    )
    inputs = {
        name: (
            manifest.resolved_input(name)
            if hasattr(manifest, "resolved_input")
            else getattr(artifact, "path", artifact)
        )
        for name, artifact in manifest.inputs.items()
    }
    canonical_path = _artifact_path(
        inputs,
        "canonicalTransactions",
        "canonical_transactions",
        "transactions",
        "canonical",
        required=True,
    )
    assert canonical_path is not None
    canonical_raw = _read_rows(canonical_path)
    records, flat = _canonical_records(canonical_raw)
    _reject_future_rows(flat, as_of=as_of, source="canonical transactions")

    quality_path = _artifact_path(inputs, "qualityEvidence", required=True)
    assert quality_path is not None
    quality_evidence = _read_object(quality_path, label="quality evidence")
    evidence_run_id = quality_evidence.get("runId")
    if evidence_run_id is not None and evidence_run_id != run_id:
        raise DailyPipelineError("quality evidence runId does not match manifest")
    evidence_as_of = quality_evidence.get("asOf")
    if evidence_as_of is not None and _as_utc(evidence_as_of, name="quality asOf") != as_of:
        raise DailyPipelineError("quality evidence asOf does not match manifest")

    batch_path = _artifact_path(inputs, "secBatch", "sec_batch", "sec", "batch")
    batch_records: list[CanonicalTransaction] = []
    if batch_path is not None:
        batch_raw = _read_sec_batch(batch_path)
        batch_records, batch_flat = _canonical_records(batch_raw)
        _reject_future_rows(batch_flat, as_of=as_of, source="SEC batch")
        if len(batch_records) != len(batch_raw):
            raise DailyPipelineError("SEC batch must contain model-valid canonical transactions")
        if any(record.quality.status is QualityStatus.QUARANTINED for record in batch_records):
            raise DailyPipelineError("SEC batch contains quarantined rows")

    effective_records = records
    canonical_history = records
    if records or batch_records:
        if flat and len(records) != len(canonical_raw):
            raise DailyPipelineError("canonical history cannot mix typed and flattened rows")
        resolution = resolve_amendments([*records, *batch_records], as_of=as_of)
        if resolution.quarantines:
            raise DailyPipelineError("canonical amendment resolution produced quarantined rows")
        canonical_history = list(resolution.all_revisions)
        effective_records = list(resolution.effective_records)
        flat = [_flat_record(record) for record in effective_records]
    if batch_records:
        represented = {record.source.source_row_key for record in canonical_history}
        if not all(record.source.source_row_key in represented for record in batch_records):
            raise DailyPipelineError(
                "not every SEC batch row is represented in canonical transactions"
            )

    identity_path = _artifact_path(inputs, "identities", "identity", "issuer_identity")
    market_path = _artifact_path(inputs, "marketBars", "market", "market_bars", "prices")
    identity_rows = _read_rows(identity_path) if identity_path else []
    identity = _ticker_by_cik(identity_rows, as_of=as_of)
    sector_by_ticker = _sector_by_ticker(identity_rows, identity, as_of=as_of)
    market_rows = _read_rows(market_path) if market_path else []
    _reject_future_rows(market_rows, as_of=as_of, source="market")
    price_facts: dict[str, dict[str, Any]] = {}
    scoring_context: list[dict[str, Any]] = []
    market_error: str | None = None
    if market_rows:
        try:
            market_frame = pl.DataFrame(market_rows)
            full_price = price_features(market_frame, as_of=as_of)
            price_facts = _latest_by_symbol(latest_price_facts(market_frame, as_of=as_of))
            full_rs = relative_strength_features(
                market_frame,
                as_of=as_of,
                sector_by_symbol=sector_by_ticker,
                universe_symbols=tuple(identity.values()),
            )
            scoring_context = _technical_contexts(
                price_frame=full_price,
                rs_frame=full_rs,
                identity=identity,
                as_of=as_of,
            )
        except (TypeError, ValueError, pl.exceptions.PolarsError) as exc:
            market_error = f"MARKET_FEATURES_UNAVAILABLE:{type(exc).__name__}"

    prior_state = _read_prior(_artifact_path(inputs, "priorState", "prior_state", "state"))
    qualified = [row for row in flat if _qualified(row, as_of=as_of)]
    issuers = sorted(
        {str(row.get("issuer_cik", "")).zfill(10) for row in qualified if row.get("issuer_cik")}
    )
    engine = ScoreEngine(as_of=as_of, run_id=run_id)
    mapped_issuers = {cik for cik in issuers if identity.get(cik)}
    priced_issuers = {cik for cik in mapped_issuers if identity[cik] in price_facts}
    market_coverage = len(priced_issuers) / len(mapped_issuers) if mapped_issuers else 0.0
    latest_candidate_session = max(
        (
            row["date"]
            for ticker in identity.values()
            if (row := price_facts.get(ticker)) is not None and isinstance(row.get("date"), date)
        ),
        default=None,
    )
    required_benchmarks = {"SPY", *sector_by_ticker.values()}
    benchmark_fresh = latest_candidate_session is not None and all(
        (facts := price_facts.get(symbol)) is not None
        and isinstance(facts.get("date"), date)
        and facts["date"] >= latest_candidate_session
        for symbol in required_benchmarks
    )
    sec_evidence = quality_evidence.get("sec", {})
    market_evidence = quality_evidence.get("market", {})
    core_evidence = quality_evidence.get("coreBranchCoverage", {})
    if not isinstance(sec_evidence, Mapping) or not isinstance(market_evidence, Mapping):
        raise DailyPipelineError("quality evidence sec and market fields must be objects")

    def evidence_count(source: Mapping[str, Any], name: str, default: int = 0) -> int:
        value = source.get(name, default)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise DailyPipelineError(f"quality evidence {name} must be a non-negative integer")
        return value

    sec_records = evidence_count(sec_evidence, "recordCount", len(batch_records))
    sec_quarantines = evidence_count(sec_evidence, "quarantineCount")
    sec_failures = evidence_count(sec_evidence, "failureCount")
    if "recordCount" in sec_evidence and sec_records != len(canonical_history):
        raise DailyPipelineError(
            "quality evidence SEC recordCount does not match canonical history"
        )
    parse_measurement = _measurement(
        sec_records,
        sec_records + sec_quarantines + sec_failures,
        0.995,
    )
    coverage_measurement = _measurement(len(priced_issuers), len(mapped_issuers), 0.90)
    if isinstance(core_evidence, Mapping):
        core_numerator = (
            0
            if core_evidence.get("numerator") is None
            else evidence_count(core_evidence, "numerator")
        )
        core_denominator = (
            0
            if core_evidence.get("denominator") is None
            else evidence_count(core_evidence, "denominator")
        )
    else:
        core_numerator = core_denominator = 0
    core_measurement = _measurement(core_numerator, core_denominator, 0.85)
    evidence_benchmark_fresh = market_evidence.get("benchmarkFresh")
    if evidence_benchmark_fresh is not None and not isinstance(evidence_benchmark_fresh, bool):
        raise DailyPipelineError("quality evidence benchmarkFresh must be boolean")
    benchmark_fresh = benchmark_fresh and evidence_benchmark_fresh is not False

    backtest_path = _artifact_path(inputs, "backtestReport")
    backtest_gate = None
    backtest_lineage_valid = False
    backtest_observed_outcomes = 0
    if backtest_path is not None:
        backtest_report = _read_object(backtest_path, label="backtest report")
        formal = backtest_report.get("formalReport", {})
        if isinstance(formal, Mapping):
            gate = formal.get("gate")
            provenance = formal.get("scoring_provenance")
            if isinstance(gate, Mapping) and isinstance(provenance, Mapping):
                raw_observed = gate.get("observed_eligible_oos_outcomes", 0)
                if (
                    isinstance(raw_observed, bool)
                    or not isinstance(raw_observed, int)
                    or raw_observed < 0
                ):
                    raise DailyPipelineError(
                        "backtest observed eligible outcomes must be a non-negative integer"
                    )
                backtest_observed_outcomes = raw_observed
                backtest_lineage_valid = (
                    backtest_report.get("evaluationStage") == "sealed-oos"
                    and backtest_report.get("scoreVersion") == engine.score_version
                    and provenance.get("score_version") == engine.score_version
                    and provenance.get("score_config_hash") == engine.score_config_hash
                    and provenance.get("methodology_hash") == engine.methodology_hash
                    and provenance.get("methodology_status") == "FROZEN"
                    and backtest_observed_outcomes >= 200
                )
                if backtest_lineage_valid:
                    backtest_gate = gate.get("status")

    issues: list[str] = []
    if parse_measurement["result"] != "PASS":
        issues.append("SEC_PARSE_QUALITY_FAILED")
    if coverage_measurement["result"] != "PASS":
        issues.append("MARKET_COVERAGE_FAILED")
    if core_measurement["result"] != "PASS":
        issues.append("CORE_BRANCH_COVERAGE_NOT_VERIFIED")
    if not benchmark_fresh:
        issues.append("STALE_OR_MISSING_BENCHMARK")
    if not engine.methodology_complete:
        issues.append("SCORING_METHODOLOGY_INCOMPLETE")
    if backtest_path is not None and not backtest_lineage_valid:
        issues.append("BACKTEST_LINEAGE_OR_SAMPLE_INVALID")
    if backtest_gate != "PASS":
        issues.append("BACKTEST_GATE_NOT_PASS")
    operational_pass = (
        parse_measurement["result"] == "PASS"
        and coverage_measurement["result"] == "PASS"
        and core_measurement["result"] == "PASS"
        and benchmark_fresh
    )
    release_pass = operational_pass and engine.methodology_complete and backtest_gate == "PASS"
    disposition = "PASS" if release_pass else "DEGRADED" if operational_pass else "BLOCKED"
    export_quality = {
        "disposition": disposition,
        "canonicalValid": sec_quarantines == 0 and sec_failures == 0,
        "methodologyComplete": engine.methodology_complete,
        "benchmarkFresh": benchmark_fresh,
        "parseSuccess": parse_measurement,
        "marketCoverage": coverage_measurement,
        "coreBranchCoverage": core_measurement,
        "issues": sorted(set(issues)),
    }
    quality = {
        "schemaVersion": "1.0.0",
        "runId": run_id,
        "asOf": as_of,
        "canonicalValid": True,
        "quarantineCount": sec_quarantines,
        "effectiveTransactionCount": len(effective_records) if effective_records else len(flat),
        "insiderActiveIssuerCount": len(issuers),
        "mappedIssuerCount": len(mapped_issuers),
        "pricedIssuerCount": len(priced_issuers),
        "marketCoverage": round(market_coverage, 6),
        "coveragePass": bool(mapped_issuers) and market_coverage >= 0.90,
        "benchmarkFresh": benchmark_fresh,
        "marketFeatureError": market_error,
        "methodologyComplete": engine.methodology_complete,
        "methodologyStatus": engine.methodology_status,
        "backtestGate": backtest_gate,
        "backtestObservedEligibleOutcomes": backtest_observed_outcomes,
        "backtestLineageValid": backtest_lineage_valid,
        "disposition": disposition,
        "issues": sorted(set(issues)),
    }
    alert_quality = {
        "canonical_valid": True,
        "stale_benchmark": not benchmark_fresh,
        "parse_success_rate": parse_measurement["rate"] or 0.0,
        "market_data_coverage_rate": market_coverage,
        "core_branch_coverage_rate": core_measurement["rate"] or 0.0,
        "quality_gate_passed": release_pass,
    }
    active = set(issuers)
    effective_for_scoring: list[Any] = (
        [record for record in effective_records if record.issuer.cik in active]
        if effective_records
        else [row for row in flat if str(row.get("issuer_cik", "")).zfill(10) in active]
    )
    try:
        scoring = assemble_daily_scores(
            effective_for_scoring,
            scoring_context,
            identity,
            prior_state,
            as_of=as_of,
            run_id=run_id,
            quality=alert_quality,
        )
    except DailyScoringError as exc:
        raise DailyPipelineError(str(exc)) from exc
    components_output = list(scoring.components)
    signals = list(scoring.signals)
    alerts = list(scoring.alerts)
    next_state = list(scoring.states)
    next_scores = [
        {"issuer_cik": signal["issuer_cik"], "total_score": signal.get("total_score")}
        for signal in signals
    ]

    canonical_output = (
        [record.canonical_dump() for record in canonical_history] if canonical_history else flat
    )
    effective_output = (
        [record.canonical_dump() for record in effective_records] if effective_records else flat
    )
    dashboard_input = build_dashboard_input(
        run_id=run_id,
        as_of=as_of,
        records=effective_records,
        identity_rows=identity_rows,
        ticker_by_cik=identity,
        sector_by_ticker=sector_by_ticker,
        scoring_context=scoring_context,
        components=components_output,
        signals=signals,
        quality=export_quality,
        score_version=engine.score_version,
    )
    artifacts = {
        "components/components.json": _canonical_json(components_output),
        "warehouse/signals.json": _canonical_json(signals),
        "warehouse/dashboard-input.json": _canonical_json(dashboard_input),
        "alerts/candidates.json": _canonical_json(alerts),
        "state/prior-state.json": _canonical_json(next_state),
        "state/prior-scores.json": _canonical_json(next_scores),
        "quality/quality.json": _canonical_json(quality),
    }
    if batch_path is not None:
        artifacts["staging/sec-batch-committed.sha256"] = (
            hashlib.sha256(batch_path.read_bytes()).hexdigest() + "\n"
        ).encode("ascii")
    _write_snapshot(
        output_root,
        run_id=run_id,
        as_of=as_of,
        artifacts=artifacts,
        parquet_artifacts={
            "canonical/transactions.parquet": canonical_output,
            "canonical/effective-transactions.parquet": effective_output,
        },
    )
    return DailyRunResult(
        run_id=run_id,
        status="SUCCEEDED",
        output_root=output_root,
        effective_transactions=len(flat),
        signals=tuple(signals),
        alerts=tuple(alerts),
    )
