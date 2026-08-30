"""Provider-neutral daily market data contracts.

The ingestion boundary intentionally uses immutable, standard-library values
so that neither a vendor SDK nor a dataframe library leaks into scoring.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class DailyBar:
    """One canonical daily OHLCV observation.

    ``date`` is the exchange session date.  Prices are Decimal values and
    volume is a non-negative integer.  ``adj_close`` may equal ``close`` when
    the provider does not publish adjusted prices; the adjustment fields make
    that distinction explicit for downstream consumers.
    """

    date: date
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    adj_close: Decimal | None = None
    provider: str = "unknown"
    provider_record_id: str | None = None
    available_at: datetime | None = None
    is_adjusted: bool = False
    adjustment_basis: str = "unadjusted"
    split_factor: Decimal | None = None
    provenance: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("symbol must be a non-empty uppercase value")
        if self.open <= 0 or self.high <= 0 or self.low <= 0 or self.close <= 0:
            raise ValueError("OHLC values must be positive")
        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")
        if self.adj_close is None:
            object.__setattr__(self, "adj_close", self.close)

    @property
    def ticker(self) -> str:
        """Compatibility spelling used by identity and scoring callers."""

        return self.symbol

    @property
    def adjusted(self) -> bool:
        return self.is_adjusted


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    """Operational status returned by a market provider."""

    provider: str
    available: bool
    lag: int | None = None
    quota_state: str = "unknown"
    checked_at: datetime | None = None
    message: str = ""
    cache_hits: int = 0
    cache_misses: int = 0

    @property
    def healthy(self) -> bool:
        return self.available and (self.lag is None or self.lag >= 0)

    @property
    def availability(self) -> bool:
        """ADR spelling for the provider's availability result."""

        return self.available


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Coverage and quarantine result for a market-universe probe."""

    requested_symbols: tuple[str, ...]
    covered_symbols: tuple[str, ...]
    missing_symbols: tuple[str, ...]
    stale_symbols: tuple[str, ...] = ()
    split_discontinuity_symbols: tuple[str, ...] = ()
    quarantined_symbols: tuple[str, ...] = ()
    as_of: date | None = None
    expected_sessions: int | None = None
    observed_rows: int = 0
    reasons: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def coverage_rate(self) -> float:
        return (
            len(self.covered_symbols) / len(self.requested_symbols)
            if self.requested_symbols
            else 0.0
        )

    @property
    def coverage(self) -> float:
        return self.coverage_rate

    @property
    def market_coverage_rate(self) -> float:
        return self.coverage_rate

    @property
    def stale(self) -> tuple[str, ...]:
        return self.stale_symbols

    @property
    def split_discontinuities(self) -> tuple[str, ...]:
        return self.split_discontinuity_symbols

    @property
    def is_acceptable(self) -> bool:
        return self.coverage_rate >= 0.90 and not self.quarantined_symbols

    @property
    def passed(self) -> bool:
        return self.is_acceptable


@runtime_checkable
class MarketDataProvider(Protocol):
    """Minimal provider port shared by CSV, Stooq, and future adapters."""

    name: str

    def get_daily_bars(
        self,
        symbol: str,
        *,
        start: date | None = None,
        end: date | None = None,
        as_of: date | None = None,
    ) -> Sequence[DailyBar]: ...

    def fetch_daily(
        self,
        symbol: str,
        *,
        start: date | None = None,
        end: date | None = None,
        as_of: date | None = None,
    ) -> Sequence[DailyBar]: ...

    def health(self) -> ProviderHealth: ...
