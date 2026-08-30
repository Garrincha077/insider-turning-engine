from datetime import date
from decimal import Decimal

import httpx
import pytest

from insider_turning_engine.ingestion.market import (
    CsvMarketDataProvider,
    DailyBar,
    StooqMarketDataProvider,
    probe_market_coverage,
)

FIXTURE = "tests/fixtures/daily_market.csv"


def test_csv_provider_normalizes_sorts_and_slices_as_of() -> None:
    provider = CsvMarketDataProvider(FIXTURE, as_of_date=date(2026, 8, 14))
    bars = provider.get_daily_bars("ACME", as_of=date(2026, 8, 5))
    assert [bar.date for bar in bars] == [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)]
    assert bars[-1].close == Decimal("10.25")
    assert provider.get_weekly_bars("SPY")[0].volume == 255_000_000


@pytest.mark.parametrize(
    "row",
    [
        "2026-08-03,ACME,0,10.25,9.9,10.2,100",
        "2026-08-03,ACME,10,9,9.9,10.2,100",
        "2026-08-03,ACME,10,10.25,9.9,10.2,-1",
    ],
)
def test_csv_provider_rejects_economically_invalid_rows(row: str) -> None:
    with pytest.raises(ValueError):
        CsvMarketDataProvider(
            "date,ticker,open,high,low,close,adj_close,volume\n" + row,
            as_of_date=date(2026, 8, 14),
        )


def test_stooq_uses_injected_transport_and_caches() -> None:
    payload = "Date,Open,High,Low,Close,Volume\n2026-08-03,10,11,9,10.5,100\n"
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text=payload, request=request)

    provider = StooqMarketDataProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=lambda _delay: None,
    )
    assert provider.map_symbol("SPY") == "spy.us"
    assert provider.map_symbol("XLF.US") == "xlf.us"
    assert provider.get_daily_bars("SPY") == provider.get_daily_bars("SPY")
    assert len(calls) == 1
    assert "spy.us" in calls[0]


def test_stooq_rejects_redirect_responses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://example.com/"}, request=request)

    provider = StooqMarketDataProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_attempts=1,
        sleeper=lambda _delay: None,
    )
    with pytest.raises(RuntimeError, match="redirect"):
        provider.get_daily_bars("SPY")


def test_quality_probe_is_offline_and_quarantines_split_gap() -> None:
    bars = [
        DailyBar(
            date=date(2026, 8, 3),
            symbol="SPY",
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=1,
        ),
        DailyBar(
            date=date(2026, 8, 4),
            symbol="SPY",
            open=Decimal("50"),
            high=Decimal("51"),
            low=Decimal("49"),
            close=Decimal("50"),
            volume=1,
        ),
    ]
    report = probe_market_coverage(bars, ["SPY", "XLF"], as_of=date(2026, 8, 4))
    assert report.coverage_rate == 0.5
    assert report.missing_symbols == ("XLF",)
    assert report.split_discontinuity_symbols == ("SPY",)
    assert report.quarantined_symbols == ("SPY",)
