"""Offline contract tests for the SEC company-submissions source."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from insider_turning_engine.ingestion.sec import SECIncrementalSource
from insider_turning_engine.ingestion.sec.base import SecOutcomeStatus, SecResult
from insider_turning_engine.ingestion.sec.historical import RequestPacer


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
        self.headers = headers or {"Content-Type": "application/json"}
        self.url = url
        self.history = history


class _Client:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> _Response:
        self.requests.append((url, kwargs))
        return self.responses.pop(0)


def _payload() -> bytes:
    return json.dumps(
        {
            "filings": {
                "recent": {
                    "accessionNumber": [
                        "0001999001-24-000002",
                        "0001999001-24-000001",
                        "0001999001-24-000003",
                    ],
                    "form": ["4", "8-K", "4/A"],
                    "acceptanceDateTime": [
                        "2024-01-02T15:04:05Z",
                        "2024-01-01T15:04:05Z",
                        "2024-01-03T15:04:05Z",
                    ],
                    "primaryDocument": ["b.xml", "ignored.xml", "c.xml"],
                }
            }
        }
    ).encode()


def _source(client: _Client, cache_dir: Path | None = None) -> SECIncrementalSource:
    return SECIncrementalSource(
        [1999001],
        "insider-engine test@example.com",
        cache_dir=cache_dir,
        client=client,
        pacer=RequestPacer(sleeper=lambda _: None),
        sleeper=lambda _: None,
        clock=lambda: datetime(2024, 1, 5, tzinfo=UTC),
    )


def test_filters_sorts_and_requires_identifying_user_agent() -> None:
    client = _Client([_Response(_payload())])
    page = _source(client).fetch(
        since=datetime(2024, 1, 1, tzinfo=UTC),
        through=datetime(2024, 1, 2, 23, 59, tzinfo=UTC),
    )
    assert [record.accession_number for record in page.records] == ["0001999001-24-000002"]
    assert page.records[0].source_url.endswith("/000199900124000002/b.xml")
    assert client.requests[0][1]["headers"] == {
        "User-Agent": "insider-engine test@example.com",
        "Accept": "application/json",
    }


def test_malformed_array_is_quarantined() -> None:
    payload = {"filings": {"recent": {"accessionNumber": [], "form": ["4"]}}}
    page = _source(_Client([_Response(json.dumps(payload).encode())])).fetch()
    assert not page.records
    assert {item.reason_code for item in page.quarantines} == {"SEC_SUBMISSIONS_ARRAY"}


def test_cursor_is_strict_and_primary_xml_is_hashed_and_cached(tmp_path: Path) -> None:
    client = _Client(
        [
            _Response(_payload()),
            _Response(b"<ownershipDocument />", headers={"Content-Type": "application/xml"}),
            _Response(_payload()),
        ]
    )
    source = _source(client, tmp_path)
    page = source.fetch()
    assert len(page.records) == 2
    raw = source.get(page.records[0].provider_record_id)
    assert raw.content_hash == "sha256:" + hashlib.sha256(b"<ownershipDocument />").hexdigest()
    assert source.get(page.records[0].provider_record_id) == raw
    assert list(tmp_path.rglob("*.manifest.json"))
    assert not source.fetch(cursor=page.next_cursor).records
    assert len(client.requests) == 3


@pytest.mark.parametrize(
    "response",
    [
        _Response(_payload(), status_code=302),
        _Response(_payload(), url="https://evil.example/submissions.json"),
        _Response(_payload(), headers={"Content-Type": "text/html"}),
    ],
)
def test_submissions_reject_redirect_effective_host_and_content_type(response: _Response) -> None:
    page = _source(_Client([response])).fetch()
    assert not page.records
    assert [item.reason_code for item in page.quarantines] == ["SEC_REQUEST_FAILED"]


def test_submissions_reject_body_over_limit() -> None:
    source = SECIncrementalSource(
        [1999001],
        "insider-engine test@example.com",
        client=_Client([_Response(_payload())]),
        pacer=RequestPacer(sleeper=lambda _: None),
        sleeper=lambda _: None,
        max_attempts=1,
        max_submissions_bytes=10,
    )
    page = source.fetch()
    assert not page.records
    assert "size limit" in page.quarantines[0].message


def test_filing_cache_preserves_and_validates_original_provenance(tmp_path: Path) -> None:
    first_client = _Client(
        [
            _Response(_payload()),
            _Response(b"<ownershipDocument />", headers={"Content-Type": "application/xml"}),
        ]
    )
    first = SECIncrementalSource(
        [1999001],
        "insider-engine test@example.com",
        cache_dir=tmp_path,
        client=first_client,
        pacer=RequestPacer(sleeper=lambda _: None),
        sleeper=lambda _: None,
        clock=lambda: datetime(2024, 1, 5, tzinfo=UTC),
    )
    first_reference = first.fetch().records[0]
    first_raw = first.get(first_reference.provider_record_id)
    assert not isinstance(first_raw, SecResult)

    replay_client = _Client([_Response(_payload())])
    replay = SECIncrementalSource(
        [1999001],
        "insider-engine test@example.com",
        cache_dir=tmp_path,
        client=replay_client,
        pacer=RequestPacer(sleeper=lambda _: None),
        sleeper=lambda _: None,
        clock=lambda: datetime(2024, 1, 10, tzinfo=UTC),
    )
    replay_reference = replay.fetch().records[0]
    replay_raw = replay.get(replay_reference.provider_record_id)
    assert not isinstance(replay_raw, SecResult)
    assert replay_raw.retrieved_at == first_raw.retrieved_at
    assert len(replay_client.requests) == 1

    manifest = next((tmp_path / "filings").rglob("*.manifest.json"))
    manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_value["provider_record_id"] = "0001999001-24-999999"
    manifest.write_text(json.dumps(manifest_value), encoding="utf-8")

    refetch_client = _Client(
        [
            _Response(_payload()),
            _Response(b"<ownershipDocument />", headers={"Content-Type": "application/xml"}),
        ]
    )
    refetch = SECIncrementalSource(
        [1999001],
        "insider-engine test@example.com",
        cache_dir=tmp_path,
        client=refetch_client,
        pacer=RequestPacer(sleeper=lambda _: None),
        sleeper=lambda _: None,
        clock=lambda: datetime(2024, 1, 12, tzinfo=UTC),
    )
    refetch_reference = refetch.fetch().records[0]
    refetched_raw = refetch.get(refetch_reference.provider_record_id)
    assert not isinstance(refetched_raw, SecResult)
    assert refetched_raw.retrieved_at == datetime(2024, 1, 12, tzinfo=UTC)
    assert len(refetch_client.requests) == 2


def test_filing_rejects_wrong_content_type() -> None:
    source = _source(_Client([_Response(_payload()), _Response(b"<html />")]))
    reference = source.fetch().records[0]
    result = source.get(reference.provider_record_id)
    assert isinstance(result, SecResult)
    assert result.status is SecOutcomeStatus.PERMANENT_INVALID
    assert "Content-Type" in result.message
