import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from insider_turning_engine.ingestion.market.yahoo_chart import YahooChartProvider


def _payload() -> bytes:
    return json.dumps(
        {
            "chart": {
                "error": None,
                "result": [
                    {
                        "timestamp": [1788163200, 1788249600],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [10.0, 11.0],
                                    "high": [12.0, 13.0],
                                    "low": [9.0, 10.0],
                                    "close": [11.0, 12.0],
                                    "volume": [100, 200],
                                }
                            ],
                            "adjclose": [{"adjclose": [5.5, 6.0]}],
                        },
                    }
                ],
            }
        }
    ).encode()


def test_yahoo_chart_parses_adjusted_ohlcv_and_provenance() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_payload(), request=request)

    provider = YahooChartProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    )
    bars = provider.fetch_daily("ABC")
    provider.close()

    assert len(bars) == 2
    assert bars[0].close == Decimal("5.50")
    assert bars[0].open == Decimal("5.00")
    assert bars[0].is_adjusted is True
    assert bars[0].provider == "yahoo-chart-experimental"
    assert bars[0].available_at is not None
    assert bars[0].available_at.tzinfo is UTC


def test_yahoo_chart_cache_is_content_addressed_and_replayable(tmp_path) -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, content=_payload(), request=request)

    provider = YahooChartProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
        cache_dir=tmp_path,
    )
    first = provider.fetch_daily("ABC")
    second = provider.fetch_daily("ABC")
    provider.close()

    assert first == second
    assert requests == 1
    manifest = next((tmp_path / "yahoo-chart").glob("*.manifest.json"))
    value = json.loads(manifest.read_text("utf-8"))
    assert value["sha256"].startswith("sha256:")
    assert datetime.fromisoformat(value["fetchedAt"]).tzinfo is not None


def test_yahoo_chart_rejects_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"Location": "https://example.com/data"},
            request=request,
        )

    provider = YahooChartProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    )
    try:
        try:
            provider.fetch_daily("ABC")
        except ValueError as exc:
            assert "redirect" in str(exc).lower()
        else:
            raise AssertionError("redirect should be rejected")
    finally:
        provider.close()


def test_yahoo_cache_with_zero_ttl_is_always_refetched(tmp_path) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=_payload(), request=request)

    provider = YahooChartProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        cache_dir=tmp_path, cache_ttl_seconds=0,
    )
    try:
        provider.fetch_daily("ABC")
        provider.fetch_daily("ABC")
        assert len(calls) == 2
    finally:
        provider.close()
