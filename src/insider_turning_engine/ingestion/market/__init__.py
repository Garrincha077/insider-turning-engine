"""Market data contracts and deterministic/provider-backed adapters."""

from .base import CoverageReport, DailyBar, MarketDataProvider, ProviderHealth
from .csv_provider import CsvMarketDataProvider, CsvProvider
from .quality import (
    assess_market_quality,
    probe_50_symbols,
    probe_coverage,
    probe_market_coverage,
)
from .stooq import (
    SECTOR_ETFS,
    STOOQ_SYMBOL_MAP,
    SUPPORTED_SYMBOLS,
    StooqMarketDataProvider,
    StooqProvider,
)

__all__ = [
    "CoverageReport",
    "DailyBar",
    "MarketDataProvider",
    "ProviderHealth",
    "CsvMarketDataProvider",
    "CsvProvider",
    "StooqMarketDataProvider",
    "StooqProvider",
    "SECTOR_ETFS",
    "STOOQ_SYMBOL_MAP",
    "SUPPORTED_SYMBOLS",
    "probe_market_coverage",
    "probe_coverage",
    "probe_50_symbols",
    "assess_market_quality",
]
