import json
import threading

import httpx
import pytest

from insider_turning_engine.ingestion.market.yahoo_chart import YahooChartProvider
from insider_turning_engine.pipeline import daily_research
from insider_turning_engine.pipeline import live_experimental as live


class FakeProvider:
    def __init__(self, providers):
        for provider in providers:
            assert provider.client.timeout.read == 8.0
            provider.close()
        self.selected_provider = {}
        self.cross_validated_symbols = set()
        self.closed = False

    def close(self):
        self.closed = True


def test_parallel_fetch_is_bounded_and_preserves_deterministic_inventory(tmp_path, monkeypatch):
    barrier = threading.Barrier(4)
    instances = []

    class Provider(FakeProvider):
        def __init__(self, providers):
            super().__init__(providers)
            instances.append(self)

        def fetch_daily(self, symbol):
            barrier.wait(timeout=5)
            if symbol == "BAD":
                raise RuntimeError("unavailable")
            self.selected_provider[symbol] = "fixture"
            self.cross_validated_symbols.add(symbol)
            return ()

    monkeypatch.setattr(live, "RedundantEODProvider", Provider)
    bars, failed, sources, cross = live._fetch_market(
        ["DDD", "AAA", "BAD", "CCC", "AAA"], cache_dir=tmp_path, max_workers=4,
        budget_seconds=20)
    assert list(bars) == ["AAA", "CCC", "DDD"]
    assert failed == {"BAD": "unavailable"}
    assert list(sources) == list(bars) and cross == set(bars)
    assert len(instances) == 1 and instances[0].closed


def test_expired_budget_never_starts_queued_network_requests(tmp_path, monkeypatch):
    ticks = iter([0.0, 0.5, 2.0, 2.0])
    monkeypatch.setattr(live.time, "monotonic", lambda: next(ticks))
    requests = []

    class Provider(FakeProvider):
        def fetch_daily(self, symbol):
            requests.append(symbol)
            return ()

    monkeypatch.setattr(live, "RedundantEODProvider", Provider)
    bars, failed, _, _ = live._fetch_market(
        ["AAA", "BBB", "CCC"], cache_dir=tmp_path, budget_seconds=1)
    assert requests == ["AAA"] and list(bars) == ["AAA"]
    assert failed == dict.fromkeys(["BBB", "CCC"], "MARKET_REFRESH_BUDGET_EXHAUSTED")


@pytest.mark.parametrize("workers,budget", [(0, 1), (5, 1), (1, 0), (1, -1)])
def test_invalid_refresh_bounds_fail_before_network(tmp_path, workers, budget):
    with pytest.raises(ValueError, match="workers"):
        live._fetch_market([], cache_dir=tmp_path, max_workers=workers, budget_seconds=budget)


def test_shards_record_scrubbed_partial_coverage_and_budget_reason(tmp_path, monkeypatch):
    def fetch(symbols, **kwargs):
        assert kwargs["max_workers"] == 4 and kwargs["budget_seconds"] == 1800
        assert kwargs["required_cache_session"] is not None
        return ({symbol: () for symbol in symbols if symbol == "AAA"},
                {symbol: "MARKET_REFRESH_BUDGET_EXHAUSTED" if symbol == "BBB"
                 else "private provider diagnostic" for symbol in symbols if symbol != "AAA"},
                {}, set())

    monkeypatch.setattr(daily_research, "_fetch_market", fetch)
    bars, failed = daily_research.market_shards(["CCC", "BBB", "AAA"],
                                               cache_dir=tmp_path / "market")
    report = json.loads((tmp_path / "market-status.json").read_text())
    assert report["requested"] == 3 and report["available"] == len(bars) == 1
    assert report["status"] == "PARTIAL" and report["failures"] == failed
    assert failed["BBB"] == "MARKET_REFRESH_BUDGET_EXHAUSTED"
    assert "private" not in json.dumps(report)


def test_yahoo_timeout_is_configurable_without_changing_parsing():
    provider = YahooChartProvider(timeout=8)
    assert provider.client.timeout == httpx.Timeout(8)
    provider.close()


def test_benchmarks_are_requested_before_stocks_when_budget_expires(tmp_path, monkeypatch):
    ticks = iter([0.0, 0.1, 0.2, 2.0, 2.0])
    monkeypatch.setattr(live.time, "monotonic", lambda: next(ticks))
    requests = []

    class Provider(FakeProvider):
        def fetch_daily(self, symbol):
            requests.append(symbol)
            return ()

    monkeypatch.setattr(live, "RedundantEODProvider", Provider)
    bars, failed, _, _ = live._fetch_market(
        ["AAA", "BBB", "XLK", "SPY", "SPY"], cache_dir=tmp_path,
        priority_symbols=["XLK", "SPY", "NOT_REQUESTED"], budget_seconds=1)
    assert requests == ["SPY", "XLK"]
    assert list(bars) == ["SPY", "XLK"]
    assert failed == dict.fromkeys(["AAA", "BBB"], "MARKET_REFRESH_BUDGET_EXHAUSTED")


def test_shards_forward_benchmark_priority_without_changing_requested_inventory(tmp_path,
                                                                              monkeypatch):
    calls = []

    def fetch(symbols, **kwargs):
        assert kwargs["priority_symbols"] == ("SPY", "XLK")
        assert kwargs["max_workers"] == 4 and kwargs["budget_seconds"] == 1800
        assert kwargs["required_cache_session"] is not None
        calls.append(tuple(symbols))
        return dict.fromkeys(symbols, ()), {}, {}, set()

    monkeypatch.setattr(daily_research, "_fetch_market", fetch)
    bars, failed = daily_research.market_shards(
        ["CCC", "AAA", "SPY", "XLK", "AAA"], cache_dir=tmp_path / "market",
        priority_symbols=("SPY", "XLK"))
    assert sorted(symbol for shard in calls for symbol in shard) == ["AAA", "CCC", "SPY", "XLK"]
    assert len(calls) == 3 and set(bars) == {"AAA", "CCC", "SPY", "XLK"}
    assert not failed
