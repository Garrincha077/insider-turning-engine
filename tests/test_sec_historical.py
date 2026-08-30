"""Deterministic contract tests for the SEC historical adapter."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from insider_turning_engine.ingestion.sec.historical import (
    RequestPacer,
    UnsafeArchiveError,
    archive_url,
    download_quarter,
    extract_archive,
    list_quarters,
    parse_sec_tables_with_quarantine,
    stage_quarter,
)


def _zip_bytes(*members: tuple[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in members:
            archive.writestr(name, content)
    return output.getvalue()


class _Response:
    def __init__(
        self,
        body: bytes,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.content = body
        self.status_code = status_code
        self.headers = headers or {}


class _Client:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> _Response:
        self.requests.append((url, kwargs))
        return self.responses.pop(0)


def test_period_url_and_enumeration() -> None:
    assert archive_url(2006, 1).endswith("/2006q1.zip")
    assert list_quarters(2006, 2007) == [
        (2006, 1),
        (2006, 2),
        (2006, 3),
        (2006, 4),
        (2007, 1),
        (2007, 2),
        (2007, 3),
        (2007, 4),
    ]
    with pytest.raises(ValueError):
        archive_url(2005, 1)
    with pytest.raises(ValueError):
        archive_url(2024, 5)


def test_download_retries_and_is_cache_idempotent(tmp_path: Path) -> None:
    body = _zip_bytes(("SUBMISSION.tsv", "ACCESSION\tFORM\na\t4\n"))
    client = _Client([_Response(b"busy", 429, {"Retry-After": "0"}), _Response(body)])
    sleeps: list[float] = []
    result = download_quarter(
        2024,
        1,
        tmp_path,
        "insider-engine test@example.com",
        client=client,
        sleeper=sleeps.append,
        pacer=RequestPacer(sleeper=lambda _: None),
    )
    assert result.path.is_file()
    assert result.sha256
    assert len(client.requests) == 2
    assert client.requests[0][1]["headers"] == {
        "User-Agent": "insider-engine test@example.com",
        "Accept": "application/zip",
    }
    again = download_quarter(
        2024,
        1,
        tmp_path,
        "insider-engine test@example.com",
        client=_Client([]),
        sleeper=lambda _: None,
        pacer=RequestPacer(sleeper=lambda _: None),
    )
    assert again.downloaded is False
    assert again.sha256 == result.sha256


def test_download_requires_project_identity_and_contact_email(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="project identity and contact email"):
        download_quarter(2024, 1, tmp_path, "operator@example.com")


def test_safe_extraction_and_row_quarantine(tmp_path: Path) -> None:
    safe = tmp_path / "safe.zip"
    safe.write_bytes(_zip_bytes(("TABLE.tsv", "a\tb\n1\t2\nshort\n")))
    extracted = extract_archive(safe, tmp_path / "extract")
    tables, quarantined = parse_sec_tables_with_quarantine(extracted)
    assert tables["TABLE"].height == 1
    assert quarantined[0].reason == "COLUMN_COUNT"

    unsafe = tmp_path / "unsafe.zip"
    unsafe.write_bytes(_zip_bytes(("../escape.tsv", "a\n1\n")))
    with pytest.raises(UnsafeArchiveError):
        extract_archive(unsafe, tmp_path / "extract-unsafe")


def test_extraction_preflights_declared_compressed_sizes_and_keeps_destination_atomic(
    tmp_path: Path,
) -> None:
    compressed = tmp_path / "compressed.zip"
    compressed.write_bytes(_zip_bytes(("one.tsv", "x")))
    with zipfile.ZipFile(compressed) as archive:
        info = archive.infolist()[0]
        assert info.file_size == 1
        assert info.compress_size > info.file_size
    # The uncompressed declaration is within the limit; the compressed
    # declaration must be rejected before its member is opened.
    with pytest.raises(UnsafeArchiveError, match="member size"):
        extract_archive(compressed, tmp_path / "too-compressed", max_member_bytes=1)

    invalid = tmp_path / "invalid.zip"
    invalid.write_bytes(_zip_bytes(("first.tsv", "x"), ("second.tsv", "xx")))
    destination = tmp_path / "existing"
    destination.mkdir()
    sentinel = destination / "previous.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(UnsafeArchiveError, match="member size"):
        extract_archive(invalid, destination, max_member_bytes=1)
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_stage_writes_partition_and_quarantine(tmp_path: Path) -> None:
    archive = tmp_path / "quarter.zip"
    archive.write_bytes(_zip_bytes(("A.tsv", "x\n1\n2\n"), ("B.tsv", "x\nmalformed\textra\n")))
    result = stage_quarter(2024, 2, tmp_path / "cache", tmp_path / "stage", archive_path=archive)
    assert result.partition_path == tmp_path / "stage" / "year=2024" / "quarter=2"
    assert {path.name for path in result.parquet_paths} == {"A.parquet", "B.parquet"}
    assert result.quarantined_rows == 1
    assert result.quarantine_path is not None and result.quarantine_path.is_file()
