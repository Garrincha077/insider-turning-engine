from datetime import UTC, date, datetime

from insider_turning_engine.normalization.identity import (
    IssuerIdentityIndex,
    TickerInterval,
    evaluate_security_universe,
    filter_security_universe,
    map_sic_to_sector_etf,
    normalize_cik,
)


def test_cik_is_the_stable_ten_digit_issuer_key() -> None:
    assert normalize_cik("CIK-1234") == "0000001234"
    assert normalize_cik(1234) == "0000001234"
    assert normalize_cik("12345678901") is None


def test_filing_symbol_wins_and_current_mapping_is_explicit_fallback() -> None:
    index = IssuerIdentityIndex.from_records(
        [
            {
                "cik": "1",
                "name": "Example, Inc.",
                "ticker": "OLD",
                "valid_from": "2020-01-01",
                "valid_to": "2024-01-01",
            }
        ],
        sec_current_mapping={"NEW": "1"},
    )
    filing = index.resolve(
        {
            "issuerCik": "1",
            "issuerTradingSymbol": "FILE",
            "acceptedAt": "2020-12-31T21:00:00Z",
        },
        as_of="2021-01-01",
    )
    assert filing.ticker == "FILE"
    assert filing.provenance["source"] == "filing_issuerTradingSymbol"
    historical = index.resolve_ticker("1", as_of="2021-01-01")
    assert historical.ticker == "OLD"
    current = index.resolve_ticker("1")
    assert current.ticker == "NEW"
    assert current.provenance["historical_mapping_caveat"] is True


def test_historical_resolution_withholds_future_filing_and_unversioned_current_mapping() -> None:
    index = IssuerIdentityIndex.from_records([], sec_current_mapping={"NOW": "1"})
    future_filing = index.resolve(
        {
            "issuerCik": "1",
            "issuerTradingSymbol": "FUTR",
            "acceptedAt": "2025-01-02T21:00:00Z",
        },
        as_of="2024-12-31",
    )
    assert future_filing.ticker is None
    assert future_filing.provenance["source"] == "sec_current_mapping_withheld"

    unknown_filing_time = index.resolve(
        {"issuerCik": "1", "issuerTradingSymbol": "UNKNOWN"}, as_of="2024-12-31"
    )
    assert unknown_filing_time.ticker is None


def test_date_only_identity_cutoff_rejects_same_day_knowledge_after_market_close() -> None:
    index = IssuerIdentityIndex.from_records([])
    filing = {
        "issuerCik": "1",
        "issuerTradingSymbol": "LATE",
        # US regular-session close is 21:00 UTC in January.
        "acceptedAt": "2024-01-02T21:00:01Z",
    }

    assert index.resolve(filing, as_of=date(2024, 1, 2)).ticker is None
    assert (
        index.resolve(
            filing,
            as_of=datetime(2024, 1, 2, 21, 0, 1, tzinfo=UTC),
        ).ticker
        == "LATE"
    )

    interval_index = IssuerIdentityIndex(
        ticker_intervals=[
            TickerInterval(
                "0000000001",
                "LATE",
                valid_from=date(2020, 1, 1),
                knowledge_at=datetime(2024, 1, 2, 21, 0, 1, tzinfo=UTC),
            )
        ]
    )
    assert interval_index.resolve_ticker("1", date(2024, 1, 2)).ticker is None
    assert interval_index.resolve_ticker("1", date(2024, 1, 3)).ticker == "LATE"


def test_dated_current_mapping_can_be_used_only_after_it_was_known() -> None:
    index = IssuerIdentityIndex(
        sec_current_mapping=[
            TickerInterval(
                "0000000001",
                "KNOWN",
                source="sec_current_mapping",
                knowledge_at=date(2024, 1, 2),
            )
        ]
    )
    assert index.resolve_ticker("1", date(2024, 1, 1)).ticker is None
    assert index.resolve_ticker("1", date(2024, 1, 2)).ticker == "KNOWN"


def test_valid_time_ticker_resolution_is_deterministic() -> None:
    index = IssuerIdentityIndex(
        ticker_intervals=[
            TickerInterval("0000000001", "OLD", date(2020, 1, 1), date(2022, 1, 1)),
            TickerInterval("0000000001", "NEW", date(2022, 1, 1), None),
        ]
    )
    assert index.resolve_ticker("1", date(2021, 6, 1)).ticker == "OLD"
    assert index.resolve_ticker("1", date(2022, 1, 1)).ticker == "NEW"


def test_future_known_ticker_is_not_used_before_knowledge_date() -> None:
    index = IssuerIdentityIndex(
        ticker_intervals=[
            TickerInterval(
                "0000000001",
                "NEW",
                date(2020, 1, 1),
                None,
                knowledge_at=date(2025, 1, 1),
            )
        ]
    )
    assert index.resolve_ticker("1", date(2021, 1, 1)).ticker is None
    assert index.resolve_ticker("1", date(2025, 1, 1)).ticker == "NEW"


def test_universe_excludes_non_operating_and_non_common_securities() -> None:
    good = {
        "cik": "1",
        "name": "Example Inc",
        "exchange": "NASDAQ",
        "security_type": "Common Stock",
        "country": "US",
    }
    assert evaluate_security_universe(good).include
    assert not evaluate_security_universe({**good, "exchange": "OTCQX"}).include
    assert not evaluate_security_universe({**good, "security_type": "ETF"}).include
    assert not evaluate_security_universe({**good, "name": "Example Acquisition Corp"}).include
    assert not evaluate_security_universe(
        {**good, "knowledge_at": "2025-01-01"}, as_of="2021-01-01"
    ).include
    assert not evaluate_security_universe(
        {**good, "knowledge_at": "2024-01-02T21:00:01Z"},
        as_of=date(2024, 1, 2),
    ).include


def test_universe_accepts_record_collections_and_sector_mapping_is_versioned() -> None:
    records = [
        {"cik": "1", "name": "A", "exchange": "NYSE"},
        {"cik": "2", "name": "B ETF", "exchange": "NYSE"},
    ]
    assert len(filter_security_universe(records)) == 1
    result = map_sic_to_sector_etf("1311")
    assert result == "XLE"
    assert result.mapping_version == "1.0.0"
    assert result.provenance["historical_mapping_caveat"] is True
    assert map_sic_to_sector_etf("9999") == "UNKNOWN"
