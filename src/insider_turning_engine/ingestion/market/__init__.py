"""Market data contracts and deterministic/provider-backed adapters."""

from .base import CoverageReport, DailyBar, MarketDataProvider, ProviderHealth
from .csv_provider import CsvMarketDataProvider, CsvProvider
from .quality import (
    assess_market_quality,
    probe_50_symbols,
    probe_coverage,
    probe_market_coverage,
)
from .redundant import RedundantEODProvider
from .stooq import (
    MAX_SHARD_COUNT,
    SECTOR_ETFS,
    STOOQ_SYMBOL_MAP,
    SUPPORTED_SYMBOLS,
    MarketFetchBatch,
    StooqMarketDataProvider,
    StooqProvider,
)
from .yahoo_chart import YAHOO_CHART_ROOT, YahooChartProvider

__all__ = [
    "CoverageReport",
    "DailyBar",
    "MarketDataProvider",
    "ProviderHealth",
    "RedundantEODProvider",
    "CsvMarketDataProvider",
    "CsvProvider",
    "StooqMarketDataProvider",
    "StooqProvider",
    "MarketFetchBatch",
    "MAX_SHARD_COUNT",
    "SECTOR_ETFS",
    "STOOQ_SYMBOL_MAP",
    "SUPPORTED_SYMBOLS",
    "YAHOO_CHART_ROOT",
    "YahooChartProvider",
    "probe_market_coverage",
    "probe_coverage",
    "probe_50_symbols",
    "assess_market_quality",
]
