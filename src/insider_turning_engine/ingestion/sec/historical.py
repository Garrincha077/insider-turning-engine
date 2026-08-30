"""Downloader and staging adapter for the SEC quarterly insider data sets.

The SEC bulk files are untrusted input.  This module deliberately keeps the
transport, archive, and table parsing boundaries small so they can be tested
with a fake ``httpx`` client without contacting the SEC.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath
from typing import Any

import httpx
import polars as pl

SEC_ARCHIVE_URL_TEMPLATE = (
    "https://www.sec.gov/files/dera/data/insider-transactions-data-sets/{year}q{quarter}.zip"
)
MIN_YEAR = 2006
MAX_RETRY_DELAY_SECONDS = 60.0
MAX_MEMBER_BYTES = 250 * 1024 * 1024
MAX_TOTAL_EXTRACTED_BYTES = 750 * 1024 * 1024
_COPY_CHUNK_BYTES = 1024 * 1024
_CONTACT_EMAIL_RE = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
)


class SECDownloadError(RuntimeError):
    """Raised when a quarterly archive cannot be downloaded."""


class UnsafeArchiveError(ValueError):
    """Raised when an archive contains an unsafe member name or type."""


@dataclass(frozen=True)
class DownloadResult:
    """Stable details of a downloaded (or cache-hit) archive."""

    year: int
    quarter: int
    url: str
    path: Path
    sha256: str
    size_bytes: int
    manifest_path: Path
    downloaded: bool


@dataclass(frozen=True)
class StageResult:
    """Paths and quality counts produced by :func:`stage_quarter`."""

    year: int
    quarter: int
    archive: DownloadResult
    partition_path: Path
    parquet_paths: tuple[Path, ...]
    quarantine_path: Path | None
    quarantined_rows: int
    manifest_path: Path


@dataclass(frozen=True)
class QuarantinedRow:
    table: str
    line_number: int
    reason: str
    raw: str


class RequestPacer:
    """A process-local pacer that keeps SEC requests at most six per second."""

    def __init__(
        self,
        requests_per_second: float = 6.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self.interval = 1.0 / requests_per_second
        self.sleeper = sleeper
        self._last_request: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if self._last_request is not None:
                delay = self.interval - (now - self._last_request)
                if delay > 0:
                    self.sleeper(delay)
                    now = time.monotonic()
            self._last_request = now


# A shared pacer is important when callers use several adapter instances in
# one process.  Tests can pass their own pacer (and a no-op sleeper).
_SEC_PACER = RequestPacer()


def validate_quarter(year: int, quarter: int) -> tuple[int, int]:
    """Validate and return a normalized SEC archive period."""

    if isinstance(year, bool) or not isinstance(year, int) or year < MIN_YEAR:
        raise ValueError(f"year must be an integer >= {MIN_YEAR}")
    if isinstance(quarter, bool) or not isinstance(quarter, int) or quarter not in (1, 2, 3, 4):
        raise ValueError("quarter must be one of 1, 2, 3, or 4")
    return year, quarter


def archive_url(year: int, quarter: int) -> str:
    """Return the official SEC bulk archive URL for a quarter."""

    year, quarter = validate_quarter(year, quarter)
    return SEC_ARCHIVE_URL_TEMPLATE.format(year=year, quarter=quarter)


def list_quarters(start_year: int = MIN_YEAR, end_year: int | None = None) -> list[tuple[int, int]]:
    """Purely enumerate valid year/quarter pairs (inclusive)."""

    if isinstance(start_year, bool) or not isinstance(start_year, int) or start_year < MIN_YEAR:
        raise ValueError(f"start_year must be an integer >= {MIN_YEAR}")
    if end_year is None:
        end_year = start_year
    if isinstance(end_year, bool) or not isinstance(end_year, int) or end_year < start_year:
        raise ValueError("end_year must be an integer >= start_year")
    return [(year, quarter) for year in range(start_year, end_year + 1) for quarter in range(1, 5)]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_sec_user_agent(user_agent: str) -> str:
    """Return a SEC-compliant identifier with a project name and contact email."""

    if not isinstance(user_agent, str):
        raise ValueError("SEC user_agent must include project identity and contact email")
    value = user_agent.strip()
    match = _CONTACT_EMAIL_RE.search(value)
    if match is None:
        raise ValueError("SEC user_agent must include project identity and contact email")
    identity = (value[: match.start()] + value[match.end() :]).strip(" ()<>[]{};,:-\t")
    if not identity:
        raise ValueError("SEC user_agent must include project identity and contact email")
    return value


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def make_manifest(
    year: int,
    quarter: int,
    url: str,
    sha256: str,
    size_bytes: int,
    members: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build a deterministic archive manifest from supplied facts.

    The function performs no I/O and deliberately omits retrieval timestamps,
    allowing equivalent runs to produce byte-identical manifests.
    """

    validate_quarter(year, quarter)
    normalized_members = [dict(member) for member in members]
    normalized_members.sort(key=lambda member: str(member.get("name", "")))
    return {
        "schema_version": "1.0",
        "source": "sec",
        "year": year,
        "quarter": quarter,
        "url": url,
        "sha256": sha256,
        "content_hash": f"sha256:{sha256}",
        "size_bytes": size_bytes,
        "members": normalized_members,
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _retry_after(headers: Mapping[str, str]) -> float | None:
    value = headers.get("retry-after") or headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            return max(0.0, (when - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _response_content(response: Any) -> Iterable[bytes]:
    iterator = getattr(response, "iter_bytes", None)
    if callable(iterator):
        yield from iterator()
        return
    payload = getattr(response, "content", None)
    if payload is None:
        raise SECDownloadError("SEC response did not contain a body")
    yield bytes(payload)


def _request_archive(
    url: str,
    user_agent: str,
    client: Any,
    sleeper: Callable[[float], None],
    pacer: RequestPacer,
    max_attempts: int,
) -> tuple[bytes, bool]:
    headers = {"User-Agent": user_agent, "Accept": "application/zip"}
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        pacer.wait()
        try:
            try:
                response = client.get(url, headers=headers, follow_redirects=False)
            except TypeError as exc:
                # Small deterministic fakes often expose only ``get(url,
                # headers=...)``.  Keep redirect protection for real httpx
                # clients while remaining dependency-injection friendly.
                if "follow_redirects" not in str(exc):
                    raise
                response = client.get(url, headers=headers)
            status = int(getattr(response, "status_code", 200))
            response_headers = getattr(response, "headers", {})
            retryable = status == 429 or 500 <= status <= 599
            if retryable and attempt + 1 < max_attempts:
                advised = _retry_after(response_headers)
                delay = advised if advised is not None else min(2**attempt, 16)
                sleeper(min(MAX_RETRY_DELAY_SECONDS, max(0.0, delay)))
                continue
            if status >= 400:
                raise SECDownloadError(f"SEC archive request returned HTTP {status}")
            return b"".join(_response_content(response)), True
        except SECDownloadError as exc:
            last_error = exc
            if attempt + 1 >= max_attempts or "HTTP " not in str(exc):
                raise
        except (httpx.HTTPError, OSError) as exc:
            last_error = exc
            if attempt + 1 >= max_attempts:
                break
            sleeper(min(MAX_RETRY_DELAY_SECONDS, 2**attempt))
    raise SECDownloadError(
        f"SEC archive request failed after {max_attempts} attempts"
    ) from last_error


def _validate_member_name(member_name: str) -> PurePosixPath:
    """Validate a ZIP member name without resolving or opening the member."""

    # ZIP uses POSIX separators.  Backslashes and colons are still rejected so
    # an archive cannot acquire a different meaning when staged on Windows.
    if not member_name or "\x00" in member_name or "\\" in member_name:
        raise UnsafeArchiveError(f"unsafe ZIP member path: {member_name!r}")
    pure = PurePosixPath(member_name)
    if (
        pure.is_absolute()
        or ".." in pure.parts
        or any(":" in part for part in pure.parts)
        or not pure.parts
    ):
        raise UnsafeArchiveError(f"unsafe ZIP member path: {member_name!r}")
    return pure


def _preflight_archive(
    infos: Sequence[zipfile.ZipInfo],
    *,
    max_member_bytes: int,
    max_total_bytes: int,
) -> list[dict[str, Any]]:
    """Reject unsafe archive metadata before opening any compressed member."""

    if max_member_bytes < 1 or max_total_bytes < 1:
        raise ValueError("ZIP size limits must be positive")
    total_compressed = 0
    total_uncompressed = 0
    seen_names: set[str] = set()
    members: list[dict[str, Any]] = []
    for info in infos:
        pure = _validate_member_name(info.filename)
        name_key = pure.as_posix().casefold()
        if name_key in seen_names:
            raise UnsafeArchiveError(f"duplicate ZIP member path: {info.filename!r}")
        seen_names.add(name_key)
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise UnsafeArchiveError(f"symbolic links are not allowed: {info.filename!r}")
        compressed = info.compress_size
        uncompressed = info.file_size
        if compressed < 0 or uncompressed < 0:
            raise UnsafeArchiveError("ZIP member has an invalid declared size")
        if compressed > max_member_bytes or uncompressed > max_member_bytes:
            raise UnsafeArchiveError("ZIP member size exceeds configured limit")
        total_compressed += compressed
        total_uncompressed += uncompressed
        if total_compressed > max_total_bytes or total_uncompressed > max_total_bytes:
            raise UnsafeArchiveError("ZIP total size exceeds configured limit")
        members.append(
            {
                "name": info.filename,
                "compressed_size_bytes": compressed,
                "size_bytes": uncompressed,
                # Hashes are calculated while bounded extraction streams the
                # member.  Never pre-read a full member merely for a manifest.
                "sha256": None,
            }
        )
    return members


def _archive_members(
    path: Path,
    *,
    max_member_bytes: int = MAX_MEMBER_BYTES,
    max_total_bytes: int = MAX_TOTAL_EXTRACTED_BYTES,
) -> list[dict[str, Any]]:
    """Inspect central-directory metadata without decompressing ZIP members."""

    with zipfile.ZipFile(path) as archive:
        return _preflight_archive(
            archive.infolist(),
            max_member_bytes=max_member_bytes,
            max_total_bytes=max_total_bytes,
        )


def download_quarter(
    year: int,
    quarter: int,
    cache_dir: str | Path,
    user_agent: str,
    *,
    client: Any | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    pacer: RequestPacer | None = None,
    max_attempts: int = 4,
) -> DownloadResult:
    """Download and cache one SEC quarter, returning its content manifest.

    Existing archives are hash-checked and reused, making redelivery
    idempotent.  ``user_agent`` is required because the SEC blocks anonymous
    bulk requests; it should identify the application and an operator contact.
    """

    year, quarter = validate_quarter(year, quarter)
    user_agent = validate_sec_user_agent(user_agent)
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    root = Path(cache_dir)
    raw_dir = root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{year}q{quarter}.zip"
    manifest_path = raw_dir / f"{year}q{quarter}.manifest.json"
    url = archive_url(year, quarter)

    existing_hash: str | None = None
    if path.is_file():
        existing_hash = sha256_file(path)
        if manifest_path.is_file():
            try:
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
                if existing.get("sha256") == existing_hash and existing.get("url") == url:
                    # A hash match is not enough: older cache entries may
                    # have been written before archive-metadata preflight.
                    _archive_members(path)
                    return DownloadResult(
                        year,
                        quarter,
                        url,
                        path,
                        existing_hash,
                        path.stat().st_size,
                        manifest_path,
                        False,
                    )
            except (OSError, ValueError, TypeError, zipfile.BadZipFile):
                pass

    if client is None:
        client = httpx.Client(timeout=60.0)
    response_body, downloaded = _request_archive(
        url, user_agent, client, sleeper, pacer or _SEC_PACER, max_attempts
    )
    digest = sha256_bytes(response_body)
    temporary = path.with_suffix(".zip.tmp")
    temporary.write_bytes(response_body)
    try:
        members = _archive_members(temporary)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    os.replace(temporary, path)
    manifest = make_manifest(year, quarter, url, digest, len(response_body), members)
    _write_json(manifest_path, manifest)
    return DownloadResult(
        year, quarter, url, path, digest, len(response_body), manifest_path, downloaded
    )


def _safe_member_path(root: Path, member_name: str) -> Path:
    # ZIP names always use '/', even on Windows.  Reject absolute, drive, and
    # parent paths before resolving the target.
    pure = _validate_member_name(member_name)
    target = (root / Path(*pure.parts)).resolve()
    root_resolved = root.resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise UnsafeArchiveError(f"unsafe ZIP member path: {member_name!r}") from exc
    return target


def extract_archive(
    archive_path: str | Path,
    destination: str | Path,
    *,
    max_member_bytes: int = MAX_MEMBER_BYTES,
    max_total_bytes: int = MAX_TOTAL_EXTRACTED_BYTES,
) -> Path:
    """Safely extract a ZIP archive and reject traversal, links, and bombs."""

    root = Path(destination)
    root.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        _preflight_archive(
            infos,
            max_member_bytes=max_member_bytes,
            max_total_bytes=max_total_bytes,
        )
        with tempfile.TemporaryDirectory(
            prefix=f".{root.name}.stage-", dir=root.parent
        ) as temp_name:
            staged_root = Path(temp_name) / "contents"
            staged_root.mkdir()
            total = 0
            for info in infos:
                target = _safe_member_path(staged_root, info.filename)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                copied = 0
                with archive.open(info) as source, target.open("xb") as output:
                    while True:
                        remaining = min(max_member_bytes - copied, max_total_bytes - total)
                        if remaining < 1:
                            if source.read(1):
                                raise UnsafeArchiveError(
                                    "ZIP decompressed size exceeds configured limit"
                                )
                            break
                        chunk = source.read(min(_COPY_CHUNK_BYTES, remaining))
                        if not chunk:
                            break
                        copied += len(chunk)
                        total += len(chunk)
                        output.write(chunk)
                if copied != info.file_size:
                    raise UnsafeArchiveError("ZIP member size does not match its declaration")
            if root.exists():
                backup = root.with_name(f".{root.name}.previous-{uuid.uuid4().hex}")
                os.replace(root, backup)
            try:
                os.replace(staged_root, root)
            except BaseException:
                if backup is not None and backup.exists() and not root.exists():
                    os.replace(backup, root)
                raise
    if backup is not None and backup.exists():
        if backup.is_symlink() or backup.is_file():
            backup.unlink()
        elif backup.is_dir():
            shutil.rmtree(backup)
    return root


def _table_files(extracted_dir: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in extracted_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {".tsv", ".txt"}
        ),
        key=lambda path: path.relative_to(extracted_dir).as_posix().upper(),
    )


def _parse_table(path: Path, table_name: str) -> tuple[pl.DataFrame, list[QuarantinedRow]]:
    quarantined: list[QuarantinedRow] = []
    valid_rows: list[dict[str, str | None]] = []
    with path.open("rb") as binary:
        # utf-8-sig removes the BOM used by a few SEC exports while retaining
        # strict decoding for malformed payloads.
        text = io.TextIOWrapper(binary, encoding="utf-8-sig", errors="strict", newline="")
        reader = csv.reader(text, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration:
            return pl.DataFrame(), quarantined
        header = [value.strip() for value in header]
        if not header or any(not value for value in header) or len(set(header)) != len(header):
            return pl.DataFrame(), [
                QuarantinedRow(table_name, 1, "INVALID_HEADER", "\t".join(header)[:1000])
            ]
        for line_number, row in enumerate(reader, start=2):
            raw = "\t".join(row)
            if not row or not any(cell.strip() for cell in row):
                continue
            if len(row) != len(header):
                quarantined.append(
                    QuarantinedRow(table_name, line_number, "COLUMN_COUNT", raw[:1000])
                )
                continue
            valid_rows.append(
                {
                    key: (value if value != "" else None)
                    for key, value in zip(header, row, strict=True)
                }
            )
    if valid_rows:
        frame = pl.DataFrame(
            valid_rows,
            schema={column: pl.String for column in header},
            orient="row",
        )
    else:
        frame = pl.DataFrame(schema={column: pl.String for column in header})
    return frame, quarantined


def parse_sec_tables(
    extracted_dir: str | Path,
    *,
    return_quarantine: bool = False,
) -> dict[str, pl.DataFrame] | tuple[dict[str, pl.DataFrame], list[QuarantinedRow]]:
    """Parse SEC tab-separated tables into string-typed Polars frames.

    Ragged or malformed rows are returned as quarantine records and never
    prevent other tables from being parsed.  Set ``return_quarantine`` to
    retrieve those records; the default mapping-only form is convenient for
    callers that only need valid rows.
    """

    tables: dict[str, pl.DataFrame] = {}
    quarantined: list[QuarantinedRow] = []
    for path in _table_files(Path(extracted_dir)):
        table_name = path.stem.upper()
        try:
            frame, bad_rows = _parse_table(path, table_name)
        except (UnicodeError, csv.Error, OSError) as exc:
            frame = pl.DataFrame()
            bad_rows = [QuarantinedRow(table_name, 0, "TABLE_PARSE_ERROR", str(exc)[:1000])]
        tables[table_name] = frame
        quarantined.extend(bad_rows)
    if return_quarantine:
        return tables, quarantined
    return tables


def parse_sec_tables_with_quarantine(
    extracted_dir: str | Path,
) -> tuple[dict[str, pl.DataFrame], list[QuarantinedRow]]:
    """Explicit tuple-returning alias for :func:`parse_sec_tables`."""

    result = parse_sec_tables(extracted_dir, return_quarantine=True)
    assert isinstance(result, tuple)
    return result


def stage_quarter(
    year: int,
    quarter: int,
    cache_dir: str | Path,
    staging_dir: str | Path,
    user_agent: str | None = None,
    *,
    archive_path: str | Path | None = None,
    client: Any | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    pacer: RequestPacer | None = None,
) -> StageResult:
    """Download (if necessary), parse, and write a deterministic partition."""

    year, quarter = validate_quarter(year, quarter)
    if archive_path is None:
        if user_agent is None:
            raise ValueError("user_agent is required when downloading an archive")
        archive = download_quarter(
            year,
            quarter,
            cache_dir,
            user_agent,
            client=client,
            sleeper=sleeper,
            pacer=pacer,
        )
    else:
        path = Path(archive_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        digest = sha256_file(path)
        archive = DownloadResult(
            year,
            quarter,
            archive_url(year, quarter),
            path,
            digest,
            path.stat().st_size,
            path,
            False,
        )

    partition = Path(staging_dir) / f"year={year:04d}" / f"quarter={quarter}"
    partition.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f"sec-{year}q{quarter}-", dir=str(partition.parent)
    ) as temp_name:
        extracted = extract_archive(archive.path, Path(temp_name) / "tables")
        tables, bad_rows = parse_sec_tables_with_quarantine(extracted)
        parquet_paths: list[Path] = []
        for table_name in sorted(tables):
            destination = partition / f"{table_name}.parquet"
            temporary = destination.with_suffix(".parquet.tmp")
            tables[table_name].write_parquet(temporary, compression="zstd", statistics=False)
            os.replace(temporary, destination)
            parquet_paths.append(destination)

    quarantine_path: Path | None = None
    if bad_rows:
        quarantine_path = partition / "quarantine.jsonl"
        lines = [
            json.dumps(
                {
                    "table": row.table,
                    "line_number": row.line_number,
                    "reason": row.reason,
                    "raw": row.raw,
                },
                sort_keys=True,
            )
            for row in bad_rows
        ]
        quarantine_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    stage_manifest = {
        "schema_version": "1.0",
        "source": "sec",
        "year": year,
        "quarter": quarter,
        "archive_sha256": archive.sha256,
        "tables": [
            {
                "name": path.stem,
                "path": path.name,
                "sha256": sha256_file(path),
                "rows": tables[path.stem].height,
            }
            for path in parquet_paths
        ],
        "quarantined_rows": len(bad_rows),
    }
    manifest_path = partition / "manifest.json"
    _write_json(manifest_path, stage_manifest)
    return StageResult(
        year,
        quarter,
        archive,
        partition,
        tuple(parquet_paths),
        quarantine_path,
        len(bad_rows),
        manifest_path,
    )


def list_cached_quarters(cache_dir: str | Path) -> list[dict[str, Any]]:
    """List valid cached archive manifests without making network requests."""

    raw_dir = Path(cache_dir) / "raw"
    results: list[dict[str, Any]] = []
    for manifest_path in sorted(raw_dir.glob("*.manifest.json")):
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
            path = raw_dir / f"{value['year']}q{value['quarter']}.zip"
            if path.is_file() and sha256_file(path) == value.get("sha256"):
                results.append(value)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(results, key=lambda value: (int(value["year"]), int(value["quarter"])))


# Friendly names used by callers and conformance tests.
build_archive_url = archive_url
quarter_manifest = make_manifest
download = download_quarter
extract = extract_archive
stage = stage_quarter


__all__ = [
    "DownloadResult",
    "MIN_YEAR",
    "QuarantinedRow",
    "RequestPacer",
    "SECDownloadError",
    "SEC_ARCHIVE_URL_TEMPLATE",
    "StageResult",
    "UnsafeArchiveError",
    "archive_url",
    "build_archive_url",
    "download",
    "download_quarter",
    "extract",
    "extract_archive",
    "list_cached_quarters",
    "list_quarters",
    "make_manifest",
    "parse_sec_tables",
    "parse_sec_tables_with_quarantine",
    "quarter_manifest",
    "sha256_bytes",
    "sha256_file",
    "stage",
    "stage_quarter",
    "validate_sec_user_agent",
    "validate_quarter",
]
