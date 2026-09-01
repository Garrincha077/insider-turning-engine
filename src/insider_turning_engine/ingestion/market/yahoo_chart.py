"""Keyless Yahoo chart fallback for the live experimental dashboard.

Yahoo is not the locked v1 research provider. Every bar is therefore stamped
as experimental so it cannot be mistaken for Stooq/CSV validation input.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from insider_turning_engine.domain.time import us_equity_session_close

from .base import DailyBar

YAHOO_CHART_ROOT = "https://query1.finance.yahoo.com/v8/finance/chart"


class YahooChartProvider:
    """Fetch two years of split/dividend-adjusted daily OHLCV bars."""

    name = "yahoo-chart-experimental"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        cache_dir: str | Path | None = None,
        max_bytes: int = 5 * 1024 * 1024,
    ) -> None:
        self.client = client or httpx.Client(timeout=45.0, follow_redirects=False)
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.max_bytes = max_bytes

    @staticmethod
    def _symbol(value: str) -> tuple[str, str]:
        symbol = value.strip().upper()
        if not symbol or any(
            char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for char in symbol
        ):
            raise ValueError(f"invalid Yahoo chart symbol: {value!r}")
        return symbol, symbol.replace(".", "-")

    def _url(self, symbol: str) -> str:
        _, yahoo_symbol = self._symbol(symbol)
        return (
            f"{YAHOO_CHART_ROOT}/{quote(yahoo_symbol, safe='-')}"
            "?range=2y&interval=1d&events=history"
        )

    def _cache_paths(self, symbol: str) -> tuple[Path, Path] | None:
        if self.cache_dir is None:
            return None
        safe = symbol.lower().replace(".", "_")
        root = self.cache_dir / "yahoo-chart"
        return root / f"{safe}.json", root / f"{safe}.manifest.json"

    def _read_cache(self, symbol: str) -> bytes | None:
        paths = self._cache_paths(symbol)
        if paths is None:
            return None
        payload_path, manifest_path = paths
        try:
            payload = payload_path.read_bytes()
            manifest = json.loads(manifest_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        if (
            not isinstance(manifest, dict)
            or manifest.get("schemaVersion") != "1.0.0"
            or manifest.get("symbol") != symbol
            or manifest.get("sourceUrl") != self._url(symbol)
            or manifest.get("sha256") != digest
            or manifest.get("byteLength") != len(payload)
        ):
            return None
        return payload

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_name = stream.name
                stream.write(content)
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

    def _write_cache(self, symbol: str, payload: bytes, source_url: str) -> None:
        paths = self._cache_paths(symbol)
        if paths is None:
            return
        payload_path, manifest_path = paths
        manifest = {
            "schemaVersion": "1.0.0",
            "symbol": symbol,
            "sourceUrl": source_url,
            "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
            "byteLength": len(payload),
            "fetchedAt": datetime.now(UTC).isoformat(),
        }
        self._atomic_write(payload_path, payload)
        self._atomic_write(
            manifest_path,
            (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        )

    def fetch_daily(self, symbol: str) -> tuple[DailyBar, ...]:
        normalized, _ = self._symbol(symbol)
        source_url = self._url(normalized)
        payload = self._read_cache(normalized)
        if payload is None:
            response = self.client.get(
                source_url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "InsiderTurningEngine/1.0",
                },
            )
            host = (urlparse(str(response.url)).hostname or "").lower()
            if response.history or response.is_redirect or host != "query1.finance.yahoo.com":
                raise ValueError("Yahoo chart redirect or response host is not accepted")
            response.raise_for_status()
            payload = response.content
            if len(payload) > self.max_bytes:
                raise ValueError("Yahoo chart response exceeds the configured size limit")
            self._write_cache(normalized, payload, source_url)
        return self._parse(payload, normalized, source_url)

    @staticmethod
    def _parse(payload: bytes, symbol: str, source_url: str) -> tuple[DailyBar, ...]:
        try:
            document = json.loads(payload)
            chart = document["chart"]
            if chart.get("error") is not None:
                raise ValueError(f"Yahoo chart error: {chart['error']}")
            result = chart["result"][0]
            timestamps = result["timestamp"]
            quote_rows = result["indicators"]["quote"][0]
            adjusted = (
                result["indicators"].get("adjclose", [{}])[0].get("adjclose", quote_rows["close"])
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Yahoo chart response has an invalid schema") from exc
        bars: list[DailyBar] = []
        for index, raw_timestamp in enumerate(timestamps):
            try:
                raw_values = [
                    quote_rows[name][index] for name in ("open", "high", "low", "close", "volume")
                ]
                if any(value is None for value in raw_values):
                    continue
                close = Decimal(str(quote_rows["close"][index]))
                adj_close = Decimal(
                    str(
                        adjusted[index]
                        if index < len(adjusted) and adjusted[index] is not None
                        else close
                    )
                )
                factor = adj_close / close
                day = datetime.fromtimestamp(int(raw_timestamp), UTC).date()
                bars.append(
                    DailyBar(
                        date=day,
                        symbol=symbol,
                        open=Decimal(str(quote_rows["open"][index])) * factor,
                        high=Decimal(str(quote_rows["high"][index])) * factor,
                        low=Decimal(str(quote_rows["low"][index])) * factor,
                        close=close * factor,
                        adj_close=adj_close,
                        volume=int(quote_rows["volume"][index]),
                        provider="yahoo-chart-experimental",
                        provider_record_id=f"yahoo-chart:{symbol}:{day.isoformat()}",
                        available_at=us_equity_session_close(day),
                        is_adjusted=True,
                        adjustment_basis="adjclose-ratio-applied-to-ohlc",
                        provenance={
                            "source": "yahoo-chart-experimental",
                            "locator": source_url,
                        },
                    )
                )
            except (ArithmeticError, IndexError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid Yahoo chart row for {symbol}: {exc}") from exc
        if not bars:
            raise ValueError(f"Yahoo chart returned no usable rows for {symbol}")
        return tuple(sorted(bars, key=lambda item: item.date))

    def close(self) -> None:
        self.client.close()


__all__ = ["YAHOO_CHART_ROOT", "YahooChartProvider"]
