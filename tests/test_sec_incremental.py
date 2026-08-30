"""Offline contract tests for the SEC company-submissions source."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from insider_turning_engine.ingestion.sec import SECIncrementalSource
from insider_turning_engine.ingestion.sec.historical import RequestPacer


class _Response:
    def __init__(
        self, body: bytes, status_code: int = 200, headers: dict[str, str] | None = None
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
        [_Response(_payload()), _Response(b"<ownershipDocument />"), _Response(_payload())]
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
