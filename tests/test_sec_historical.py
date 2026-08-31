"""Deterministic contract tests for the SEC historical adapter."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from insider_turning_engine.ingestion.sec import historical
from insider_turning_engine.ingestion.sec.historical import (
    RequestPacer,
    SECDownloadError,
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
        url: str | None = None,
        history: tuple[object, ...] = (),
    ) -> None:
        self.content = body
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "application/zip"}
        self.url = url
        self.history = history


class _Client:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> _Response:
        self.requests.append((url, kwargs))
        return self.responses.pop(0)


class _InterruptedResponse(_Response):
    def __init__(self, prefix: bytes) -> None:
        super().__init__(b"")
        self.prefix = prefix

    def iter_bytes(self) -> object:
        yield self.prefix
        raise OSError("connection interrupted")


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


def test_download_resumes_durable_partial_with_validated_range(tmp_path: Path) -> None:
    body = _zip_bytes(("SUBMISSION.tsv", "ACCESSION\tFORM\na\t4\n"))
    split = len(body) // 2
    with pytest.raises(SECDownloadError, match="failed after 1 attempts"):
        download_quarter(
            2024,
            1,
            tmp_path,
            "insider-engine test@example.com",
            client=_Client([_InterruptedResponse(body[:split])]),
            pacer=RequestPacer(sleeper=lambda _: None),
            max_attempts=1,
        )
    part = tmp_path / "raw" / "2024q1.zip.part"
    assert part.read_bytes() == body[:split]

    resumed = _Response(
        body[split:],
        status_code=206,
        headers={
            "Content-Type": "application/zip",
            "Content-Length": str(len(body) - split),
            "Content-Range": f"bytes {split}-{len(body) - 1}/{len(body)}",
        },
    )
    client = _Client([resumed])
    result = download_quarter(
        2024,
        1,
        tmp_path,
        "insider-engine test@example.com",
        client=client,
        pacer=RequestPacer(sleeper=lambda _: None),
        max_attempts=1,
    )

    assert client.requests[0][1]["headers"]["Range"] == f"bytes={split}-"
    assert result.path.read_bytes() == body
    assert not part.exists()


def test_download_restarts_when_server_ignores_range(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    part = raw / "2024q1.zip.part"
    part.write_bytes(b"stale-prefix")
    body = _zip_bytes(("SUBMISSION.tsv", "ACCESSION\tFORM\na\t4\n"))
    client = _Client([_Response(body)])

    result = download_quarter(
        2024,
        1,
        tmp_path,
        "insider-engine test@example.com",
        client=client,
        pacer=RequestPacer(sleeper=lambda _: None),
        max_attempts=1,
    )

    assert client.requests[0][1]["headers"]["Range"] == "bytes=12-"
    assert result.path.read_bytes() == body


@pytest.mark.parametrize(
    "response, message",
    [
        (_Response(b"ignored", status_code=302), "redirect"),
        (
            _Response(
                b"ignored",
                url="https://evil.example/2024q1.zip",
            ),
            "allowlist",
        ),
        (_Response(b"ignored", headers={"Content-Type": "text/html"}), "Content-Type"),
    ],
)
def test_download_rejects_redirect_host_and_content_type(
    tmp_path: Path, response: _Response, message: str
) -> None:
    with pytest.raises(SECDownloadError, match=message):
        download_quarter(
            2024,
            1,
            tmp_path,
            "insider-engine test@example.com",
            client=_Client([response]),
            pacer=RequestPacer(sleeper=lambda _: None),
            max_attempts=1,
        )


def test_download_rejects_body_over_limit_before_cache_replace(tmp_path: Path) -> None:
    body = _zip_bytes(("SUBMISSION.tsv", "ACCESSION\tFORM\na\t4\n"))
    with pytest.raises(SECDownloadError, match="size limit"):
        download_quarter(
            2024,
            1,
            tmp_path,
            "insider-engine test@example.com",
            client=_Client([_Response(body)]),
            pacer=RequestPacer(sleeper=lambda _: None),
            max_attempts=1,
            max_download_bytes=len(body) - 1,
        )
    assert not (tmp_path / "raw" / "2024q1.zip").exists()


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


def test_extraction_rejects_excessive_member_count(tmp_path: Path) -> None:
    archive = tmp_path / "members.zip"
    archive.write_bytes(_zip_bytes(("one.tsv", ""), ("two.tsv", "")))
    with pytest.raises(UnsafeArchiveError, match="member count"):
        extract_archive(archive, tmp_path / "extract-members", max_members=1)


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
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["parsed_rows"] == 2
    assert manifest["total_rows"] == 3
    assert manifest["parse_success_rate"] == pytest.approx(2 / 3)


def test_stage_replaces_partition_atomically_and_removes_stale_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = tmp_path / "original.zip"
    original.write_bytes(_zip_bytes(("A.tsv", "x\n1\n"), ("B.tsv", "x\nbad\textra\n")))
    first = stage_quarter(2024, 2, tmp_path / "cache", tmp_path / "stage", archive_path=original)
    before = {
        path.relative_to(first.partition_path).as_posix(): path.read_bytes()
        for path in first.partition_path.rglob("*")
        if path.is_file()
    }

    replacement = tmp_path / "replacement.zip"
    replacement.write_bytes(_zip_bytes(("A.tsv", "x\n2\n")))

    def fail_manifest_write(*_args: object, **_kwargs: object) -> None:
        raise OSError("manifest write failed")

    with monkeypatch.context() as scoped:
        scoped.setattr(historical, "_write_json", fail_manifest_write)
        with pytest.raises(OSError, match="manifest write failed"):
            stage_quarter(
                2024,
                2,
                tmp_path / "cache",
                tmp_path / "stage",
                archive_path=replacement,
            )
    after_failure = {
        path.relative_to(first.partition_path).as_posix(): path.read_bytes()
        for path in first.partition_path.rglob("*")
        if path.is_file()
    }
    assert after_failure == before

    replaced = stage_quarter(
        2024, 2, tmp_path / "cache", tmp_path / "stage", archive_path=replacement
    )
    assert {path.name for path in replaced.partition_path.iterdir()} == {
        "A.parquet",
        "manifest.json",
    }
    assert replaced.quarantine_path is None


def test_stage_recovers_previous_partition_before_new_work(tmp_path: Path) -> None:
    archive = tmp_path / "quarter.zip"
    archive.write_bytes(_zip_bytes(("A.tsv", "x\n1\n")))
    first = stage_quarter(2024, 2, tmp_path / "cache", tmp_path / "stage", archive_path=archive)
    sentinel = (first.partition_path / "manifest.json").read_bytes()
    backup = first.partition_path.with_name(f".{first.partition_path.name}.previous-crash")
    first.partition_path.replace(backup)

    with pytest.raises(FileNotFoundError):
        stage_quarter(
            2024,
            2,
            tmp_path / "cache",
            tmp_path / "stage",
            archive_path=tmp_path / "missing.zip",
        )

    assert (first.partition_path / "manifest.json").read_bytes() == sentinel
    assert not backup.exists()
