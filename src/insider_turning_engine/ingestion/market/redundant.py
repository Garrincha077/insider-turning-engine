"""Redundant EOD selection with deterministic cross-provider checks."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Protocol

import httpx

from .base import DailyBar, ProviderHealth


class EODSource(Protocol):
    name: str

    def fetch_daily(self, symbol: str) -> Sequence[DailyBar]: ...

    def close(self) -> None: ...


class RedundantEODProvider:
    """Use the first healthy source and reject material source disagreement."""

    name = "redundant-eod"

    def __init__(
        self,
        providers: Sequence[EODSource],
        *,
        adjusted_close_tolerance: Decimal = Decimal("0.05"),
    ) -> None:
        if len(providers) < 2:
            raise ValueError("redundant EOD provider requires at least two sources")
        if adjusted_close_tolerance <= 0 or adjusted_close_tolerance > Decimal("0.25"):
            raise ValueError("adjusted close tolerance must be in (0, 0.25]")
        self.providers = tuple(providers)
        self.adjusted_close_tolerance = adjusted_close_tolerance
        self.selected_provider: dict[str, str] = {}
        self.cross_validated_symbols: set[str] = set()
        self.failures: dict[str, dict[str, str]] = {}

    def fetch_daily(
        self,
        symbol: str,
        *,
        start: date | None = None,
        end: date | None = None,
        as_of: date | None = None,
    ) -> tuple[DailyBar, ...]:
        normalized = symbol.strip().upper()
        self.selected_provider.pop(normalized, None)
        self.cross_validated_symbols.discard(normalized)
        self.failures.pop(normalized, None)
        successes: list[tuple[str, tuple[DailyBar, ...]]] = []
        errors: dict[str, str] = {}
        for provider in self.providers:
            try:
                rows = tuple(
                    row
                    for row in provider.fetch_daily(normalized)
                    if (start is None or row.date >= start)
                    and (end is None or row.date <= end)
                    and (as_of is None or row.date <= as_of)
                )
                if not rows:
                    raise ValueError("provider returned no eligible daily bars")
                successes.append((provider.name, rows))
            except (OSError, RuntimeError, ValueError, httpx.HTTPError) as exc:
                errors[provider.name] = type(exc).__name__
        if not successes:
            self.failures[normalized] = errors
            raise RuntimeError(f"all EOD providers failed for {normalized}")
        if len(successes) > 1:
            self._cross_validate(normalized, successes)
            self.cross_validated_symbols.add(normalized)
        # Prefer the freshest history; configured source order breaks ties.
        selected_name, selected_rows = max(
            successes, key=lambda item: max(row.date for row in item[1])
        )
        self.selected_provider[normalized] = selected_name
        if errors:
            self.failures[normalized] = errors
        return selected_rows

    def get_daily_bars(
        self,
        symbol: str,
        *,
        start: date | None = None,
        end: date | None = None,
        as_of: date | None = None,
    ) -> tuple[DailyBar, ...]:
        return self.fetch_daily(symbol, start=start, end=end, as_of=as_of)

    def _cross_validate(
        self, symbol: str, successes: Sequence[tuple[str, tuple[DailyBar, ...]]]
    ) -> None:
        reference_name, reference_rows = successes[0]
        reference = {row.date: row for row in reference_rows}
        for provider_name, rows in successes[1:]:
            candidate = {row.date: row for row in rows}
            overlap = sorted(set(reference).intersection(candidate))
            if not overlap:
                raise RuntimeError(
                    f"EOD providers have no overlapping session for {symbol}: "
                    f"{reference_name}, {provider_name}"
                )
            session = overlap[-1]
            left = reference[session].adj_close
            right = candidate[session].adj_close
            if left is None or right is None or left <= 0 or right <= 0:
                raise RuntimeError(f"EOD adjusted close is invalid for {symbol}")
            difference = abs(left - right) / max(left, right)
            if difference > self.adjusted_close_tolerance:
                raise RuntimeError(
                    f"EOD adjusted close mismatch for {symbol} on {session.isoformat()}"
                )

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            available=bool(self.selected_provider),
            quota_state="ok" if not self.failures else "degraded",
            checked_at=datetime.now(UTC),
            message=(
                f"{len(self.cross_validated_symbols)} symbols cross-validated; "
                f"{len(self.failures)} symbols had provider failures"
            ),
        )

    def close(self) -> None:
        for provider in self.providers:
            provider.close()


__all__ = ["EODSource", "RedundantEODProvider"]
