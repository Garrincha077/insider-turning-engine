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
