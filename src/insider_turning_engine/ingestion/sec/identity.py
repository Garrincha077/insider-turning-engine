"""Official SEC company ticker/exchange identity source.

The SEC's ``company_tickers_exchange.json`` file is a *current* mapping.  It
is useful for resolving an issuer at the time the file was retrieved, but it
is not a historical security master and must not be used before that instant.
This adapter keeps that distinction explicit on every returned row.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from insider_turning_engine.domain.models import QuarantineRecord
from insider_turning_engine.normalization.identity import evaluate_security_universe

from .historical import (
    _SEC_PACER,
    MAX_RETRY_DELAY_SECONDS,
    RequestPacer,
    _bounded_response_body,
    _response_context,
    validate_sec_user_agent,
)

COMPANY_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
# Friendly names retained for callers that refer to this as a company ticker
# map rather than the SEC endpoint's file name.
SEC_COMPANY_TICKERS_EXCHANGE_URL = COMPANY_TICKERS_EXCHANGE_URL
SEC_COMPANY_TICKER_EXCHANGE_URL = COMPANY_TICKERS_EXCHANGE_URL
MAX_COMPANY_TICKERS_BYTES = 25 * 1024 * 1024
_SEC_IDENTITY_HOSTS = frozenset({"sec.gov", "www.sec.gov"})
_JSON_CONTENT_TYPES = frozenset({"application/json"})


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _now() -> datetime:
    return datetime.now(UTC)


def _hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _cik(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("CIK must be a numeric SEC identifier")
    text = str(value).strip()
    if not text.isdigit() or len(text) > 10:
        raise ValueError("CIK must contain at most ten digits")
    return text.zfill(10)


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True, slots=True)
class CompanyTickerIdentity:
    """One issuer identity observed in the SEC's current mapping."""

    cik: str
    name: str
    ticker: str
    exchange: str
    knowledge_at: datetime
    source: str = COMPANY_TICKERS_EXCHANGE_URL
    provenance: Mapping[str, object] = field(default_factory=dict)
    current_mapping: bool = True
    survivorship_caveat: bool = True

    @property
    def issuer_cik(self) -> str:
        return self.cik

    @property
    def cik_str(self) -> str:
        return self.cik

    @property
    def source_url(self) -> str:
        return self.source

    @property
    def usable_from(self) -> datetime:
        return self.knowledge_at

    @property
    def is_current_mapping(self) -> bool:
        return self.current_mapping

    def usable_at(self, as_of: datetime | date | str) -> bool:
        """Whether this current mapping may be used at ``as_of``."""

        if isinstance(as_of, datetime):
            point = _utc(as_of)
        elif isinstance(as_of, date):
            point = datetime(as_of.year, as_of.month, as_of.day, tzinfo=UTC)
        else:
            text = as_of.strip()
            point = _utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
        return point >= _utc(self.knowledge_at)

    # The normalization layer uses ``name``/``ticker`` but some consumers use
    # the explicit issuer vocabulary.  These aliases do not add inferred data.
    @property
    def issuer_name(self) -> str:
        return self.name

    @property
    def valid_from(self) -> datetime:
        """Current-map validity starts at retrieval knowledge time."""

        return self.knowledge_at


@dataclass(frozen=True, slots=True)
class CompanyTickerIdentityResult:
    """Rows and quality metadata from one fetch."""

    records: tuple[CompanyTickerIdentity, ...] = ()
    quarantines: tuple[QuarantineRecord, ...] = ()
    retrieved_at: datetime | None = None
    source_url: str = COMPANY_TICKERS_EXCHANGE_URL
    content_hash: str | None = None
    cache_hit: bool = False
    excluded_count: int = 0

    def __iter__(self) -> Iterator[CompanyTickerIdentity]:
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> CompanyTickerIdentity:
        return self.records[index]


def _field_indexes(fields: Sequence[object]) -> dict[str, int]:
    normalized = {str(value).strip().casefold(): index for index, value in enumerate(fields)}
    aliases = {
        "cik": ("cik", "cik_str", "cikstr"),
        "name": ("name", "company_name", "companyname"),
        "ticker": ("ticker", "symbol"),
        "exchange": ("exchange", "exchange_name", "exchangename"),
    }
    result: dict[str, int] = {}
    for required, names in aliases.items():
        for name in names:
            if name in normalized:
                result[required] = normalized[name]
                break
        if required not in result:
            raise ValueError(f"SEC identity fields missing {required!r}")
    return result


def _parse_row(row: object, indexes: Mapping[str, int]) -> tuple[str, str, str, str]:
    if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray)):
        raise ValueError("SEC identity row must be an array")
    try:
        cik = _cik(row[indexes["cik"]])
        name = _text(row[indexes["name"]], "name")
        ticker = _text(row[indexes["ticker"]], "ticker").upper()
        exchange = _text(row[indexes["exchange"]], "exchange")
    except (IndexError, KeyError) as exc:
        raise ValueError("SEC identity row has too few fields") from exc
    if len(ticker) > 15 or any(
        character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for character in ticker
    ):
        raise ValueError("SEC identity ticker is invalid")
    return cik, name, ticker, exchange


def parse_company_tickers_exchange(
    payload: bytes | str,
    *,
    retrieved_at: datetime | None = None,
    source_url: str = COMPANY_TICKERS_EXCHANGE_URL,
    content_hash: str | None = None,
) -> tuple[CompanyTickerIdentity, ...]:
    """Parse the official SEC JSON into deterministic identity rows.

    Parsing is strict: callers needing row-level quarantine can use
    :func:`parse_company_tickers_exchange_with_quarantine`.
    """

    try:
        decoded = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        document = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("SEC company ticker payload is not valid JSON") from exc
    if not isinstance(document, Mapping):
        raise ValueError("SEC company ticker payload must be an object")
    fields = document.get("fields")
    rows = document.get("data")
    if not isinstance(fields, Sequence) or isinstance(fields, (str, bytes, bytearray)):
        raise ValueError("SEC company ticker payload fields must be an array")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ValueError("SEC company ticker payload data must be an array")
    indexes = _field_indexes(fields)
    observed = _utc(retrieved_at or _now())
    digest = content_hash or (
        "sha256:" + _hash(payload.encode("utf-8") if isinstance(payload, str) else payload)
    )
    output: list[CompanyTickerIdentity] = []
    for row in rows:
        cik, name, ticker, exchange = _parse_row(row, indexes)
        output.append(
            CompanyTickerIdentity(
                cik=cik,
                name=name,
                ticker=ticker,
                exchange=exchange,
                knowledge_at=observed,
                source=source_url,
                provenance={
                    "source": source_url,
                    "content_hash": digest,
                    "mapping_status": "current",
                    "current_mapping": True,
                    "survivorship_caveat": True,
                    "usable_only_at_or_after": observed.isoformat(),
                },
            )
        )
    return tuple(sorted(output, key=lambda item: (item.cik, item.ticker, item.exchange, item.name)))


def parse_company_tickers_exchange_with_quarantine(
    payload: bytes | str,
    *,
    retrieved_at: datetime | None = None,
    source_url: str = COMPANY_TICKERS_EXCHANGE_URL,
    content_hash: str | None = None,
) -> tuple[tuple[CompanyTickerIdentity, ...], tuple[QuarantineRecord, ...]]:
    """Parse valid rows while quarantining malformed rows."""

    decoded = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    try:
        document = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("SEC company ticker payload is not valid JSON") from exc
    if not isinstance(document, Mapping):
        raise ValueError("SEC company ticker payload must be an object")
    fields = document.get("fields")
    rows = document.get("data")
    if not isinstance(fields, Sequence) or isinstance(fields, (str, bytes, bytearray)):
        raise ValueError("SEC company ticker payload fields must be an array")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ValueError("SEC company ticker payload data must be an array")
    indexes = _field_indexes(fields)
    observed = _utc(retrieved_at or _now())
    digest = content_hash or ("sha256:" + _hash(decoded.encode("utf-8")))
    valid: list[CompanyTickerIdentity] = []
    bad: list[QuarantineRecord] = []
    for index, row in enumerate(rows):
        try:
            cik, name, ticker, exchange = _parse_row(row, indexes)
            valid.append(
                CompanyTickerIdentity(
                    cik=cik,
                    name=name,
                    ticker=ticker,
                    exchange=exchange,
                    knowledge_at=observed,
                    source=source_url,
                    provenance={
                        "source": source_url,
                        "content_hash": digest,
                        "mapping_status": "current",
                        "current_mapping": True,
                        "survivorship_caveat": True,
                        "usable_only_at_or_after": observed.isoformat(),
                    },
                )
            )
        except ValueError as exc:
            bad.append(
                QuarantineRecord(
                    reason_code="SEC_COMPANY_TICKER_ROW_INVALID",
                    message=str(exc),
                    source_row_key=str(index),
                    locator=source_url,
                )
            )
    ordered = tuple(
        sorted(valid, key=lambda item: (item.cik, item.ticker, item.exchange, item.name))
    )
    return ordered, tuple(bad)


def _cache_candidates(cache_dir: Path, source_url: str) -> tuple[Path, Path, dict[str, Any]] | None:
    root = cache_dir / "company-tickers"
    if not root.is_dir():
        return None
    for manifest_path in sorted(root.glob("*.manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict) or manifest.get("url") != source_url:
                continue
            digest = str(manifest.get("sha256", ""))
            payload_path = root / f"{digest}.json"
            payload = payload_path.read_bytes()
            if digest != _hash(payload) or manifest.get("byteLength") != len(payload):
                continue
            retrieved = manifest.get("retrievedAt")
            if not isinstance(retrieved, str):
                continue
            return payload_path, manifest_path, manifest
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return None


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class SECCompanyTickerSource:
    """Fetch and normalize the official SEC current ticker/exchange map."""

    name = "sec-company-tickers-exchange"

    def __init__(
        self,
        user_agent: str,
        *,
        client: Any | None = None,
        cache_dir: str | Path | None = None,
        url: str = COMPANY_TICKERS_EXCHANGE_URL,
        pacer: RequestPacer | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
        max_bytes: int = MAX_COMPANY_TICKERS_BYTES,
        max_response_bytes: int | None = None,
        clock: Callable[[], datetime] = _now,
        filter_universe: bool = True,
    ) -> None:
        self.user_agent = validate_sec_user_agent(user_agent)
        self.url = url
        self._validate_url()
        if max_attempts < 1 or (max_response_bytes or max_bytes) < 1:
            raise ValueError("SEC identity source limits must be positive")
        self.client = client
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.pacer = pacer or _SEC_PACER
        self.sleeper = sleeper
        self.max_attempts = max_attempts
        self.max_bytes = max_response_bytes if max_response_bytes is not None else max_bytes
        self.clock = clock
        self.filter_universe = filter_universe

    def _validate_url(self) -> None:
        parsed = urlparse(self.url)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("SEC identity URL contains an invalid port") from exc
        if (
            parsed.scheme.casefold() != "https"
            or (parsed.hostname or "").casefold() not in _SEC_IDENTITY_HOSTS
            or port not in {None, 443}
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("SEC identity URL host is outside the allowlist")

    def _request(self) -> tuple[bytes, bool]:
        self._validate_url()
        client = self.client or httpx.Client(timeout=60.0, follow_redirects=False)
        self.client = client
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            self.pacer.wait()
            try:
                headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
                with _response_context(client, self.url, headers) as response:
                    history = getattr(response, "history", ())
                    effective = str(getattr(response, "url", self.url) or self.url)
                    if (
                        history
                        or effective != self.url
                        or 300 <= int(getattr(response, "status_code", 200)) <= 399
                    ):
                        raise ValueError("SEC redirects are not accepted")
                    parsed_effective = urlparse(effective)
                    if (
                        parsed_effective.scheme.casefold() != "https"
                        or (parsed_effective.hostname or "").casefold() not in _SEC_IDENTITY_HOSTS
                        or parsed_effective.port not in {None, 443}
                        or parsed_effective.username is not None
                        or parsed_effective.password is not None
                    ):
                        raise ValueError("SEC response host is outside the allowlist")
                    status = int(getattr(response, "status_code", 200))
                    headers = getattr(response, "headers", {})
                    content_type = next(
                        (
                            str(value)
                            for key, value in headers.items()
                            if str(key).casefold() == "content-type"
                        ),
                        "",
                    )
                    if (
                        200 <= status <= 299
                        and content_type.split(";", 1)[0].strip().casefold()
                        not in _JSON_CONTENT_TYPES
                    ):
                        raise ValueError("SEC response has disallowed Content-Type")
                    if status == 429 or 500 <= status <= 599:
                        if attempt + 1 < self.max_attempts:
                            delay = min(MAX_RETRY_DELAY_SECONDS, float(2**attempt))
                            self.sleeper(delay)
                            continue
                        raise RuntimeError(f"SEC identity request returned HTTP {status}")
                    if status >= 400:
                        raise RuntimeError(f"SEC identity request returned HTTP {status}")
                    return _bounded_response_body(response, self.max_bytes), False
            except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    self.sleeper(min(MAX_RETRY_DELAY_SECONDS, float(2**attempt)))
                    continue
        raise RuntimeError(f"SEC identity request failed: {last_error}") from last_error

    def _load_cache(self) -> tuple[bytes, datetime] | None:
        if self.cache_dir is None:
            return None
        candidate = _cache_candidates(self.cache_dir, self.url)
        if candidate is None:
            return None
        payload_path, _manifest_path, manifest = candidate
        try:
            retrieved = datetime.fromisoformat(str(manifest["retrievedAt"]).replace("Z", "+00:00"))
            payload = payload_path.read_bytes()
            if len(payload) > self.max_bytes:
                return None
            return payload, _utc(retrieved)
        except (OSError, TypeError, ValueError, KeyError):
            return None

    def _save_cache(self, payload: bytes, retrieved_at: datetime) -> None:
        if self.cache_dir is None:
            return
        root = self.cache_dir / "company-tickers"
        root.mkdir(parents=True, exist_ok=True)
        digest = _hash(payload)
        _atomic_write(root / f"{digest}.json", payload)
        manifest = {
            "schemaVersion": "1.0.0",
            "url": self.url,
            "sha256": digest,
            "checksum": "sha256:" + digest,
            "byteLength": len(payload),
            "retrievedAt": _utc(retrieved_at).isoformat(),
        }
        manifest_payload = (
            json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        _atomic_write(root / f"{digest}.manifest.json", manifest_payload)

    def fetch(
        self, *, as_of: datetime | date | str | None = None
    ) -> CompanyTickerIdentityResult:
        cached = self._load_cache()
        if cached is not None:
            payload, retrieved_at = cached
            digest = "sha256:" + _hash(payload)
            cache_hit = True
        else:
            payload, _ = self._request()
            retrieved_at = _utc(self.clock())
            self._save_cache(payload, retrieved_at)
            digest = "sha256:" + _hash(payload)
            cache_hit = False
        records, quarantines = parse_company_tickers_exchange_with_quarantine(
            payload, retrieved_at=retrieved_at, source_url=self.url, content_hash=digest
        )
        if self.filter_universe:
            included: list[CompanyTickerIdentity] = []
            excluded = 0
            for record in records:
                decision = evaluate_security_universe(record, as_of=retrieved_at)
                if decision.include:
                    included.append(record)
                else:
                    excluded += 1
            records = tuple(included)
        else:
            excluded = 0
        result = CompanyTickerIdentityResult(
            records=records,
            quarantines=quarantines,
            retrieved_at=retrieved_at,
            source_url=self.url,
            content_hash=digest,
            cache_hit=cache_hit,
            excluded_count=excluded,
        )
        if as_of is not None:
            records = tuple(record for record in result.records if record.usable_at(as_of))
            result = CompanyTickerIdentityResult(
                records=records,
                quarantines=result.quarantines,
                retrieved_at=result.retrieved_at,
                source_url=result.source_url,
                content_hash=result.content_hash,
                cache_hit=result.cache_hit,
                excluded_count=result.excluded_count,
            )
        return result

    def iter_records(
        self, *, as_of: datetime | date | str | None = None
    ) -> Iterable[CompanyTickerIdentity]:
        yield from self.fetch(as_of=as_of).records

    fetch_current = fetch

    def close(self) -> None:
        if self.client is not None:
            close = getattr(self.client, "close", None)
            if callable(close):
                close()


# API spellings used by downstream integrations.
SECCompanyTickerSource = SECCompanyTickerSource
SECCompanyTickerExchangeSource = SECCompanyTickerSource
CompanyTickerExchangeSource = SECCompanyTickerSource
SECCompanyIdentitySource = SECCompanyTickerSource
SECIdentitySource = SECCompanyTickerSource
SECCurrentIdentitySource = SECCompanyTickerSource

__all__ = [
    "COMPANY_TICKERS_EXCHANGE_URL",
    "SEC_COMPANY_TICKERS_EXCHANGE_URL",
    "SEC_COMPANY_TICKER_EXCHANGE_URL",
    "MAX_COMPANY_TICKERS_BYTES",
    "CompanyTickerIdentity",
    "CompanyTickerIdentityResult",
    "SECCompanyTickerSource",
    "SECCompanyTickerExchangeSource",
    "CompanyTickerExchangeSource",
    "SECCompanyIdentitySource",
    "SECIdentitySource",
    "SECCurrentIdentitySource",
    "parse_company_tickers_exchange",
    "parse_company_tickers_exchange_with_quarantine",
]
