"""Offline contracts for official catalog resolution and bulk-history readiness."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import httpx
import polars as pl
import pytest
from typer.testing import CliRunner

from insider_turning_engine.cli import app
from insider_turning_engine.ingestion.sec import historical, history

UA = "InsiderTurningEngine test@example.com"
URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/2026q2_form345.zip"
HTML = f'<a href="{URL}">Download</a>'


def test_catalog_is_authoritative_not_a_guessed_path() -> None:
    catalog = historical.parse_quarter_catalog(HTML)
    assert historical.archive_url(2026, 2, catalog) == URL
    with pytest.raises(historical.SECDownloadError, match="no published"):
        historical.archive_url(2026, 3, catalog)
    for html in (
        HTML.replace("www.sec.gov", "evil.example"),
        HTML.replace("https:", "http:"),
        HTML.replace("_form345.zip", "_form345.zip?redirect=yes"),
        HTML + HTML.replace("structureddata", "datastandardsinnovation"),
    ):
        with pytest.raises(ValueError):
            historical.parse_quarter_catalog(html)
    with pytest.raises(historical.SECDownloadError):
        historical.parse_quarter_catalog("<h1>Access denied</h1>")


def test_catalog_transport_retries_and_rejects_redirects() -> None:
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.headers["User-Agent"] == UA
        return httpx.Response(429 if len(calls) == 1 else 200,
                              headers={"Content-Type": "text/html"}, text=HTML)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        assert historical.fetch_quarter_catalog(UA, client=client, sleeper=lambda _: None)
    assert len(calls) == 2
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(302))) as client:
        with pytest.raises(ValueError, match="redirect"):
            historical.fetch_quarter_catalog(UA, client=client)


def fixture_partition(tmp_path: Path, *, year: int = 2026, quarter: int = 2,
                      amended: bool = False, filed: str = "08-Jun-2026") -> Path:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in sorted(history.TABLES):
            header, rows = "ACCESSION_NUMBER", "a"
            if name == "SUBMISSION":
                header += "\tFILING_DATE\tDOCUMENT_TYPE\tISSUERCIK"
                rows += f"\t{filed}\t{'4/A' if amended else '4'}\t123"
            elif name == "NONDERIV_TRANS":
                header += ("\tNONDERIV_TRANS_SK\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES"
                           "\tTRANS_PRICEPERSHARE\tTRANS_ACQUIRED_DISP_CD")
                rows += "\t1\t07-Jun-2026\tP\t100\t25\tA"
            elif name == "DERIV_TRANS":
                header += "\tDERIV_TRANS_SK"
                rows += "\t1"
            elif name == "REPORTINGOWNER":
                header += "\tRPTOWNERCIK"
                rows = "a\t111\na\t222"  # Must not double-count the same economic transaction.
            archive.writestr(f"{name}.tsv", header + "\n" + rows + "\n")
    archive_path = tmp_path / "fixture.zip"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(buffer.getvalue())
    result = historical.stage_quarter(year, quarter, tmp_path / "cache", tmp_path / "stage",
                                      archive_path=archive_path)
    return result.partition_path


def test_inventory_is_deterministic_date_only_and_not_a_signal_universe(tmp_path: Path) -> None:
    fixture_partition(tmp_path)
    root = tmp_path / "stage"
    first = history.activity_inventory(root, as_of=date(2026, 6, 9))
    assert first == history.activity_inventory(root, as_of=date(2026, 6, 9))
    assert first["candidateIssuerCiks"] == ["0000000123"]
    assert first["pricedPSCandidateRows"] == 1  # two owners, one transaction
    assert not first["canonicalReady"] and not first["eligibleUniverseReady"]
    assert "INCOMPLETE_QUARTER_COVERAGE" in first["qualityFlags"]
    assert history.activity_inventory(root, as_of=date(2026, 6, 8))["candidateIssuerCount"] == 0
    assert history.activity_inventory(root, as_of=date(2026, 6, 7))["candidateIssuerCount"] == 0
    assert history.activity_inventory(root, as_of=date(2027, 6, 9))["candidateIssuerCount"] == 0


def test_inventory_excludes_unlinked_amendments_and_future_rows(tmp_path: Path) -> None:
    fixture_partition(tmp_path, amended=True)
    report = history.activity_inventory(tmp_path / "stage", as_of=date(2026, 6, 9))
    assert report["candidateIssuerCount"] == 0
    assert report["excludedAmendmentRows"] == 1
    before = history.activity_inventory(tmp_path / "stage", as_of=date(2026, 6, 8))
    fixture_partition(tmp_path, amended=False, filed="09-Jun-2026")
    after = history.activity_inventory(tmp_path / "stage", as_of=date(2026, 6, 8))
    # Input checksums change, the earlier acquisition candidates do not.
    assert before["candidateIssuerCiks"] == after["candidateIssuerCiks"] == []


@pytest.mark.parametrize("damage", ["checksum", "missing", "traversal", "quarantine", "count"])
def test_partition_fails_closed(tmp_path: Path, damage: str) -> None:
    root = fixture_partition(tmp_path)
    path = root / "manifest.json"
    payload = json.loads(path.read_text())
    if damage == "checksum":
        payload["tables"][0]["sha256"] = "0" * 64
    elif damage == "missing":
        payload["tables"].pop()
    elif damage == "traversal":
        payload["tables"][0]["path"] = "../other.parquet"
    elif damage == "quarantine":
        payload["quarantined_rows"] = 1
    else:
        payload["total_rows"] += 1
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        history.validate_partition(root, 2026, 2)


def test_backfill_resumes_verified_partitions_and_reports_partial_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = fixture_partition(tmp_path)
    digest = json.loads((root / "manifest.json").read_text())["archive_sha256"]

    def download(year: int, quarter: int, *args: object, **kwargs: object) -> SimpleNamespace:
        if quarter == 1:
            raise historical.SECDownloadError("fixture failure")
        return SimpleNamespace(sha256=digest, url=URL, path=tmp_path / "fixture.zip")

    monkeypatch.setattr(history, "download_quarter", download)
    monkeypatch.setattr(history, "stage_quarter", lambda *a, **kw: pytest.fail("cache restaged"))
    report = history.backfill_history(
        cache_dir=tmp_path / "cache", staging_dir=tmp_path / "stage", user_agent=UA,
        start=(2026, 1), end=(2026, 2), today=date(2026, 9, 9), catalog={},
    )
    assert report["status"] == "INCOMPLETE" and not report["canonicalReady"]
    assert [q["status"] for q in report["quarters"]] == ["FAILED", "STAGED"]
    assert not list(tmp_path.rglob("*cursor*"))
    assert not list(tmp_path.rglob("*commit-marker*"))


@pytest.mark.parametrize("damage", ["duplicate", "orphan", "null_key"])
def test_hash_correct_tables_still_require_valid_keys_and_joins(
    tmp_path: Path, damage: str,
) -> None:
    root = fixture_partition(tmp_path)
    path = root / "NONDERIV_TRANS.parquet"
    frame = pl.read_parquet(path)
    if damage == "duplicate":
        frame = pl.concat([frame, frame])
    else:
        frame = frame.with_columns(pl.lit(None if damage == "null_key" else "unknown")
                                   .cast(pl.String).alias("ACCESSION_NUMBER"))
    frame.write_parquet(path)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for table in manifest["tables"]:
        if table["name"] == "NONDERIV_TRANS":
            table.update(sha256=historical.sha256_file(path), rows=frame.height)
    manifest["parsed_rows"] = manifest["total_rows"] = sum(t["rows"] for t in manifest["tables"])
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="keys|orphan"):
        history.validate_partition(root, 2026, 2)


def test_backfill_repairs_corrupt_staging_from_valid_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = fixture_partition(tmp_path)
    archive_path = tmp_path / "fixture.zip"
    monkeypatch.setattr(history, "download_quarter", lambda *a, **kw: SimpleNamespace(
        sha256=historical.sha256_file(archive_path), url=URL, path=archive_path,
    ))
    (root / "SUBMISSION.parquet").write_bytes(b"corrupt")
    report = history.backfill_history(
        cache_dir=tmp_path / "cache", staging_dir=tmp_path / "stage", user_agent=UA,
        start=(2026, 2), end=(2026, 2), today=date(2026, 9, 9), catalog={},
    )
    assert report["status"] == "STAGED"
    assert history.validate_partition(root, 2026, 2)["SUBMISSION"].height == 1


def test_range_and_cli_are_offline_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(history, "fetch_quarter_catalog", lambda *a: pytest.fail("network"))
    assert history.last_completed_quarter(date(2026, 1, 1)) == (2025, 4)
    assert len(history.quarter_range((2006, 1), (2026, 2))) == 82
    with pytest.raises(ValueError):
        history.quarter_range((2026, 2), (2025, 1))
    result = CliRunner().invoke(app, ["backfill-sec-history", "--start-year", "2025"])
    assert result.exit_code == 0 and "DRY_RUN" in result.stdout
    assert CliRunner().invoke(app, ["backfill-sec-history", "--end-year", "2025"]).exit_code != 0
