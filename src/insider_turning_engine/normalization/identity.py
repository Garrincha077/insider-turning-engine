"""Deterministic issuer, ticker, security-universe, and sector identity helpers.

The SEC CIK is the legal issuer key in the engine.  Tickers, exchanges, and
security classifications are attributes that may change over time and must
therefore be resolved at a point in time.  This module deliberately works on
plain mappings, dataclass/Pydantic objects, and dataframe-like inputs so that
the normalization boundary does not depend on a provider SDK or a database.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from insider_turning_engine.domain.time import us_equity_session_close

_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SIC_MAPPING_PATH = _ROOT / "config" / "sic-sector.v1.yaml"
IDENTITY_VERSION = "identity.v1"
UNIVERSE_VERSION = "security-universe.v1"
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")
_US_COUNTRIES = {"US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"}
_ALLOWED_EXCHANGES = {"NYSE", "NASDAQ", "NYSE AMERICAN", "AMEX", "NYSE MKT"}
_EXCLUDED_TEXT = re.compile(
    r"\b(?:ETF|ETN|FUND|MUTUAL FUND|CLOSED[- ]END|PREFERRED|PREF(?:ERRED)?\.?|"
    r"WARRANTS?|UNITS?|RIGHTS?|DEBENTURES?|NOTES?|BONDS?|TRUST|REIT ETF)\b",
    re.IGNORECASE,
)
_SPAC_TEXT = re.compile(
    r"(?:\bSPAC\b|blank[- ]check|shell company|\bacquisition\s+(?:corp(?:oration)?|company)\b)",
    re.IGNORECASE,
)


def _get(obj: Any, *names: str, default: Any = None) -> Any:
    """Read snake/camel case fields from mappings and model-like objects."""

    if obj is None:
        return default
    if isinstance(obj, Mapping):
        for name in names:
            if name in obj and obj[name] is not None:
                return obj[name]
    else:
        for name in names:
            value = getattr(obj, name, None)
            if value is not None:
                return value
        # Pydantic and similar models can expose aliases only through a dump.
        dumper = getattr(obj, "model_dump", None)
        if callable(dumper):
            try:
                dumped = dumper(by_alias=True)
            except TypeError:
                dumped = dumper()
            return _get(dumped, *names, default=default)
    return default


def _nested(obj: Any, *paths: tuple[str, ...], default: Any = None) -> Any:
    for path in paths:
        value = obj
        for name in path:
            value = _get(value, name)
            if value is None:
                break
        if value is not None:
            return value
    return default


def _rows(data: Any) -> list[Any]:
    """Materialize records without requiring pandas or polars at import time."""

    if data is None:
        return []
    if isinstance(data, Mapping):
        # A dictionary of ticker -> CIK is a common compact SEC mapping form.
        if not any(key in data for key in ("cik", "CIK", "ticker", "symbol", "issuerCik")):
            rows: list[dict[str, Any]] = []
            for key, value in data.items():
                if isinstance(value, Mapping):
                    row = dict(value)
                    row.setdefault("cik", key)
                    rows.append(row)
                elif normalize_cik(key) is not None:
                    rows.append({"cik": key, "ticker": value})
                else:
                    rows.append({"ticker": key, "cik": value})
            return rows
        return [data]
    to_dicts = getattr(data, "to_dicts", None)
    if callable(to_dicts):
        return list(to_dicts())
    to_dict = getattr(data, "to_dict", None)
    if callable(to_dict):
        try:
            result = to_dict(orient="records")
        except (TypeError, ValueError):
            result = None
        if isinstance(result, list):
            return result
    if isinstance(data, (str, bytes)):
        return [data]
    try:
        return list(data)
    except TypeError:
        return [data]


def _date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(UTC)
        return cast(date, value.date())
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        candidate = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            try:
                return date.fromisoformat(candidate)
            except ValueError:
                return None
    return None


def _instant(value: Any) -> datetime | None:
    """Preserve knowledge-time precision at the point-in-time boundary.

    Date-only evidence is interpreted at the US regular-session close.  A
    full timestamp remains exact, so knowledge obtained after that close
    cannot leak into the same daily snapshot.
    """

    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        current = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return current.astimezone(UTC)
    if isinstance(value, date):
        return us_equity_session_close(value)
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        if len(candidate) == 10:
            try:
                return us_equity_session_close(date.fromisoformat(candidate))
            except ValueError:
                return None
        try:
            current = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            return None
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return current.astimezone(UTC)
    return None


def normalize_cik(value: Any) -> str | None:
    """Return the SEC CIK as exactly ten digits, or ``None`` if invalid."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        text = str(value)
    else:
        text = str(value).strip()
    digits = re.sub(r"\D", "", text)
    if not digits or len(digits) > 10:
        return None
    return digits.zfill(10)


def normalize_ticker(value: Any) -> str | None:
    """Normalize a ticker without treating it as issuer identity."""

    if value is None:
        return None
    ticker = str(value).strip().upper()
    return ticker if ticker and _TICKER_RE.fullmatch(ticker) else None


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


@dataclass(frozen=True)
class TickerInterval:
    """A ticker valid during the half-open interval ``[valid_from, valid_to)``."""

    cik: str
    ticker: str
    valid_from: date | None = None
    valid_to: date | None = None
    source: str = "sec"
    knowledge_at: date | datetime | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def contains(self, as_of: Any = None) -> bool:
        point = _date(as_of) if as_of is not None else None
        point_instant = _instant(as_of) if as_of is not None else None
        known = _instant(self.knowledge_at)
        if point is None:
            return self.knowledge_at is None
        return (
            (known is None or (point_instant is not None and known <= point_instant))
            and (self.valid_from is None or self.valid_from <= point)
            and (self.valid_to is None or point < self.valid_to)
        )


@dataclass(frozen=True)
class IssuerIdentity:
    cik: str
    name: str = ""
    ticker: str | None = None
    exchange: str | None = None
    sic: str | None = None
    status: str = "ACTIVE"
    provenance: Mapping[str, Any] = field(default_factory=dict)

    @property
    def issuer_cik(self) -> str:
        return self.cik


@dataclass(frozen=True)
class IdentityResolution:
    cik: str
    issuer: IssuerIdentity | None
    ticker: str | None
    provenance: Mapping[str, Any] = field(default_factory=dict)

    @property
    def issuer_cik(self) -> str:
        return self.cik


def _issuer_fields(record: Any) -> tuple[str | None, str, str | None, str | None, str | None]:
    nested_issuer = _get(record, "issuer", default=None)
    cik = normalize_cik(
        _nested(record, ("issuer_cik",), ("issuerCik",), ("cik",), ("CIK",), default=None)
    )
    if cik is None:
        cik = normalize_cik(_get(nested_issuer, "cik", "issuer_cik", "issuerCik"))
    name = _nested(record, ("issuer_name",), ("issuerName",), ("name",), default=None)
    if name is None:
        name = _get(nested_issuer, "name", "issuer_name", "issuerName", default="")
    ticker = _nested(
        record,
        ("issuer_trading_symbol",),
        ("issuerTradingSymbol",),
        ("filing_issuer_trading_symbol",),
        ("filingIssuerTradingSymbol",),
        ("ticker",),
        ("symbol",),
        default=None,
    )
    if ticker is None:
        ticker = _get(nested_issuer, "ticker", "issuer_trading_symbol", "issuerTradingSymbol")
    exchange = _nested(
        record, ("exchange",), ("primary_exchange",), ("primaryExchange",), default=None
    )
    sic = _nested(record, ("sic",), ("sic_code",), ("sicCode",), default=None)
    return (
        cik,
        str(name or "").strip(),
        normalize_ticker(ticker),
        str(exchange or "").strip() or None,
        str(sic or "").strip() or None,
    )


def _interval_from_record(record: Any, *, default_source: str = "filing") -> TickerInterval | None:
    cik, _name, ticker, _exchange, _sic = _issuer_fields(record)
    if cik is None or ticker is None:
        return None
    valid_from = _date(
        _nested(
            record,
            ("valid_from",),
            ("validFrom",),
            ("effective_from",),
            ("effectiveFrom",),
            ("filing_date",),
            ("filingDate",),
            default=None,
        )
    )
    valid_to = _date(
        _nested(
            record, ("valid_to",), ("validTo",), ("effective_to",), ("effectiveTo",), default=None
        )
    )
    knowledge_at = _instant(
        _nested(
            record,
            ("knowledge_at",),
            ("knowledgeAt",),
            ("accepted_at",),
            ("acceptedAt",),
            default=None,
        )
    )
    source = str(_get(record, "ticker_source", "source", default=default_source) or default_source)
    return TickerInterval(
        cik=cik,
        ticker=ticker,
        valid_from=valid_from,
        valid_to=valid_to,
        source=source,
        knowledge_at=knowledge_at,
        provenance={"source_record": source},
    )


class IssuerIdentityIndex:
    """In-memory, deterministic issuer identity and ticker interval index."""

    def __init__(
        self,
        issuers: Iterable[IssuerIdentity] = (),
        ticker_intervals: Iterable[TickerInterval] = (),
        sec_current_mapping: Any = None,
        *,
        version: str = IDENTITY_VERSION,
    ) -> None:
        self.version = version
        self.issuers: dict[str, IssuerIdentity] = {}
        for issuer in issuers:
            cik = normalize_cik(issuer.cik)
            if cik is None:
                continue
            self.issuers[cik] = IssuerIdentity(
                cik=cik,
                name=issuer.name,
                ticker=normalize_ticker(issuer.ticker),
                exchange=issuer.exchange,
                sic=issuer.sic,
                status=issuer.status,
                provenance=issuer.provenance,
            )
        self.ticker_intervals = list(ticker_intervals)
        self.sec_current_mapping: dict[str, TickerInterval] = {}
        for row in _rows(sec_current_mapping):
            interval = _interval_from_record(row, default_source="sec_current_mapping")
            if interval is None:
                cik = normalize_cik(_get(row, "cik", "CIK", "issuerCik"))
                ticker = normalize_ticker(_get(row, "ticker", "symbol"))
                if cik and ticker:
                    interval = TickerInterval(cik=cik, ticker=ticker, source="sec_current_mapping")
            if interval is not None:
                # A duplicate current mapping must resolve identically.  Keep
                # the lexically smallest row to make malformed input stable.
                previous = self.sec_current_mapping.get(interval.cik)
                if previous is None or (interval.ticker, interval.source) < (
                    previous.ticker,
                    previous.source,
                ):
                    self.sec_current_mapping[interval.cik] = interval

    @classmethod
    def from_records(
        cls,
        records: Any = (),
        sec_current_mapping: Any = None,
        *,
        version: str = IDENTITY_VERSION,
    ) -> IssuerIdentityIndex:
        issuers: dict[str, IssuerIdentity] = {}
        intervals: list[TickerInterval] = []
        for record in _rows(records):
            cik, name, ticker, exchange, sic = _issuer_fields(record)
            if cik is None:
                continue
            existing = issuers.get(cik)
            # Names and attributes are deterministic: first non-empty value in
            # lexical source order wins, while CIK remains the only key.
            issuers[cik] = existing or IssuerIdentity(
                cik=cik, name=name, ticker=ticker, exchange=exchange, sic=sic
            )
            interval = _interval_from_record(record)
            if interval is not None:
                intervals.append(interval)
        return cls(issuers.values(), intervals, sec_current_mapping, version=version)

    def resolve_ticker(
        self,
        cik: Any,
        as_of: Any = None,
        filing_issuer_trading_symbol: Any = None,
        filing_ticker_known_at: Any = None,
    ) -> IdentityResolution:
        normalized = normalize_cik(cik)
        if normalized is None:
            return IdentityResolution(
                cik="",
                issuer=None,
                ticker=None,
                provenance={"source": "invalid_cik", "version": self.version},
            )
        filing_ticker = normalize_ticker(filing_issuer_trading_symbol)
        point = _date(as_of) if as_of is not None else None
        point_instant = _instant(as_of) if as_of is not None else None
        filing_known = _instant(filing_ticker_known_at)
        if filing_ticker and (
            point is None
            or (
                filing_known is not None
                and point_instant is not None
                and filing_known <= point_instant
            )
        ):
            return self._resolution(
                normalized,
                filing_ticker,
                {
                    "source": "filing_issuerTradingSymbol",
                    "method": "filing_preferred",
                    "knowledge_at": filing_known.isoformat() if filing_known else None,
                    "version": self.version,
                    "historical_mapping_caveat": False,
                },
            )
        current = self.sec_current_mapping.get(normalized)
        if current is not None and point is None:
            return self._resolution(
                normalized,
                current.ticker,
                {
                    "source": "sec_current_mapping",
                    "method": "current_mapping_fallback",
                    "version": self.version,
                    "historical_mapping_caveat": True,
                    "caveat": (
                        "SEC current mapping is not a historical ticker map; "
                        "use valid-time intervals for backtests."
                    ),
                },
            )
        candidates = [
            interval
            for interval in self.ticker_intervals
            if interval.cik == normalized and interval.contains(as_of)
        ]
        if candidates:
            chosen = sorted(
                candidates,
                key=lambda item: (
                    item.valid_from or date.min,
                    item.valid_to is None,
                    item.source,
                    item.ticker,
                ),
                reverse=True,
            )[0]
            chosen_known = _instant(chosen.knowledge_at)
            return self._resolution(
                normalized,
                chosen.ticker,
                {
                    "source": chosen.source,
                    "method": "valid_time_interval",
                    "valid_from": chosen.valid_from.isoformat() if chosen.valid_from else None,
                    "valid_to": chosen.valid_to.isoformat() if chosen.valid_to else None,
                    "knowledge_at": chosen_known.isoformat() if chosen_known is not None else None,
                    "version": self.version,
                    "historical_mapping_caveat": False,
                },
            )
        current_known = _instant(current.knowledge_at) if current is not None else None
        if (
            current is not None
            and current_known is not None
            and point_instant is not None
            and current_known <= point_instant
        ):
            return self._resolution(
                normalized,
                current.ticker,
                {
                    "source": "sec_current_mapping",
                    "method": "current_mapping_fallback",
                    "knowledge_at": current_known.isoformat(),
                    "version": self.version,
                    "historical_mapping_caveat": True,
                    "caveat": (
                        "SEC current mapping is not a historical ticker map; "
                        "use valid-time intervals for backtests."
                    ),
                },
            )
        return self._resolution(
            normalized,
            None,
            {
                "source": (
                    "sec_current_mapping_withheld"
                    if current is not None and point is not None
                    else "unresolved"
                ),
                "method": "no_point_in_time_mapping",
                "version": self.version,
                "historical_mapping_caveat": current is not None and point is not None,
                "caveat": (
                    "SEC current mapping was withheld because it has no point-in-time "
                    "knowledge evidence."
                    if current is not None and point is not None
                    else None
                ),
            },
        )

    def resolve(self, record_or_cik: Any, as_of: Any = None) -> IdentityResolution:
        if isinstance(record_or_cik, (str, int)):
            return self.resolve_ticker(record_or_cik, as_of)
        cik, _name, filing_ticker, _exchange, _sic = _issuer_fields(record_or_cik)
        filing_known_at = _nested(
            record_or_cik,
            ("knowledge_at",),
            ("knowledgeAt",),
            ("accepted_at",),
            ("acceptedAt",),
            ("timestamps", "knowledge_at"),
            ("timestamps", "knowledgeAt"),
            default=None,
        )
        return self.resolve_ticker(cik, as_of, filing_ticker, filing_known_at)

    def _resolution(
        self, cik: str, ticker: str | None, provenance: Mapping[str, Any]
    ) -> IdentityResolution:
        issuer = self.issuers.get(cik)
        if issuer is not None:
            issuer = IssuerIdentity(
                cik=cik,
                name=issuer.name,
                ticker=ticker,
                exchange=issuer.exchange,
                sic=issuer.sic,
                status=issuer.status,
                provenance=provenance,
            )
        return IdentityResolution(cik=cik, issuer=issuer, ticker=ticker, provenance=provenance)


def build_issuer_identity(
    records: Any, sec_current_mapping: Any = None, *, version: str = IDENTITY_VERSION
) -> IssuerIdentityIndex:
    """Build a CIK-keyed issuer index from records or a dataframe."""

    return IssuerIdentityIndex.from_records(records, sec_current_mapping, version=version)


@dataclass(frozen=True)
class SecurityUniverseDecision:
    include: bool
    cik: str | None
    reason: str
    provenance: Mapping[str, Any] = field(default_factory=dict)

    @property
    def included(self) -> bool:
        return self.include

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(self.provenance.get("reasons", ()))


def evaluate_security_universe(
    record: Any, *, version: str = UNIVERSE_VERSION, as_of: Any = None
) -> SecurityUniverseDecision:
    cik, name, _ticker, exchange, sic = _issuer_fields(record)
    exchange_value = (
        (
            exchange
            or _get(record, "listing_exchange", "listingExchange", "exchangeCode", default="")
            or ""
        )
        .strip()
        .upper()
    )
    country = (
        str(
            _get(
                record,
                "country",
                "country_code",
                "countryCode",
                "domicile",
                "incorporation_country",
                default="",
            )
            or ""
        )
        .strip()
        .upper()
    )
    security_type = str(
        _get(
            record,
            "security_type",
            "securityType",
            "asset_type",
            "assetType",
            "instrument_type",
            "instrumentType",
            default="",
        )
        or ""
    )
    title = " ".join(
        str(value or "")
        for value in (
            name,
            _get(record, "title", "security_title", "securityTitle", default=""),
            _get(record, "class_name", "className", default=""),
            security_type,
        )
    )
    reasons: list[str] = []
    point = _date(as_of) if as_of is not None else None
    point_instant = _instant(as_of) if as_of is not None else None
    if point is not None:
        knowledge_at = _instant(
            _get(record, "knowledge_at", "knowledgeAt", "accepted_at", "acceptedAt")
        )
        valid_from = _date(
            _get(record, "valid_from", "validFrom", "effective_from", "effectiveFrom")
        )
        valid_to = _date(_get(record, "valid_to", "validTo", "effective_to", "effectiveTo"))
        if (
            knowledge_at is not None
            and point_instant is not None
            and knowledge_at > point_instant
        ):
            reasons.append("membership_known_after_as_of")
        if valid_from is not None and valid_from > point:
            reasons.append("membership_not_yet_effective")
        if valid_to is not None and point >= valid_to:
            reasons.append("membership_expired")
    if cik is None:
        reasons.append("invalid_cik")
    if exchange_value not in _ALLOWED_EXCHANGES and not exchange_value.startswith("NASDAQ"):
        reasons.append("non_us_operating_exchange")
    if country and country not in _US_COUNTRIES:
        reasons.append("non_us_domicile")
    if _EXCLUDED_TEXT.search(title):
        reasons.append("excluded_security_type")
    for flag in (
        "is_etf",
        "is_fund",
        "is_preferred",
        "is_warrant",
        "is_unit",
        "is_shell",
        "is_spac",
        "is_blank_check",
    ):
        camel_flag = "".join(part.title() if i else part for i, part in enumerate(flag.split("_")))
        acronym_flag = camel_flag.replace("Etf", "ETF").replace("Spac", "SPAC")
        if _bool(_get(record, flag, camel_flag, acronym_flag, default=False)):
            reasons.append(flag)
    if _SPAC_TEXT.search(title) or str(sic or "").strip() == "6770":
        reasons.append("blank_check_or_spac_shell")
    included = not reasons
    return SecurityUniverseDecision(
        include=included,
        cik=cik,
        reason="included" if included else ";".join(dict.fromkeys(reasons)),
        provenance={
            "version": version,
            "criteria": "US operating common stock on NYSE/Nasdaq/NYSE American",
            "reasons": tuple(dict.fromkeys(reasons)),
        },
    )


def is_in_security_universe(record: Any) -> bool:
    return evaluate_security_universe(record).include


def filter_security_universe(
    records: Any, *, version: str = UNIVERSE_VERSION, as_of: Any = None
) -> Any:
    """Filter records/dataframes while preserving dataframe shape when practical."""

    materialized = _rows(records)
    keep = [
        index
        for index, record in enumerate(materialized)
        if evaluate_security_universe(record, version=version, as_of=as_of).include
    ]
    if hasattr(records, "iloc"):
        return records.iloc[keep].copy()
    if hasattr(records, "filter") and hasattr(records, "to_dicts"):
        return records.__class__([materialized[index] for index in keep])
    return [materialized[index] for index in keep]


@dataclass(frozen=True)
class SectorMappingResult:
    sic: str | None
    sector_etf: str
    mapping_version: str
    provenance: Mapping[str, Any] = field(default_factory=dict)

    @property
    def etf(self) -> str:
        return self.sector_etf

    @property
    def sector(self) -> str:
        return self.sector_etf

    def __str__(self) -> str:
        return self.sector_etf

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SectorMappingResult):
            return (self.sic, self.sector_etf, self.mapping_version) == (
                other.sic,
                other.sector_etf,
                other.mapping_version,
            )
        if isinstance(other, str):
            return self.sector_etf == other
        return NotImplemented


def _sic_number(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not re.fullmatch(r"\d{1,4}", text):
        return None
    number = int(text)
    return number if 0 <= number <= 9999 else None


def load_sic_sector_mapping(path: str | Path = DEFAULT_SIC_MAPPING_PATH) -> Mapping[str, Any]:
    with Path(path).open("r", encoding="utf-8") as stream:
        loaded = yaml.safe_load(stream)
    if not isinstance(loaded, Mapping) or not isinstance(loaded.get("rules"), Sequence):
        raise ValueError("SIC sector mapping must contain a rules sequence")
    return loaded


def map_sic_to_sector_etf(
    sic: Any, *, mapping_path: str | Path = DEFAULT_SIC_MAPPING_PATH
) -> SectorMappingResult:
    number = _sic_number(sic)
    mapping = load_sic_sector_mapping(mapping_path)
    version = str(mapping.get("version", "unknown"))
    default = str(mapping.get("default_etf", "UNKNOWN"))
    selected = default
    matched_range: tuple[int, int] | None = None
    if number is not None:
        for rule in mapping["rules"]:
            if not isinstance(rule, Mapping):
                continue
            etf = str(rule.get("etf", "UNKNOWN"))
            ranges = rule.get("sic_ranges", ())
            for bounds in ranges if isinstance(ranges, Sequence) else ():
                if isinstance(bounds, Sequence) and len(bounds) == 2:
                    low, high = int(bounds[0]), int(bounds[1])
                    if low <= number <= high:
                        selected, matched_range = etf, (low, high)
                        break
            if matched_range is not None:
                break
    caveat = str(mapping.get("historical_caveat", ""))
    return SectorMappingResult(
        sic=f"{number:04d}" if number is not None else None,
        sector_etf=selected,
        mapping_version=version,
        provenance={
            "source": str(mapping_path),
            "mapping_version": version,
            "matched_sic_range": matched_range,
            "historical_mapping_caveat": True,
            "caveat": caveat,
        },
    )


def sector_etf_for_sic(sic: Any, *, mapping_path: str | Path = DEFAULT_SIC_MAPPING_PATH) -> str:
    """String convenience API for callers that only need the ETF symbol."""

    return map_sic_to_sector_etf(sic, mapping_path=mapping_path).sector_etf


# Common aliases used at pipeline boundaries.
resolve_issuer_identity = build_issuer_identity
filter_universe = filter_security_universe
security_universe_filter = filter_security_universe
map_sic_to_sector = map_sic_to_sector_etf
sic_to_sector_etf = sector_etf_for_sic
IssuerResolver = IssuerIdentityIndex
TickerMapping = TickerInterval


def resolve_ticker_as_of(
    index: IssuerIdentityIndex,
    cik: Any,
    as_of: Any = None,
    filing_issuer_trading_symbol: Any = None,
    filing_ticker_known_at: Any = None,
) -> IdentityResolution:
    """Functional convenience wrapper for point-in-time ticker resolution."""

    return index.resolve_ticker(
        cik,
        as_of,
        filing_issuer_trading_symbol,
        filing_ticker_known_at,
    )


__all__ = [
    "DEFAULT_SIC_MAPPING_PATH",
    "IDENTITY_VERSION",
    "UNIVERSE_VERSION",
    "IdentityResolution",
    "IssuerIdentity",
    "IssuerIdentityIndex",
    "IssuerResolver",
    "SectorMappingResult",
    "SecurityUniverseDecision",
    "TickerInterval",
    "TickerMapping",
    "build_issuer_identity",
    "evaluate_security_universe",
    "filter_security_universe",
    "filter_universe",
    "is_in_security_universe",
    "load_sic_sector_mapping",
    "map_sic_to_sector",
    "map_sic_to_sector_etf",
    "normalize_cik",
    "normalize_ticker",
    "resolve_issuer_identity",
    "resolve_ticker_as_of",
    "security_universe_filter",
    "sector_etf_for_sic",
    "sic_to_sector_etf",
]
