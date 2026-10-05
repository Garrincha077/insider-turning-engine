"""Closed-session cache replay is fast, honest and still fail-closed."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from insider_turning_engine.ingestion.market import DailyBar, RedundantEODProvider
from insider_turning_engine.ingestion.market.stooq import StooqMarketDataProvider
from insider_turning_engine.ingestion.market.yahoo_chart import YahooChartProvider

SESSION = date(2026, 10, 2)


class CachedSource:
    def __init__(self, name, cached_price=None, *, cached_date=SESSION, network_price="10"):
        self.name = name
        self.cached_price, self.cached_date = cached_price, cached_date
        self.network_price = network_price
        self.requests = []
        self.closed = False

    def rows(self, symbol, price, session):
        price = Decimal(price)
        return (DailyBar(symbol=symbol, date=session, open=price, high=price,
                         low=price, close=price, adj_close=price, volume=1,
                         provider=self.name),)

    def fetch_cached_daily(self, symbol):
        return None if self.cached_price is None else self.rows(
            symbol, self.cached_price, self.cached_date)

    def fetch_daily(self, symbol):
        self.requests.append(symbol)
        return self.rows(symbol, self.network_price, SESSION)

    def close(self):
        self.closed = True


def test_one_fresh_source_replays_without_recontacting_an_unavailable_source():
    sources = (CachedSource("primary"), CachedSource("fallback", "10"))
    provider = RedundantEODProvider(sources, cached_session=SESSION, max_source_workers=2)
    try:
        assert provider.fetch_daily(" aaa ")[0].provider == "fallback"
        assert all(not source.requests for source in sources)
        assert provider.selected_provider == {"AAA": "fallback"}
        assert provider.cache_replayed_symbols == {"AAA"}
        assert not provider.cross_validated_symbols  # Never claim two-source proof.
        assert not provider.failures  # An unrequested source is not a measured failure.
        assert "1 closed-session cache replays" in provider.health().message
    finally:
        provider.close()


def test_two_fresh_caches_still_cross_validate_and_keep_source_order():
    sources = (CachedSource("primary", "10"), CachedSource("fallback", "10.1"))
    provider = RedundantEODProvider(sources, cached_session=SESSION)
    try:
        assert provider.fetch_daily("AAA")[0].provider == "primary"
        assert provider.cross_validated_symbols == provider.cache_replayed_symbols == {"AAA"}
        assert all(not source.requests for source in sources)
    finally:
        provider.close()


def test_disagreeing_cached_prices_cannot_be_hidden_by_a_network_fallback():
    sources = (CachedSource("primary", "10"), CachedSource("fallback", "20"))
    provider = RedundantEODProvider(sources, cached_session=SESSION)
    try:
        with pytest.raises(RuntimeError, match="mismatch"):
            provider.fetch_daily("AAA")
        assert not provider.selected_provider and not provider.cache_replayed_symbols
        assert all(not source.requests for source in sources)
    finally:
        provider.close()


@pytest.mark.parametrize("cached_session", [None, SESSION])
def test_a_cache_without_the_required_session_does_not_avoid_normal_fetch(cached_session):
    sources = (CachedSource("primary", "10", cached_date=date(2026, 10, 1)),
               CachedSource("fallback"))
    provider = RedundantEODProvider(sources, cached_session=cached_session)
    try:
        assert provider.fetch_daily("AAA")[0].date == SESSION
        assert all(source.requests == ["AAA"] for source in sources)
        assert not provider.cache_replayed_symbols
        assert provider.cross_validated_symbols == {"AAA"}
    finally:
        provider.close()


def test_cached_replay_preserves_point_in_time_filters_and_clears_replay_metadata():
    sources = (CachedSource("primary", "10"), CachedSource("fallback", "10"))
    provider = RedundantEODProvider(sources, cached_session=SESSION)
    try:
        provider.fetch_daily("AAA", start=SESSION, end=SESSION, as_of=SESSION)
        assert provider.cache_replayed_symbols == {"AAA"}
        with pytest.raises(RuntimeError, match="all EOD"):
            provider.fetch_daily("AAA", as_of=date(2026, 10, 1))
        assert not provider.cache_replayed_symbols and not provider.selected_provider
    finally:
        provider.close()


def test_invalid_cache_read_uses_normal_bounded_fetch_instead_of_stopping_the_run():
    class BrokenCache(CachedSource):
        def fetch_cached_daily(self, symbol):
            raise ValueError("invalid cache metadata")

    sources = (BrokenCache("primary"), CachedSource("fallback"))
    provider = RedundantEODProvider(sources, cached_session=SESSION, max_source_workers=2)
    try:
        assert provider.fetch_daily("AAA")[0].provider == "primary"
        assert all(source.requests == ["AAA"] for source in sources)
        assert not provider.cache_replayed_symbols
        assert provider.cross_validated_symbols == {"AAA"}
    finally:
        provider.close()


@pytest.mark.parametrize("kind", ["stooq", "yahoo"])
def test_real_adapter_cache_read_is_offline_and_rejects_corrupt_or_stale_payload(tmp_path, kind):
    requests = []
    payload = (b"Date,Open,High,Low,Close,Volume\n2026-10-02,10,10,10,10,1\n"
               if kind == "stooq" else json.dumps({"chart": {"error": None, "result": [{
                   "timestamp": [int(datetime(2026, 10, 2, 15, tzinfo=UTC).timestamp())],
                   "indicators": {"quote": [{"open": [10], "high": [10], "low": [10],
                                              "close": [10], "volume": [1]}],
                                  "adjclose": [{"adjclose": [10]}]}}]}}).encode())

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=payload, request=request)

    cls = StooqMarketDataProvider if kind == "stooq" else YahooChartProvider
    provider = cls(client=httpx.Client(transport=httpx.MockTransport(handler)),
                   cache_dir=tmp_path, required_cache_session=SESSION)
    try:
        original = provider.fetch_daily("SPY")
        assert provider.fetch_cached_daily("SPY") == original and len(requests) == 1
        provider.required_cache_session = date(2026, 10, 5)
        assert provider.fetch_cached_daily("SPY") is None and len(requests) == 1
        provider.required_cache_session = SESSION
        root, suffix = ("stooq", "csv") if kind == "stooq" else ("yahoo-chart", "json")
        (tmp_path / root / f"spy.{suffix}").write_bytes(b"corrupt cached payload")
        assert provider.fetch_cached_daily("SPY") is None and len(requests) == 1
        # A new run has no independently validated in-memory copy from before
        # disk corruption; prove that its normal path refetches the bad cache.
        provider.close()
        provider = cls(client=httpx.Client(transport=httpx.MockTransport(handler)),
                       cache_dir=tmp_path, required_cache_session=SESSION)
        assert provider.fetch_daily("SPY") == original and len(requests) == 2
    finally:
        provider.close()
