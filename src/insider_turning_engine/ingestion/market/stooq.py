"""Anonymous Stooq daily CSV adapter."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import httpx

from insider_turning_engine.domain.time import us_equity_session_close

from .base import DailyBar, ProviderHealth

SECTOR_ETFS = ("XLE", "XLK", "XLV", "XLRE", "XLU", "XLC", "XLB", "XLP", "XLY", "XLI", "XLF")
SUPPORTED_SYMBOLS = ("SPY", *SECTOR_ETFS)
STOOQ_SYMBOL_MAP = {symbol: f"{symbol.lower()}.us" for symbol in SUPPORTED_SYMBOLS}
MAX_SHARD_COUNT = 3


@dataclass(frozen=True, slots=True)
class MarketFetchBatch:
    """One deterministic market shard with per-symbol failure isolation."""

    bars: dict[str, tuple[DailyBar, ...]]
    failures: dict[str, str]

    @property
    def requested(self) -> int:
        return len(self.bars) + len(self.failures)

    @property
    def succeeded(self) -> int:
        return len(self.bars)


class StooqMarketDataProvider:
    """Fetch daily bars from Stooq with bounded retries and in-memory cache."""

    name = "stooq"
    base_url = "https://stooq.com/q/d/l/"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        max_attempts: int = 3,
        timeout: float = 10.0,
        cache_ttl_seconds: float = 300.0,
        cache_dir: str | Path | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=False)
        self.max_attempts = max(1, max_attempts)
        self.cache_ttl_seconds = max(0.0, cache_ttl_seconds)
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._sleeper = sleeper
        self._cache: dict[str, tuple[float, tuple[DailyBar, ...]]] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        self._last_health = ProviderHealth(
            provider=self.name,
            available=True,
            quota_state="unknown",
        )

    @staticmethod
    def map_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if normalized.endswith(".US"):
            normalized = normalized[:-3]
        if not normalized or any(
            char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for char in normalized
        ):
            raise ValueError(f"invalid market symbol: {symbol!r}")
        return f"{normalized.lower()}.us"

    def _url(self, symbol: str) -> str:
        return f"{self.base_url}?s={self.map_symbol(symbol)}&i=d"

    def fetch_daily(
        self,
        symbol: str,
        *,
        start: date | None = None,
        end: date | None = None,
        as_of: date | None = None,
    ) -> tuple[DailyBar, ...]:
        return self.get_daily_bars(symbol, start=start, end=end, as_of=as_of)

    def get_daily_bars(
        self,
        symbol: str,
        *,
        start: date | None = None,
        end: date | None = None,
        as_of: date | None = None,
    ) -> tuple[DailyBar, ...]:
        key = symbol.strip().upper()
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and now - cached[0] <= self.cache_ttl_seconds:
            self._cache_hits += 1
            bars = cached[1]
        else:
            self._cache_misses += 1
            disk_bars = self._load_disk_cache(key)
            bars = disk_bars if disk_bars is not None else self._fetch(key)
            self._cache[key] = (now, bars)
        cutoff = as_of or date.today()
        return tuple(
            bar
            for bar in bars
            if bar.date <= cutoff
            and (start is None or bar.date >= start)
            and (end is None or bar.date <= end)
        )

    def _fetch(self, symbol: str) -> tuple[DailyBar, ...]:
        response: httpx.Response | None = None
        error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                request_url = self._url(symbol)
                response = self.client.get(request_url, headers={"Accept": "text/csv"})
                response_host = urlparse(str(response.url)).hostname
                if response.history or response.status_code in {301, 302, 303, 307, 308}:
                    raise ValueError("Stooq redirects are not accepted")
                if response_host not in {"stooq.com", "www.stooq.com"}:
                    raise ValueError("Stooq response host is outside the allow-list")
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise httpx.HTTPStatusError(
                        "retryable Stooq response",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                payload = response.text
                locator = response.url.__str__()
                bars = self._parse(payload, symbol, locator)
                self._write_disk_cache(symbol, payload, locator)
                self._last_health = ProviderHealth(
                    provider=self.name,
                    available=True,
                    quota_state="ok",
                    checked_at=datetime.now(UTC),
                    cache_hits=self._cache_hits,
                    cache_misses=self._cache_misses,
                )
                return bars
            except (httpx.HTTPError, ValueError) as exc:
                error = exc
                if (
                    isinstance(exc, httpx.HTTPStatusError)
                    and exc.response is not None
                    and exc.response.status_code == 404
                ):
                    break
                if attempt + 1 < self.max_attempts:
                    delay = min(4.0, 0.25 * (2**attempt))
                    self._sleeper(delay)
        self._last_health = ProviderHealth(
            provider=self.name,
            available=False,
            quota_state="error",
            checked_at=datetime.now(UTC),
            message=str(error or "empty response"),
            cache_hits=self._cache_hits,
            cache_misses=self._cache_misses,
        )
        raise RuntimeError(
            f"Stooq market fetch failed for {symbol}: {error or 'empty response'}"
        ) from error

    def _disk_paths(self, symbol: str) -> tuple[Path, Path] | None:
        if self.cache_dir is None:
            return None
        safe = symbol.lower().replace(".", "_")
        root = self.cache_dir / "stooq"
        return root / f"{safe}.csv", root / f"{safe}.manifest.json"

    def _load_disk_cache(self, symbol: str) -> tuple[DailyBar, ...] | None:
        paths = self._disk_paths(symbol)
        if paths is None:
            return None
        payload_path, manifest_path = paths
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload = payload_path.read_bytes()
            age = max(0.0, time.time() - payload_path.stat().st_mtime)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        if (
            not isinstance(manifest, dict)
            or manifest.get("schemaVersion") != "1.0.0"
            or manifest.get("symbol") != symbol
            or manifest.get("sha256") != digest
            or manifest.get("byteLength") != len(payload)
            or manifest.get("sourceUrl") != self._url(symbol)
            or age > self.cache_ttl_seconds
        ):
            return None
        try:
            bars = self._parse(payload.decode("utf-8"), symbol, str(manifest["sourceUrl"]))
        except (UnicodeError, ValueError):
            return None
        self._cache_hits += 1
        return bars

    def _write_disk_cache(self, symbol: str, payload: str, locator: str) -> None:
        paths = self._disk_paths(symbol)
        if paths is None:
            return
        payload_path, manifest_path = paths
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        content = payload.encode("utf-8")
        manifest = {
            "schemaVersion": "1.0.0",
            "symbol": symbol,
            "sourceUrl": locator,
            "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            "byteLength": len(content),
            "fetchedAt": datetime.now(UTC).isoformat(),
        }
        manifest_content = (
            json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()

        # Use unique same-directory temporary files so concurrent refreshes do
        # not clobber each other's ``.tmp`` file.  The checksum in the
        # manifest makes a crash between the two replaces fail closed: a
        # mixed data/metadata pair is ignored on the next read.
        for path, value in ((payload_path, content), (manifest_path, manifest_content)):
            temporary_name: str | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
                ) as stream:
                    temporary_name = stream.name
                    stream.write(value)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_name, path)
                temporary_name = None
            finally:
                if temporary_name is not None:
                    try:
                        os.unlink(temporary_name)
                    except FileNotFoundError:
                        pass

    def fetch_shard(
        self,
        symbols: list[str] | tuple[str, ...],
        *,
        shard_index: int = 0,
        shard_count: int = 1,
        start: date | None = None,
        end: date | None = None,
        as_of: date | None = None,
    ) -> MarketFetchBatch:
        """Fetch a stable lexical shard while retaining individual failures."""

        if (
            shard_count < 1
            or shard_count > MAX_SHARD_COUNT
            or not 0 <= shard_index < shard_count
        ):
            raise ValueError(
                "invalid shard_index/shard_count; "
                f"shard_count must be between 1 and {MAX_SHARD_COUNT}"
            )
        selected = tuple(
            symbol
            for index, symbol in enumerate(sorted({item.strip().upper() for item in symbols}))
            if index % shard_count == shard_index
        )
        bars: dict[str, tuple[DailyBar, ...]] = {}
        failures: dict[str, str] = {}
        for symbol in selected:
            try:
                bars[symbol] = self.get_daily_bars(
                    symbol,
                    start=start,
                    end=end,
                    as_of=as_of,
                )
            except (RuntimeError, ValueError) as exc:
                failures[symbol] = str(exc)
        return MarketFetchBatch(bars, failures)

    @staticmethod
    def _parse(payload: str, symbol: str, locator: str) -> tuple[DailyBar, ...]:
        reader = csv.DictReader(io.StringIO(payload))
        required = {"date", "open", "high", "low", "close", "volume"}
        fields = {field.strip().lower() for field in (reader.fieldnames or ())}
        if not required.issubset(fields):
            raise ValueError("Stooq response missing daily OHLCV columns")
        parsed: list[DailyBar] = []
        seen_dates: set[date] = set()
        for row in reader:
            normalized = {
                str(key).strip().lower(): value for key, value in row.items() if key is not None
            }
            try:
                day = date.fromisoformat(str(normalized["date"]).strip())
                if day in seen_dates:
                    raise ValueError(f"duplicate Stooq daily row for {symbol} on {day}")
                seen_dates.add(day)
                volume = int(Decimal(str(normalized["volume"]).strip()))
                open_price = Decimal(str(normalized["open"]).strip())
                high = Decimal(str(normalized["high"]).strip())
                low = Decimal(str(normalized["low"]).strip())
                close = Decimal(str(normalized["close"]).strip())
                parsed.append(
                    DailyBar(
                        date=day,
                        symbol=symbol,
                        open=open_price,
                        high=high,
                        low=low,
                        close=close,
                        adj_close=close,
                        volume=volume,
                        provider="stooq",
                        provider_record_id=f"stooq:{symbol}:{day.isoformat()}",
                        available_at=us_equity_session_close(day),
                        is_adjusted=False,
                        adjustment_basis="unadjusted",
                        provenance={"source": "stooq", "locator": locator},
                    )
                )
            except (KeyError, ValueError, ArithmeticError) as exc:
                raise ValueError(f"invalid Stooq daily row: {exc}") from exc
        return tuple(sorted(parsed, key=lambda bar: bar.date))

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            available=self._last_health.available,
            lag=self._last_health.lag,
            quota_state=self._last_health.quota_state,
            checked_at=self._last_health.checked_at,
            message=self._last_health.message,
            cache_hits=self._cache_hits,
            cache_misses=self._cache_misses,
        )

    def close(self) -> None:
        self.client.close()


StooqProvider = StooqMarketDataProvider

__all__ = ["MAX_SHARD_COUNT", "MarketFetchBatch", "StooqMarketDataProvider", "StooqProvider"]
