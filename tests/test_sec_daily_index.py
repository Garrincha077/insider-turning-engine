from datetime import UTC, date, datetime

import httpx

from insider_turning_engine.ingestion.sec.daily_index import (
    DEFAULT_SUBMISSION_MAXIMUM_BYTES,
    MAX_CONFIGURABLE_SUBMISSION_BYTES,
    SECDailyIndexSource,
    daily_index_url,
    parse_complete_submission,
    parse_daily_master_index,
)

INDEX = b"""Description: Master Index of EDGAR Dissemination Feed

CIK|Company Name|Form Type|Date Filed|Filename
--------------------------------------------------------------------------------
1234567|Owner Name|4|2026-08-31|edgar/data/1234567/0001234567-26-000001.txt
1234567|Owner Name|10-K|2026-08-31|edgar/data/1234567/0001234567-26-000002.txt
"""

SUBMISSION = b"""<SEC-HEADER>
<ACCEPTANCE-DATETIME>20260831194530
<ACCESSION-NUMBER>0001234567-26-000001
</SEC-HEADER>
<DOCUMENT>
<TYPE>4
<FILENAME>ownership.xml
<TEXT>
<XML>
<?xml version="1.0"?>
<ownershipDocument><issuer><issuerCik>7654321</issuerCik></issuer></ownershipDocument>
</XML>
</TEXT>
</DOCUMENT>
"""

REAL_SGML_SUBMISSION = b"""<SEC-DOCUMENT>0001234567-26-000001.txt : 20260831
<SEC-HEADER>0001234567-26-000001.hdr.sgml : 20260831
<ACCEPTANCE-DATETIME>20260831194530
ACCESSION NUMBER:\t\t0001234567-26-000001
CONFORMED SUBMISSION TYPE:\t4
<DOCUMENT>
<TYPE>4
<FILENAME>ownership.xml
<TEXT>
<ownershipDocument><issuer><issuerCik>7654321</issuerCik></issuer></ownershipDocument>
</TEXT>
</DOCUMENT>
"""


def test_daily_index_filters_ownership_and_does_not_invent_acceptance_time() -> None:
    rows = parse_daily_master_index(INDEX)
    assert len(rows) == 1
    assert rows[0].filer_cik == "0001234567"
    assert rows[0].filing_date == date(2026, 8, 31)
    assert daily_index_url(date(2026, 8, 31)).endswith(
        "/2026/QTR3/master.20260831.idx"
    )


def test_source_accepts_late_filed_entry_but_keeps_publication_day_provenance() -> None:
    late = INDEX.replace(b"2026-08-31", b"2026-08-30", 1)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("master.20260831.idx"):
            return httpx.Response(200, content=late, request=request)
        return httpx.Response(200, content=SUBMISSION, request=request)

    source = SECDailyIndexSource(
        "InsiderTurningEngine admin@example.com",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=lambda _delay: None,
        clock=lambda: datetime(2026, 9, 1, tzinfo=UTC),
    )
    entries = source.discover_day(date(2026, 8, 31))
    assert entries[0].filing_date == date(2026, 8, 30)
    assert entries[0].index_date == date(2026, 8, 31)
    record = source.fetch_entry(entries[0], index_hash=source.last_index_hash)
    assert record.filing_date == "2026-08-30"
    assert record.provenance["daily_index_url"].endswith("master.20260831.idx")


def test_source_rejects_future_filing_date_in_daily_index() -> None:
    future = INDEX.replace(b"2026-08-31", b"2026-09-01", 1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=future, request=request)

    source = SECDailyIndexSource(
        "InsiderTurningEngine admin@example.com",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=lambda _delay: None,
        clock=lambda: datetime(2026, 9, 2, tzinfo=UTC),
    )
    try:
        source.discover_day(date(2026, 8, 31))
    except ValueError as exc:
        assert str(exc) == "daily index contains a future filing date"
    else:
        raise AssertionError("future Date Filed must be rejected")


def test_complete_submission_recovers_exact_acceptance_and_issuer() -> None:
    entry = parse_daily_master_index(INDEX)[0]
    record = parse_complete_submission(
        SUBMISSION,
        entry,
        retrieved_at=datetime(2026, 9, 1, tzinfo=UTC),
        index_url=daily_index_url(entry.filing_date),
        index_hash="sha256:" + "1" * 64,
    )
    assert record.accepted_at == datetime(2026, 8, 31, 23, 45, 30, tzinfo=UTC)
    assert record.issuer_cik == "0007654321"
    assert record.primary_document == "ownership.xml"
    assert record.payload is not None and b"ownershipDocument" in record.payload


def test_complete_submission_accepts_real_edgar_sgml_accession_header() -> None:
    entry = parse_daily_master_index(INDEX)[0]
    record = parse_complete_submission(
        REAL_SGML_SUBMISSION,
        entry,
        retrieved_at=datetime(2026, 9, 1, tzinfo=UTC),
        index_url=daily_index_url(entry.filing_date),
        index_hash="sha256:" + "1" * 64,
    )
    assert record.accession_number == entry.accession_number
    assert record.accepted_at == datetime(2026, 8, 31, 23, 45, 30, tzinfo=UTC)


def test_daily_index_deduplicates_reporting_owner_aliases_by_accession() -> None:
    duplicated = INDEX.replace(
        b"1234567|Owner Name|4|2026-08-31|edgar/data/1234567/0001234567-26-000001.txt",
        b"7654321|Issuer Alias|4|2026-08-31|edgar/data/7654321/0001234567-26-000001.txt\n"
        b"1234567|Owner Name|4|2026-08-31|edgar/data/1234567/0001234567-26-000001.txt",
    )
    rows = parse_daily_master_index(duplicated)
    assert len(rows) == 1
    assert rows[0].filer_cik == "0001234567"


def test_source_retains_partial_failure_without_advancing_past_valid_record() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("master.20260831.idx"):
            extra = INDEX.replace(
                b"10-K|2026-08-31|edgar/data/1234567/0001234567-26-000002.txt",
                b"4|2026-08-31|edgar/data/1234567/0001234567-26-000002.txt",
            )
            return httpx.Response(200, content=extra, request=request)
        if request.url.path.endswith("0001234567-26-000001.txt"):
            return httpx.Response(200, content=SUBMISSION, request=request)
        return httpx.Response(500, request=request)

    source = SECDailyIndexSource(
        "InsiderTurningEngine admin@example.com",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_attempts=1,
        sleeper=lambda _delay: None,
    )
    page = source.fetch_day(date(2026, 8, 31))
    assert len(page.records) == 1
    assert len(page.quarantines) == 1
    assert page.source_watermark is None


def test_daily_index_cache_is_content_addressed_and_replayable(tmp_path) -> None:
    requests: list[str] = []
    retrieved = iter(
        (
            datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
            datetime(2026, 9, 1, 0, 1, tzinfo=UTC),
            datetime(2026, 9, 1, 0, 2, tzinfo=UTC),
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        payload = INDEX if request.url.path.endswith("master.20260831.idx") else SUBMISSION
        return httpx.Response(200, content=payload, request=request)

    source = SECDailyIndexSource(
        "InsiderTurningEngine admin@example.com",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        cache_dir=tmp_path,
        sleeper=lambda _delay: None,
        clock=lambda: next(retrieved),
    )
    first = source.fetch_day(date(2026, 8, 31))
    count = len(requests)
    second = source.fetch_day(date(2026, 8, 31))
    assert len(first.records) == len(second.records) == 1
    assert first.records == second.records
    assert len(requests) == count

    manifest = next((tmp_path / "daily-index").glob("*.manifest.json"))
    manifest.write_text("{}", encoding="utf-8")
    source.fetch_day(date(2026, 8, 31))
    assert len(requests) > count

def test_submission_size_limit_defaults_to_25mb_and_can_be_boundedly_overridden() -> None:
    default_source = SECDailyIndexSource("InsiderTurningEngine admin@example.com")
    try:
        assert default_source.submission_maximum_bytes == DEFAULT_SUBMISSION_MAXIMUM_BYTES
    finally:
        default_source.close()

    override_source = SECDailyIndexSource(
        "InsiderTurningEngine admin@example.com",
        submission_maximum_bytes=MAX_CONFIGURABLE_SUBMISSION_BYTES,
    )
    try:
        assert override_source.submission_maximum_bytes == MAX_CONFIGURABLE_SUBMISSION_BYTES
    finally:
        override_source.close()


def test_submission_size_limit_rejects_values_above_hard_safety_bound() -> None:
    try:
        SECDailyIndexSource(
            "InsiderTurningEngine admin@example.com",
            submission_maximum_bytes=MAX_CONFIGURABLE_SUBMISSION_BYTES + 1,
        )
    except ValueError as exc:
        assert str(exc) == "SEC submission size limit is outside configured safety bounds"
    else:
        raise AssertionError("submission cap above the hard safety bound must be rejected")


def test_fetch_entry_uses_configured_submission_limit() -> None:
    entry = parse_daily_master_index(INDEX)[0]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=SUBMISSION, request=request)

    too_small = SECDailyIndexSource(
        "InsiderTurningEngine admin@example.com",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_attempts=1,
        submission_maximum_bytes=len(SUBMISSION) - 1,
        sleeper=lambda _delay: None,
        clock=lambda: datetime(2026, 9, 1, tzinfo=UTC),
    )
    try:
        try:
            too_small.fetch_entry(entry, index_hash="sha256:" + "1" * 64)
        except RuntimeError as exc:
            assert "SEC response exceeds configured size limit" in str(exc)
        else:
            raise AssertionError("configured submission cap must be enforced")
    finally:
        too_small.close()

    large_enough = SECDailyIndexSource(
        "InsiderTurningEngine admin@example.com",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_attempts=1,
        submission_maximum_bytes=len(SUBMISSION),
        sleeper=lambda _delay: None,
        clock=lambda: datetime(2026, 9, 1, tzinfo=UTC),
    )
    try:
        record = large_enough.fetch_entry(entry, index_hash="sha256:" + "1" * 64)
        assert record.accession_number == entry.accession_number
    finally:
        large_enough.close()

