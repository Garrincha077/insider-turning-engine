"""Session freshness supersedes TTL, but never checksum/source validation."""

import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from test_yahoo_chart import _payload

from insider_turning_engine.ingestion.market.stooq import StooqMarketDataProvider
from insider_turning_engine.ingestion.market.yahoo_chart import YahooChartProvider


@pytest.mark.parametrize("source", ["stooq", "yahoo"])
@pytest.mark.parametrize("change", ["expired_fresh_session", "missing_session", "bad_hash"])
def test_session_cache_reuses_only_valid_payload_with_required_session(tmp_path, source, change):
    calls = []
    payload = (_payload() if source == "yahoo" else
               b"Date,Open,High,Low,Close,Volume\n2026-09-01,10,11,9,10.5,100\n")

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=payload, request=request)

    factory = YahooChartProvider if source == "yahoo" else StooqMarketDataProvider
    kwargs = dict(cache_dir=tmp_path, cache_ttl_seconds=0)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        original = factory(client=client, **kwargs).fetch_daily("ACME")
    manifest_path = next(tmp_path.rglob("*.manifest.json"))
    manifest = json.loads(manifest_path.read_bytes())
    manifest["fetchedAt"] = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    if change == "bad_hash":
        manifest["sha256"] = "sha256:" + "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    required = date(2026, 9, 2) if change == "missing_session" else date(2026, 9, 1)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = factory(client=client, required_cache_session=required, **kwargs)
        replay = provider.fetch_daily("ACME")
    assert replay == original
    assert len(calls) == (1 if change == "expired_fresh_session" else 2)


@pytest.mark.parametrize("source", ["stooq", "yahoo"])
def test_stale_session_hint_skips_expensive_bar_parsing_but_cannot_prove_freshness(
    tmp_path, source, monkeypatch,
):
    payload = (_payload() if source == "yahoo" else
               b"Date,Open,High,Low,Close,Volume\n2026-09-01,10,11,9,10.5,100\n")
    factory = YahooChartProvider if source == "yahoo" else StooqMarketDataProvider
    with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=payload, request=request))) as client:
        factory(client=client, cache_dir=tmp_path).fetch_daily("ACME")
    provider = factory(cache_dir=tmp_path, required_cache_session=date(2026, 9, 2))
    try:
        original_parse = provider._parse
        monkeypatch.setattr(provider, "_parse", lambda *args: pytest.fail("stale hint parsed"))
        assert provider.fetch_cached_daily("ACME") is None
        monkeypatch.setattr(provider, "_parse", original_parse)
        manifest_path = next(tmp_path.rglob("*.manifest.json"))
        manifest = json.loads(manifest_path.read_bytes())
        # A forged future hint must not turn actual earlier bars into fresh data.
        manifest["lastSession"] = "2099-01-01"
        manifest_path.write_text(json.dumps(manifest))
        assert provider.fetch_cached_daily("ACME") is None
        provider.required_cache_session = date(2026, 9, 1)
        manifest.pop("lastSession")
        manifest_path.write_text(json.dumps(manifest))
        assert provider.fetch_cached_daily("ACME")  # Legacy manifests still work.
    finally:
        provider.close()


def test_yahoo_fresh_session_cache_materializes_bars_only_once(tmp_path, monkeypatch):
    with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=_payload(), request=request))) as client:
        provider = YahooChartProvider(client=client, cache_dir=tmp_path,
                                      required_cache_session=date(2026, 9, 1))
        expected = provider.fetch_daily("ACME")
        original_parse = provider._parse
        calls = []

        def parse(*args):
            calls.append(args[1])
            return original_parse(*args)

        monkeypatch.setattr(provider, "_parse", parse)
        assert provider.fetch_cached_daily("ACME") == expected
        assert calls == ["ACME"]
        assert provider.fetch_daily("ACME") == expected
        assert calls == ["ACME", "ACME"]


def test_yahoo_invalid_network_payload_is_not_committed_to_cache(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"{}", request=request))) as client:
        provider = YahooChartProvider(client=client, cache_dir=tmp_path)
        with pytest.raises(ValueError, match="schema"):
            provider.fetch_daily("ACME")
        assert not list(tmp_path.rglob("*.manifest.json"))
