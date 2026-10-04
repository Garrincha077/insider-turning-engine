"""Bounded source concurrency must not change market selection or validation."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

import pytest

from insider_turning_engine.ingestion.market import DailyBar, RedundantEODProvider


class Source:
    def __init__(self, name, *, price="10", session=date(2026, 10, 2), action=None, history=()):
        self.name, self.price, self.session, self.action = name, price, session, action
        self.history = history
        self.closed = False

    def fetch_daily(self, symbol):
        if self.action is not None:
            self.action()
        if self.price is None:
            raise RuntimeError("source unavailable")
        price = Decimal(self.price)
        return tuple(DailyBar(date=session, symbol=symbol, open=price, high=price,
                         low=price, close=price, adj_close=price, volume=1,
                         provider=self.name) for session in (*self.history, self.session))

    def close(self):
        self.closed = True


def test_sources_overlap_in_one_fetch_and_order_does_not_follow_completion():
    fallback_finished = threading.Event()

    def primary():
        assert fallback_finished.wait(timeout=5), "fallback must start before primary finishes"

    sources = (Source("primary", action=primary),
               Source("fallback", action=fallback_finished.set))
    provider = RedundantEODProvider(sources, max_source_workers=2)
    try:
        rows = provider.fetch_daily(" aaa ")
        assert rows[0].provider == provider.selected_provider["AAA"] == "primary"
        assert provider.cross_validated_symbols == {"AAA"}
        assert not provider.failures
    finally:
        provider.close()
    assert all(source.closed for source in sources)


def test_source_pool_is_shared_and_bounded_across_concurrent_symbols():
    condition, release = threading.Condition(), threading.Event()
    active = peak = started = 0

    def action():
        nonlocal active, peak, started
        with condition:
            active += 1
            started += 1
            peak = max(peak, active)
            condition.notify_all()
        try:
            assert release.wait(timeout=5)
        finally:
            with condition:
                active -= 1

    sources = (Source("primary", action=action), Source("fallback", action=action))
    provider = RedundantEODProvider(sources, max_source_workers=2)
    with ThreadPoolExecutor(max_workers=2) as callers:
        jobs = [callers.submit(provider.fetch_daily, symbol) for symbol in ("AAA", "BBB")]
        try:
            with condition:
                assert condition.wait_for(lambda: started == 2, timeout=5)
                assert active == 2
            release.set()
            assert [job.result()[0].symbol for job in jobs] == ["AAA", "BBB"]
            assert peak == 2 and started == 4 and active == 0
            assert provider.cross_validated_symbols == {"AAA", "BBB"}
        finally:
            release.set()
            provider.close()


def test_close_drains_in_flight_requests_before_closing_source_clients():
    entered = threading.Barrier(3)
    release, closing_started, closed = threading.Event(), threading.Event(), threading.Event()

    def action():
        entered.wait(timeout=5)
        assert release.wait(timeout=5)
        assert not any(source.closed for source in sources)

    sources = (Source("primary", action=action), Source("fallback", action=action))
    provider = RedundantEODProvider(sources, max_source_workers=2)

    def close():
        closing_started.set()
        provider.close()
        closed.set()

    with ThreadPoolExecutor(max_workers=2) as callers:
        fetching = callers.submit(provider.fetch_daily, "AAA")
        try:
            entered.wait(timeout=5)
            closing = callers.submit(close)
            assert closing_started.wait(timeout=5)
            assert not closed.is_set() and not any(source.closed for source in sources)
            release.set()
            assert fetching.result()[0].provider == "primary"
            closing.result()
            assert closed.is_set() and all(source.closed for source in sources)
        finally:
            release.set()
            provider.close()


@pytest.mark.parametrize("workers", [1, 2, 8])
def test_parallel_and_sequential_paths_keep_fallback_and_failure_metadata(workers):
    provider = RedundantEODProvider((Source("primary", price=None), Source("fallback")),
                                    max_source_workers=workers)
    try:
        assert provider.fetch_daily("AAA")[0].provider == "fallback"
        assert provider.selected_provider == {"AAA": "fallback"}
        assert provider.failures == {"AAA": {"primary": "RuntimeError"}}
        assert not provider.cross_validated_symbols
    finally:
        provider.close()


@pytest.mark.parametrize("primary,fallback,match", [
    (Source("primary", price="10"), Source("fallback", price="20"), "mismatch"),
    (Source("primary", session=date(2026, 10, 1)), Source("fallback"), "overlapping"),
    (Source("primary", price=None), Source("fallback", price=None), "all EOD"),
])
def test_parallel_does_not_bypass_source_disagreement_or_missing_data(primary, fallback, match):
    provider = RedundantEODProvider((primary, fallback), max_source_workers=2)
    try:
        with pytest.raises(RuntimeError, match=match):
            provider.fetch_daily("AAA")
        assert not provider.selected_provider and not provider.cross_validated_symbols
    finally:
        provider.close()


@pytest.mark.parametrize("workers", [1, 2])
def test_freshest_source_and_point_in_time_filters_are_unchanged(workers):
    provider = RedundantEODProvider((Source("primary", session=date(2026, 10, 1)),
                                    Source("fallback")), max_source_workers=workers)
    try:
        assert provider.fetch_daily("AAA", as_of=date(2026, 10, 1))[0].provider == "primary"
        assert provider.failures["AAA"] == {"fallback": "ValueError"}
        with pytest.raises(RuntimeError, match="overlapping"):
            provider.fetch_daily("AAA")
    finally:
        provider.close()


@pytest.mark.parametrize("workers", [1, 2])
def test_freshest_history_wins_after_cross_validation_not_fastest_source(workers):
    provider = RedundantEODProvider((Source("primary", session=date(2026, 10, 1)),
                                    Source("fallback", history=(date(2026, 10, 1),))),
                                   max_source_workers=workers)
    try:
        rows = provider.fetch_daily("AAA")
        assert len(rows) == 2 and rows[-1].date == date(2026, 10, 2)
        assert provider.selected_provider == {"AAA": "fallback"}
        assert provider.cross_validated_symbols == {"AAA"}
        rows = provider.fetch_daily("AAA", end=date(2026, 10, 1), start=date(2026, 10, 1))
        assert len(rows) == 1 and rows[0].provider == "primary"
        assert provider.selected_provider == {"AAA": "primary"}
    finally:
        provider.close()


@pytest.mark.parametrize("workers", [0, 9, -1])
def test_invalid_source_worker_bounds_are_rejected(workers):
    with pytest.raises(ValueError, match="source workers"):
        RedundantEODProvider((Source("primary"), Source("fallback")), max_source_workers=workers)
