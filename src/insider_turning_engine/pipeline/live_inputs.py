"""Deterministic preparation of point-in-time inputs for a live daily run.

This module is deliberately a materialization boundary.  It consumes only
completed normalized artifacts and writes a small, content-addressed input
bundle; it neither fetches providers nor writes provider raw/cache data.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, cast

import polars as pl
from pydantic import ValidationError

from insider_turning_engine.domain.daily_manifest import DailyInputManifest
from insider_turning_engine.domain.models import CanonicalTransaction, TableType
from insider_turning_engine.normalization.amendments import resolve_amendments
from insider_turning_engine.normalization.identity import (
    evaluate_security_universe,
    map_sic_to_sector_etf,
    normalize_cik,
    normalize_ticker,
)


class LiveInputPreparationError(ValueError):
    """Raised when completed artifacts cannot safely form a live input bundle."""


@dataclass(frozen=True, slots=True)
class LiveInputPreparation:
    """Paths and point-in-time selections produced by :func:`prepare_live_inputs`."""

    root: Path
    manifest_path: Path
    canonical_path: Path
    identities_path: Path
    prior_state_path: Path
    market_bars_path: Path
    quality_evidence_path: Path
    sec_batch_path: Path | None
    backtest_report_path: Path | None
    symbols_path: Path
    benchmarks_path: Path
    active_issuers: tuple[str, ...]
    symbols: tuple[str, ...]
    benchmarks: tuple[str, ...]


_RUN_ID = re.compile(r"^run_[A-Za-z0-9_-]{8,64}$")
_COMMON_STOCK = re.compile(
    r"\b(?:common[ _-]?(?:stock|shares?)|ordinary[ _-]?shares?)\b",
    re.IGNORECASE,
)
_SUPPORTED_SUFFIXES = frozenset({".json", ".jsonl", ".ndjson", ".parquet", ".pq"})


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise LiveInputPreparationError("timestamps must be timezone-aware")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _canonical_json(value: Any) -> bytes:
    try:
        encoded = json.dumps(_json_value(value), sort_keys=True, separators=(",", ":")) + "\n"
    except (TypeError, ValueError) as exc:
        raise LiveInputPreparationError("input is not JSON serializable") from exc
    return encoded.encode("utf-8")


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _as_utc(value: Any, *, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min, tzinfo=UTC)
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise LiveInputPreparationError(f"{label} must be an ISO timestamp") from exc
    else:
        raise LiveInputPreparationError(f"{label} must be an ISO timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveInputPreparationError(f"{label} must be timezone-aware")
    return parsed.astimezone(UTC)


def _as_date(value: Any, *, label: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError) as exc:
        raise LiveInputPreparationError(f"{label} must be an ISO date") from exc


def _get(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return None


def _read_rows(path: Path, *, label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise LiveInputPreparationError(f"{label} is not a file: {path}")
    if path.suffix.lower() not in _SUPPORTED_SUFFIXES:
        raise LiveInputPreparationError(f"{label} has unsupported format: {path.suffix}")
    if path.suffix.lower() in {".parquet", ".pq"}:
        try:
            return [dict(row) for row in pl.read_parquet(path).to_dicts()]
        except (OSError, pl.exceptions.PolarsError) as exc:
            raise LiveInputPreparationError(f"{label} parquet is unreadable") from exc
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LiveInputPreparationError(f"cannot read {label}: {path}") from exc
    if not text.strip():
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        if not all(isinstance(row, Mapping) for row in parsed):
            raise LiveInputPreparationError(f"{label} JSON array rows must be objects")
        return [dict(cast(Mapping[str, Any], row)) for row in parsed]
    if isinstance(parsed, Mapping):
        wrapped_rows = parsed.get("records", parsed.get("transactions", parsed.get("rows")))
        if isinstance(wrapped_rows, list) and all(isinstance(row, Mapping) for row in wrapped_rows):
            return [dict(cast(Mapping[str, Any], row)) for row in wrapped_rows]
        raise LiveInputPreparationError(f"{label} JSON must contain an array of rows")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LiveInputPreparationError(f"{label} has invalid JSONL at line {number}") from exc
        if not isinstance(row, Mapping):
            raise LiveInputPreparationError(f"{label} JSONL row {number} must be an object")
        rows.append(dict(row))
    return rows


def _load_sec_envelope(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveInputPreparationError("SEC envelope is unreadable or invalid JSON") from exc
    if not isinstance(value, Mapping):
        raise LiveInputPreparationError("SEC envelope must be an object")
    required = {"records", "quarantines", "failures"}
    missing = required - set(value)
    if missing:
        raise LiveInputPreparationError(f"SEC envelope missing fields: {sorted(missing)}")
    records = value["records"]
    quarantines = value["quarantines"]
    failures = value["failures"]
    if not isinstance(records, list) or any(not isinstance(row, Mapping) for row in records):
        raise LiveInputPreparationError("SEC envelope records must be an array of objects")
    if not isinstance(quarantines, list) or not isinstance(failures, list):
        raise LiveInputPreparationError("SEC envelope quarantines and failures must be arrays")
    if quarantines or failures:
        raise LiveInputPreparationError("SEC envelope contains quarantine or failure evidence")
    # Re-serialize the validated producer envelope so the prepared bundle has
    # deterministic bytes independent of producer whitespace/key order.
    stable = {
        "failures": [],
        "quarantines": [],
        "records": [dict(cast(Mapping[str, Any], row)) for row in records],
    }
    return stable["records"], stable


def _typed_records(rows: Iterable[Mapping[str, Any]], *, label: str) -> list[CanonicalTransaction]:
    output: list[CanonicalTransaction] = []
    for index, row in enumerate(rows):
        try:
            output.append(CanonicalTransaction.model_validate(row))
        except ValidationError as exc:
            raise LiveInputPreparationError(f"{label} row {index} fails canonical schema") from exc
    return output


def _record_key(record: CanonicalTransaction) -> tuple[str, str]:
    return record.transaction_id, record.revision_id


def _merge_records(records: Iterable[CanonicalTransaction]) -> list[CanonicalTransaction]:
    """Deduplicate byte-identical revisions without collapsing amendments."""

    selected: dict[tuple[str, str], CanonicalTransaction] = {}
    fingerprints: dict[tuple[str, str], bytes] = {}
    for record in records:
        key = _record_key(record)
        encoded = _canonical_json(record.canonical_dump())
        previous = fingerprints.get(key)
        if previous is not None and previous != encoded:
            raise LiveInputPreparationError(
                "canonical revision identity has conflicting content; refusing ambiguous merge"
            )
        selected.setdefault(key, record)
        fingerprints.setdefault(key, encoded)
    return [selected[key] for key in sorted(selected)]


def _qualified(record: CanonicalTransaction, *, as_of: datetime) -> bool:
    return (
        record.timestamps.knowledge_at <= as_of
        and record.transaction.transaction_date <= as_of.date()
        and record.transaction.transaction_date >= as_of.date() - timedelta(days=365)
        and record.transaction.code in {"P", "S"}
        and record.security.table_type is TableType.NON_DERIVATIVE
        and record.lifecycle.status.value == "ACTIVE"
    )


def _is_common_stock_evidence(row: Mapping[str, Any]) -> bool:
    value = _get(row, "security_type", "securityType", "instrument_type", "instrumentType")
    return isinstance(value, str) and _COMMON_STOCK.search(value) is not None


def _identity_candidates(
    rows: Iterable[Mapping[str, Any]],
    *,
    as_of: datetime,
    common_stock_titles: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    filing_titles = common_stock_titles or {}
    selected: dict[str, tuple[datetime, bytes, dict[str, Any]]] = {}
    for source in rows:
        row = dict(source)
        cik = normalize_cik(_get(row, "cik", "issuer_cik", "issuerCik", "CIK"))
        ticker = normalize_ticker(_get(row, "ticker", "symbol", "issuerTradingSymbol"))
        known_value = _get(row, "knowledge_at", "knowledgeAt", "accepted_at", "acceptedAt")
        if cik is None or ticker is None or known_value is None:
            continue
        known = _as_utc(known_value, label="identity knowledge_at")
        if known > as_of:
            continue
        valid_from = _get(row, "valid_from", "validFrom", "effective_from", "effectiveFrom")
        valid_to = _get(row, "valid_to", "validTo", "effective_to", "effectiveTo")
        if (
            valid_from is not None
            and _as_date(valid_from, label="identity valid_from") > as_of.date()
        ):
            continue
        if valid_to is not None and _as_date(valid_to, label="identity valid_to") <= as_of.date():
            continue
        # The official SEC ticker/exchange map does not contain a security
        # type.  It may therefore supply exchange/ticker identity only when a
        # point-in-time non-derivative ownership filing independently supplies
        # a common-stock title for the same issuer.  No security type is
        # inferred from a ticker or company name alone.
        filing_title = filing_titles.get(cik)
        has_explicit_common_stock = _is_common_stock_evidence(row)
        has_filing_common_stock = bool(
            filing_title and _COMMON_STOCK.search(filing_title)
        )
        universe_row = dict(row)
        if has_filing_common_stock:
            universe_row.setdefault("security_title", filing_title)
        if (
            not (has_explicit_common_stock or has_filing_common_stock)
            or not evaluate_security_universe(universe_row, as_of=as_of).include
        ):
            continue
        sector = _get(row, "sector_etf", "sectorEtf")
        if not isinstance(sector, str) or not sector.strip():
            sector = map_sic_to_sector_etf(_get(row, "sic", "sic_code", "sicCode")).sector_etf
        sector_value = str(sector).strip().upper()
        security_type = _get(
            row,
            "security_type",
            "securityType",
            "instrument_type",
            "instrumentType",
        )
        normalized = {
            "cik": cik,
            "ticker": ticker,
            "exchange": str(_get(row, "exchange", "primary_exchange", "primaryExchange") or "")
            .strip()
            .upper(),
            "security_type": (
                str(security_type).strip()
                if security_type is not None
                else "Common Stock"
            ),
            "security_type_source": (
                "identity_row"
                if has_explicit_common_stock
                else "sec_filing_non_derivative_title"
            ),
            "security_title_evidence": (
                str(security_type).strip()
                if has_explicit_common_stock
                else filing_title
            ),
            "knowledge_at": _json_value(known),
            "sector_etf": sector_value,
        }
        for name in ("name", "sic", "country", "valid_from", "valid_to"):
            camel_name = "".join(
                part.title() if i else part for i, part in enumerate(name.split("_"))
            )
            value = _get(row, name, camel_name)
            if value is not None:
                normalized[name] = _json_value(value)
        encoded = _canonical_json(normalized)
        current = selected.get(cik)
        if current is None or (known, encoded) > (current[0], current[1]):
            selected[cik] = (known, encoded, normalized)
    return {cik: selected[cik][2] for cik in sorted(selected)}


def _common_stock_titles(
    records: Iterable[CanonicalTransaction], *, as_of: datetime
) -> dict[str, str]:
    selected: dict[str, tuple[datetime, str]] = {}
    for record in records:
        title = record.security.title.strip()
        if (
            record.timestamps.knowledge_at > as_of
            or record.security.table_type is not TableType.NON_DERIVATIVE
            or _COMMON_STOCK.search(title) is None
        ):
            continue
        candidate = (record.timestamps.knowledge_at, title)
        current = selected.get(record.issuer.cik)
        if current is None or candidate > current:
            selected[record.issuer.cik] = candidate
    return {cik: value[1] for cik, value in sorted(selected.items())}


def _read_identity_rows(value: Iterable[Mapping[str, Any]] | str | Path) -> list[dict[str, Any]]:
    if isinstance(value, (str, Path)):
        return _read_rows(Path(value), label="identity rows")
    rows = list(value)
    if any(not isinstance(row, Mapping) for row in rows):
        raise LiveInputPreparationError("identity rows must be mappings")
    return [dict(row) for row in rows]


def _load_quality(path: Path, *, as_of: datetime) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveInputPreparationError(
            "market quality output is unreadable or invalid JSON"
        ) from exc
    if not isinstance(value, Mapping):
        raise LiveInputPreparationError("market quality output must be an object")
    if value.get("schemaVersion") != "1.0.0":
        raise LiveInputPreparationError("market quality output schemaVersion must be 1.0.0")
    raw_as_of = value.get("asOf")
    if (
        not isinstance(raw_as_of, str)
        or _as_date(raw_as_of, label="market quality asOf") > as_of.date()
    ):
        raise LiveInputPreparationError(
            "market quality output asOf is invalid or later than run as_of"
        )
    failures = value.get("failures")
    if not isinstance(failures, Mapping):
        raise LiveInputPreparationError("market quality output failures must be an object")
    return dict(cast(Mapping[str, Any], value))


def _core_branch_coverage(path: str | Path | None) -> dict[str, Any]:
    """Extract branch evidence from pytest-cov JSON, never from an attestation."""

    if path is None:
        return {"numerator": None, "denominator": None, "rate": None, "status": "NOT_EVALUATED"}
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveInputPreparationError("core coverage JSON is unreadable or invalid") from exc
    if not isinstance(value, Mapping) or not isinstance(value.get("totals"), Mapping):
        raise LiveInputPreparationError("core coverage JSON must contain totals")
    totals = cast(Mapping[str, Any], value["totals"])
    numerator = totals.get("covered_branches")
    denominator = totals.get("num_branches")
    if (
        isinstance(numerator, bool)
        or isinstance(denominator, bool)
        or not isinstance(numerator, int)
        or not isinstance(denominator, int)
        or numerator < 0
        or denominator < 0
        or numerator > denominator
    ):
        raise LiveInputPreparationError(
            "core coverage totals must contain valid covered_branches and num_branches"
        )
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": round(numerator / denominator, 6) if denominator else None,
        "status": "EVALUATED",
    }


def _same_tree(left: Path, right: Path) -> bool:
    left_files = sorted(path.relative_to(left) for path in left.rglob("*") if path.is_file())
    right_files = sorted(path.relative_to(right) for path in right.rglob("*") if path.is_file())
    return left_files == right_files and all(
        (left / path).read_bytes() == (right / path).read_bytes() for path in left_files
    )


def prepare_live_inputs(
    *,
    canonical_sources: Iterable[str | Path],
    sec_envelope: str | Path,
    identity_rows: Iterable[Mapping[str, Any]] | str | Path,
    prior_state_file: str | Path,
    market_bars_file: str | Path,
    market_quality_file: str | Path,
    core_coverage_file: str | Path | None = None,
    backtest_report_file: str | Path | None = None,
    as_of: datetime,
    run_id: str,
    work_root: str | Path,
) -> LiveInputPreparation:
    """Prepare a deterministic, self-contained daily manifest input bundle.

    ``canonical_sources`` may be JSON, JSONL, or Parquet.  Every row is
    model-validated and source content hashes are therefore checked by the
    canonical schema before any output directory is published.
    """

    if not _RUN_ID.fullmatch(run_id):
        raise LiveInputPreparationError("run_id must be a safe run_ identifier")
    point = _as_utc(as_of, label="as_of")
    source_paths = [Path(value) for value in canonical_sources]
    if not source_paths:
        raise LiveInputPreparationError("at least one canonical source is required")
    source_rows = [
        row for path in sorted(source_paths, key=lambda item: str(item.resolve()))
        for row in _read_rows(path, label="canonical source")
    ]
    sec_path = Path(sec_envelope)
    sec_rows, sec_stable = _load_sec_envelope(sec_path)
    source_records = _merge_records(
        _typed_records(source_rows, label="canonical source")
    )
    batch_records = _merge_records(_typed_records(sec_rows, label="SEC envelope"))
    records = _merge_records([*source_records, *batch_records])
    resolution = resolve_amendments(records, as_of=point)
    # The canonical interchange projection deliberately excludes optional SEC
    # predecessor metadata.  When a serialized amendment cannot be linked,
    # retain its typed source revision rather than silently dropping it; only
    # the independently resolved effective view drives active-issuer selection.
    all_revisions = sorted(
        resolution.all_revisions if not resolution.quarantines else records,
        key=_record_key,
    )
    active_issuers = tuple(
        sorted(
            {
                record.issuer.cik
                for record in resolution.effective_records
                if _qualified(record, as_of=point)
            }
        )
    )

    identities = _identity_candidates(
        _read_identity_rows(identity_rows),
        as_of=point,
        common_stock_titles=_common_stock_titles(
            resolution.effective_records,
            as_of=point,
        ),
    )
    selected_identities = [identities[cik] for cik in active_issuers if cik in identities]
    symbols = tuple(sorted({str(row["ticker"]) for row in selected_identities}))
    sector_etfs = {
        str(row["sector_etf"])
        for row in selected_identities
        if str(row.get("sector_etf", "")).strip() and str(row["sector_etf"]).upper() != "UNKNOWN"
    }
    benchmarks = tuple(sorted({"SPY", *sector_etfs}))

    prior_rows = _read_rows(Path(prior_state_file), label="prior state")
    market_path = Path(market_bars_file)
    if not market_path.is_file():
        raise LiveInputPreparationError("market bars is not a file")
    market_quality = _load_quality(Path(market_quality_file), as_of=point)
    core_branch_coverage = _core_branch_coverage(core_coverage_file)
    backtest_report: dict[str, Any] | None = None
    if backtest_report_file is not None:
        try:
            candidate = json.loads(Path(backtest_report_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LiveInputPreparationError(
                "backtest report is unreadable or invalid JSON"
            ) from exc
        if not isinstance(candidate, Mapping):
            raise LiveInputPreparationError("backtest report must be a JSON object")
        backtest_report = dict(candidate)
    quality_evidence = {
        "schemaVersion": "1.0.0",
        "runId": run_id,
        "asOf": _json_value(point),
        "sec": {
            "recordCount": len(all_revisions),
            "quarantineCount": len(resolution.quarantines),
            "failureCount": 0,
            "status": "PASS" if not resolution.quarantines else "QUARANTINED",
        },
        "market": market_quality,
        "coreBranchCoverage": core_branch_coverage,
        "inputs": {
            "canonicalRecordCount": len(all_revisions),
            "amendmentQuarantineCount": len(resolution.quarantines),
            "activeIssuerCount": len(active_issuers),
            "selectedIdentityCount": len(selected_identities),
            "symbols": list(symbols),
            "benchmarks": list(benchmarks),
        },
    }

    root = Path(work_root).expanduser().resolve() / run_id
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".live-input-stage-", dir=root.parent) as temporary:
        stage = Path(temporary)
        inputs = stage / "inputs"
        inputs.mkdir()
        canonical_path = inputs / "canonical.json"
        identities_path = inputs / "identities.json"
        prior_path = inputs / "prior-state.json"
        sec_output = inputs / "sec-batch.json"
        quality_path = inputs / "quality-evidence.json"
        symbols_path = inputs / "symbols.txt"
        benchmarks_path = inputs / "benchmarks.txt"
        backtest_path = inputs / "backtest-report.json"
        # Keep history and the new batch disjoint at the manifest boundary.
        # Gate 1 owns the merge and can therefore prove that every batch row
        # became durable before writing its commit marker.
        canonical_path.write_bytes(
            _canonical_json([record.canonical_dump() for record in source_records])
        )
        identities_path.write_bytes(_canonical_json(selected_identities))
        prior_path.write_bytes(_canonical_json(prior_rows))
        sec_output.write_bytes(_canonical_json(sec_stable))
        quality_path.write_bytes(_canonical_json(quality_evidence))
        if backtest_report is not None:
            backtest_path.write_bytes(_canonical_json(backtest_report))
        symbols_path.write_text("\n".join(symbols) + ("\n" if symbols else ""), encoding="utf-8")
        benchmarks_path.write_text("\n".join(benchmarks) + "\n", encoding="utf-8")
        market_output = inputs / f"market-bars{market_path.suffix.lower()}"
        shutil.copyfile(market_path, market_output)
        artifacts = {
            "canonicalTransactions": canonical_path,
            "secBatch": sec_output,
            "marketBars": market_output,
            "identities": identities_path,
            "priorState": prior_path,
            "qualityEvidence": quality_path,
        }
        if backtest_report is not None:
            artifacts["backtestReport"] = backtest_path
        manifest_value = {
            "schemaVersion": "1.0.0",
            "runId": run_id,
            "asOf": _json_value(point),
            "outputRoot": "output",
            "inputs": {
                name: {"path": path.relative_to(stage).as_posix(), "sha256": _sha256(path)}
                for name, path in artifacts.items()
            },
        }
        manifest_path = stage / "daily-input-manifest.json"
        manifest_path.write_bytes(_canonical_json(manifest_value))
        # Validate relative paths and all artifact digests before publication.
        DailyInputManifest.load(manifest_path)
        if root.exists():
            if not _same_tree(stage, root):
                raise LiveInputPreparationError(
                    "run_id already exists with different prepared inputs"
                )
        else:
            os.replace(stage, root)

    return LiveInputPreparation(
        root=root,
        manifest_path=root / "daily-input-manifest.json",
        canonical_path=root / "inputs" / "canonical.json",
        identities_path=root / "inputs" / "identities.json",
        prior_state_path=root / "inputs" / "prior-state.json",
        market_bars_path=root / "inputs" / f"market-bars{market_path.suffix.lower()}",
        quality_evidence_path=root / "inputs" / "quality-evidence.json",
        sec_batch_path=root / "inputs" / "sec-batch.json",
        backtest_report_path=(
            root / "inputs" / "backtest-report.json"
            if backtest_report is not None
            else None
        ),
        symbols_path=root / "inputs" / "symbols.txt",
        benchmarks_path=root / "inputs" / "benchmarks.txt",
        active_issuers=active_issuers,
        symbols=symbols,
        benchmarks=benchmarks,
    )


# Descriptive alias for callers that use the daily pipeline nomenclature.
prepare_live_daily_inputs = prepare_live_inputs


__all__ = [
    "LiveInputPreparation",
    "LiveInputPreparationError",
    "prepare_live_daily_inputs",
    "prepare_live_inputs",
]
