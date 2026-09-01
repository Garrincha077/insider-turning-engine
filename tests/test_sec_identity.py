from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from insider_turning_engine.ingestion.sec.historical import RequestPacer
from insider_turning_engine.ingestion.sec.identity import (
    COMPANY_TICKERS_EXCHANGE_URL,
    SECCompanyTickerSource,
    parse_company_tickers_exchange,
)


def _payload() -> bytes:
    return json.dumps(
        {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [
                [7, "Good Holdings", "GOOD", "NYSE"],
                [8, "Acquisition Corp", "BAD", "Nasdaq"],
                [9, "Off Exchange", "OTC", "OTCQX"],
                ["not-a-cik", "Malformed", "NOPE", "NYSE"],
            ],
        }
    ).encode()


def _source(client: object, **kwargs: object) -> SECCompanyTickerSource:
    return SECCompanyTickerSource(
        "insider-engine test@example.com",
        client=client,
        pacer=RequestPacer(sleeper=lambda _delay: None),
        sleeper=lambda _delay: None,
        clock=lambda: datetime(2026, 9, 1, tzinfo=UTC),
        **kwargs,
    )


def test_parser_normalizes_cik_and_orders_rows() -> None:
    payload = json.dumps(
        {"fields": ["cik", "name", "ticker", "exchange"], "data": [[7, "Good", "GOOD", "NYSE"]]}
    ).encode()
    rows = parse_company_tickers_exchange(
        payload, retrieved_at=datetime(2026, 9, 1, tzinfo=UTC)
    )
    assert rows[0].cik == "0000000007"
    assert rows[0].knowledge_at == datetime(2026, 9, 1, tzinfo=UTC)
    assert rows[0].provenance["mapping_status"] == "current"
    assert rows[0].provenance["survivorship_caveat"] is True


def test_fetch_quarantines_malformed_and_applies_exchange_name_filtering() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_payload(),
            headers={"Content-Type": "application/json"},
            request=request,
        )

    result = _source(httpx.Client(transport=httpx.MockTransport(handler))).fetch()
    assert [row.ticker for row in result.records] == ["GOOD"]
    assert result.excluded_count == 2
    assert result.quarantines[0].reason_code == "SEC_COMPANY_TICKER_ROW_INVALID"


@pytest.mark.parametrize(
    "response, message",
    [
        (httpx.Response(302, headers={"Location": "https://evil.example/"}), "redirect"),
        (httpx.Response(200, headers={"Content-Type": "text/html"}), "Content-Type"),
    ],
)
def test_fetch_rejects_redirect_and_content_type(response: httpx.Response, message: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        response.request = request
        return response

    with pytest.raises(RuntimeError, match=message):
        _source(httpx.Client(transport=httpx.MockTransport(handler)), max_attempts=1).fetch()


def test_fetch_rejects_oversize_before_cache(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_payload(),
            headers={"Content-Type": "application/json"},
            request=request,
        )

    with pytest.raises(RuntimeError, match="size limit"):
        _source(
            httpx.Client(transport=httpx.MockTransport(handler)),
            cache_dir=tmp_path,
            max_attempts=1,
            max_bytes=10,
        ).fetch()
    assert not list(tmp_path.rglob("*.manifest.json"))


def test_disk_cache_replays_content_addressed_payload(tmp_path) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(
            200,
            content=_payload(),
            headers={"Content-Type": "application/json"},
            request=request,
        )

    first = _source(
        httpx.Client(transport=httpx.MockTransport(handler)), cache_dir=tmp_path
    ).fetch()
    second = _source(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(AssertionError("network"))
            )
        ),
        cache_dir=tmp_path,
    ).fetch()
    assert second.cache_hit
    assert first.records == second.records
    assert len(requests) == 1
    manifest = next(tmp_path.rglob("*.manifest.json"))
    values = json.loads(manifest.read_text())
    assert values["byteLength"] == len(_payload())
    assert values["retrievedAt"]
    assert values["checksum"].startswith("sha256:")


def test_source_url_must_use_sec_https_allowlist() -> None:
    with pytest.raises(ValueError, match="allowlist"):
        SECCompanyTickerSource("project test@example.com", url="http://evil.example/x")
    assert COMPANY_TICKERS_EXCHANGE_URL.startswith("https://www.sec.gov/")
