import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from insider_turning_engine.ingestion.sec.daily_history import ingest_day
from insider_turning_engine.ingestion.sec.daily_index import (
    SECDailyIndexSource,
    parse_complete_submission,
    parse_daily_master_index,
)
from insider_turning_engine.ingestion.sec.parser import parse_sec_filing

FIXTURE = Path(__file__).parent / "fixtures/form4_non_derivative.xml"
DAY = date(2026, 8, 31)
INDEX = (
    b"CIK|Company Name|Form Type|Date Filed|Filename\n----\n"
    b"1234567|Owner|4|2026-08-31|edgar/data/1234567/0001234567-26-000001.txt\n"
    b"1234567|Owner|4|2026-08-31|edgar/data/1234567/0001234567-26-000002.txt\n"
)


def submission(accession: str, stamp: str = "20260831160100") -> bytes:
    return (f"<ACCEPTANCE-DATETIME>{stamp}\n<ACCESSION-NUMBER>{accession}\n"
            "<DOCUMENT>\n<TYPE>4\n<FILENAME>ownership.xml\n<TEXT>\n".encode()
            + FIXTURE.read_bytes() + b"\n</TEXT>\n</DOCUMENT>")


@pytest.mark.parametrize("stamp,expected", [
    ("20260831160100", datetime(2026, 8, 31, 20, 1, tzinfo=UTC)),
    ("20260120160100", datetime(2026, 1, 20, 21, 1, tzinfo=UTC)),
    ("20060320160100", datetime(2006, 3, 20, 21, 1, tzinfo=UTC)),
    ("20060403160100", datetime(2006, 4, 3, 20, 1, tzinfo=UTC)),
])
def test_sgml_eastern_clock_and_historical_dst_rules(stamp: str, expected: datetime) -> None:
    entry = parse_daily_master_index(INDEX)[0]
    raw = parse_complete_submission(
        submission(entry.accession_number, stamp), entry,
        retrieved_at=datetime(2026, 12, 1, tzinfo=UTC), index_url="fixture", index_hash="fixture",
    )
    assert raw.accepted_at == expected
    assert raw.provenance["acceptance_parser_version"] == "2"


@pytest.mark.parametrize("stamp", ["20260308023000", "20261101013000"])
def test_ambiguous_and_nonexistent_wall_clocks_are_rejected(stamp: str) -> None:
    entry = parse_daily_master_index(INDEX)[0]
    with pytest.raises(ValueError, match="ambiguous or nonexistent"):
        parse_complete_submission(
            submission(entry.accession_number, stamp), entry,
            retrieved_at=datetime(2026, 12, 1, tzinfo=UTC),
            index_url="fixture", index_hash="fixture",
        )


def source(tmp_path: Path, *, broken: bool = False) -> SECDailyIndexSource:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".idx"):
            body = INDEX
        elif broken and request.url.path.endswith("000002.txt"):
            return httpx.Response(500)
        else:
            body = submission(Path(request.url.path).stem)
        return httpx.Response(200, content=body)
    return SECDailyIndexSource(
        "InsiderEngine test@example.com",
        client=httpx.Client(transport=httpx.MockTransport(respond)),
        cache_dir=tmp_path / "cache", clock=lambda: datetime(2026, 9, 2, 10, tzinfo=UTC),
        sleeper=lambda _: None, max_attempts=1,
    )


def test_bounded_acquisition_resumes_with_byte_identical_replay(tmp_path: Path) -> None:
    provider = source(tmp_path)
    output = tmp_path / "history"
    marker = output / DAY.isoformat() / "acquisition-complete.sha256"
    first = ingest_day(provider, day=DAY, output_root=output, max_filings=1)
    assert first["status"] == "INCOMPLETE"
    assert first["acquiredFilings"] == first["pendingFilings"] == 1
    assert first["failureCount"] == 0
    assert not marker.exists()
    second = ingest_day(provider, day=DAY, output_root=output, max_filings=1)
    assert second["status"] == "ACQUIRED" and second["acquiredFilings"] == 2
    assert marker.is_file() and not second["signalReady"]
    batch_path = marker.parent / "sec-batch.json"
    previous = batch_path.read_bytes()
    replay = ingest_day(provider, day=DAY, output_root=output, max_filings=1)
    assert replay == second and previous == batch_path.read_bytes()
    batch = json.loads(previous)
    assert all(row["timestamps"]["acceptedAt"] == "2026-08-31T20:01:00Z"
               for row in batch["records"])
    # Original collection time remains separate, not backdated to acceptance.
    assert all(row["timestamps"]["observedAt"] == "2026-09-02T10:00:00Z"
               for row in batch["records"])
    assert not list(output.rglob("sec.cursor"))
    assert not list(output.rglob("sec-batch-committed.sha256"))


def test_partial_source_failure_has_no_completion_marker(tmp_path: Path) -> None:
    report = ingest_day(source(tmp_path, broken=True), day=DAY, output_root=tmp_path / "history")
    assert report["status"] == "INCOMPLETE" and report["failureCount"] == 1
    assert not list((tmp_path / "history").rglob("acquisition-complete.sha256"))


def test_active_day_is_never_cached_as_complete(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="completed SEC filing days"):
        ingest_day(source(tmp_path), day=date(2026, 9, 2), output_root=tmp_path / "history")


@pytest.mark.parametrize("ticker", ["N/A", "BIO BIO.B"])
def test_ambiguous_ticker_does_not_destroy_cik_identity(ticker: str) -> None:
    xml = FIXTURE.read_bytes().replace(b">ACME<", f">{ticker}<".encode())
    result = parse_sec_filing(xml, {
        "accession_number": "0001234567-26-000001",
        "source_url": "https://www.sec.gov/Archives/edgar/data/fixture.xml",
        "accepted_at": datetime(2026, 8, 31, 20, 1, tzinfo=UTC),
        "observed_at": datetime(2026, 9, 2, 10, tzinfo=UTC),
    })
    assert not result.quarantines and result.records
    assert all(row.issuer.ticker is None and row.issuer.cik == "0001999001"
               for row in result.records)
    assert all("UNRESOLVED_ISSUER_TICKER" in {flag.code for flag in row.quality.flags}
               for row in result.records)
