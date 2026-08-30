"""Deterministic canonical CSV market-data provider."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TextIO

from .base import DailyBar, ProviderHealth

_REQUIRED = ("date", "ticker", "open", "high", "low", "close", "volume")
_OPTIONAL = ("adj_close", "adjusted", "is_adjusted", "adjustment_basis", "split_factor")


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"invalid market date: {value!r}") from exc


def _decimal(value: str, field: str) -> Decimal:
    try:
        result = Decimal(value.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"invalid {field}: {value!r}") from exc
    if not result.is_finite():
        raise ValueError(f"invalid {field}: {value!r}")
    return result


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


class CsvMarketDataProvider:
    """Load and serve a complete canonical multi-symbol daily CSV.

    The file is parsed once at construction, validated strictly, and held in
    memory.  This makes repeated point-in-time slices deterministic and keeps
    tests independent of network services.
    """

    name = "csv"

    @classmethod
    def from_csv(
        cls,
        source: str | Path | TextIO,
        *,
        as_of_date: date | None = None,
        provider: str = "csv",
    ) -> CsvMarketDataProvider:
        return cls(source, as_of_date=as_of_date, provider=provider)

    def __init__(
        self,
        source: str | Path | TextIO | Iterable[Mapping[str, object]],
        *,
        as_of_date: date | None = None,
        provider: str = "csv",
    ) -> None:
        self.provider = provider
        self._as_of_date = as_of_date or date.today()
        rows = self._read_rows(source)
        self._bars = self._parse(rows)
        grouped: dict[str, list[DailyBar]] = {}
        for bar in self._bars:
            grouped.setdefault(bar.symbol, []).append(bar)
        self._by_symbol = {key: tuple(value) for key, value in grouped.items()}

    @staticmethod
    def _read_rows(
        source: str | Path | TextIO | Iterable[Mapping[str, object]],
    ) -> list[Mapping[str, object]] | TextIO:
        if isinstance(source, str) and ("\n" in source or "\r" in source):
            return io.StringIO(source)
        if isinstance(source, (str, Path)):
            return io.StringIO(Path(source).read_text(encoding="utf-8"))
        if hasattr(source, "read"):
            return source  # type: ignore[return-value]
        return list(source)

    def _parse(self, rows: list[Mapping[str, object]] | TextIO) -> tuple[DailyBar, ...]:
        if hasattr(rows, "read"):
            reader = csv.DictReader(rows)  # type: ignore[arg-type]
            fieldnames = tuple((name or "").strip().lower() for name in (reader.fieldnames or ()))
            if "ticker" not in fieldnames and "symbol" in fieldnames:
                fieldnames = tuple("ticker" if name == "symbol" else name for name in fieldnames)
            if any(name not in fieldnames for name in _REQUIRED):
                raise ValueError(f"market CSV missing required columns: {_REQUIRED}")
            records: Iterable[Mapping[str, object]] = (
                {
                    str(key or "").strip().lower(): value
                    for key, value in row.items()
                    if key is not None
                }
                for row in reader
            )
        else:
            records = rows
        seen: set[tuple[str, date]] = set()
        parsed: list[DailyBar] = []
        for number, raw in enumerate(records, start=2):
            row = {str(key).strip().lower(): value for key, value in raw.items()}
            if "ticker" not in row and "symbol" in row:
                row["ticker"] = row["symbol"]
            try:
                symbol = str(row["ticker"]).strip().upper()
                if not symbol:
                    raise ValueError("empty ticker")
                day = _parse_date(str(row["date"]))
                if day > self._as_of_date:
                    raise ValueError("future market row")
                key = (symbol, day)
                if key in seen:
                    raise ValueError(f"duplicate market row for {symbol} on {day}")
                seen.add(key)
                volume_text = str(row["volume"]).strip()
                volume_decimal = _decimal(volume_text, "volume")
                if volume_decimal < 0 or volume_decimal != volume_decimal.to_integral_value():
                    raise ValueError("invalid volume")
                kwargs = {
                    "date": day,
                    "symbol": symbol,
                    "open": _decimal(str(row["open"]), "open"),
                    "high": _decimal(str(row["high"]), "high"),
                    "low": _decimal(str(row["low"]), "low"),
                    "close": _decimal(str(row["close"]), "close"),
                    "volume": int(volume_decimal),
                    "adj_close": (
                        _decimal(str(row["adj_close"]), "adj_close")
                        if row.get("adj_close") not in (None, "")
                        else None
                    ),
                    "provider": self.provider,
                    "provider_record_id": f"{self.provider}:{symbol}:{day.isoformat()}",
                    # A daily close is usable only after that session closes.
                    # The conservative UTC end-of-day pin is reproducible and
                    # keeps historical features from seeing a future session.
                    "available_at": datetime.combine(day, time.max, tzinfo=UTC),
                    "is_adjusted": _bool(str(row.get("is_adjusted", row.get("adjusted", "false")))),
                    "adjustment_basis": str(
                        row.get("adjustment_basis", "unadjusted") or "unadjusted"
                    ),
                    "split_factor": (
                        _decimal(str(row["split_factor"]), "split_factor")
                        if row.get("split_factor") not in (None, "")
                        else None
                    ),
                    "provenance": {"source": self.provider, "row": number},
                }
                parsed.append(DailyBar(**kwargs))  # type: ignore[arg-type]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid market CSV row {number}: {exc}") from exc
        return tuple(sorted(parsed, key=lambda bar: (bar.symbol, bar.date)))

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_symbol))

    @property
    def bars(self) -> tuple[DailyBar, ...]:
        return self._bars

    def get_daily_bars(
        self,
        symbol: str,
        *,
        start: date | None = None,
        end: date | None = None,
        as_of: date | None = None,
    ) -> tuple[DailyBar, ...]:
        symbol = symbol.strip().upper()
        cutoff = as_of or self._as_of_date
        return tuple(
            bar
            for bar in self._by_symbol.get(symbol, ())
            if bar.date <= cutoff
            and (start is None or bar.date >= start)
            and (end is None or bar.date <= end)
        )

    def bars_as_of(self, symbol: str, as_of: date) -> tuple[DailyBar, ...]:
        return self.get_daily_bars(symbol, as_of=as_of)

    def fetch_daily(
        self,
        symbol: str,
        *,
        start: date | None = None,
        end: date | None = None,
        as_of: date | None = None,
    ) -> tuple[DailyBar, ...]:
        return self.get_daily_bars(symbol, start=start, end=end, as_of=as_of)

    def get_weekly_bars(self, symbol: str, *, as_of: date | None = None) -> tuple[DailyBar, ...]:
        """Return Monday-anchored ISO-week OHLCV bars for aggregation callers."""

        grouped: dict[tuple[int, int], list[DailyBar]] = {}
        for bar in self.get_daily_bars(symbol, as_of=as_of):
            iso = bar.date.isocalendar()
            grouped.setdefault((iso.year, iso.week), []).append(bar)
        weekly: list[DailyBar] = []
        for (_year, _week), group in sorted(grouped.items()):
            ordered = sorted(group, key=lambda item: item.date)
            weekly.append(
                DailyBar(
                    date=ordered[-1].date,
                    symbol=ordered[0].symbol,
                    open=ordered[0].open,
                    high=max(item.high for item in ordered),
                    low=min(item.low for item in ordered),
                    close=ordered[-1].close,
                    adj_close=ordered[-1].adj_close,
                    volume=sum(item.volume for item in ordered),
                    provider=self.provider,
                    provider_record_id=(
                        f"{self.provider}:{ordered[0].symbol}:{ordered[-1].date}:W"
                    ),
                    is_adjusted=all(item.is_adjusted for item in ordered),
                    adjustment_basis=ordered[-1].adjustment_basis,
                    provenance={"source": self.provider, "aggregation": "iso_week"},
                )
            )
        return tuple(weekly)

    def health(self) -> ProviderHealth:
        latest = max((bar.date for bar in self._bars), default=None)
        lag = (self._as_of_date - latest).days if latest else None
        return ProviderHealth(
            provider=self.provider,
            available=bool(self._bars),
            lag=lag,
            quota_state="not_applicable",
            checked_at=datetime.now(UTC),
        )


CsvProvider = CsvMarketDataProvider
