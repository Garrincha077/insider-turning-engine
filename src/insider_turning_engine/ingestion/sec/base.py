"""Provider-neutral contracts for SEC sources.

The objects in this module are deliberately transport and storage neutral.  A
source may use SEC's company-submissions endpoint, the quarterly bulk files,
or a replay cache, while consumers only see immutable raw records and pages.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from insider_turning_engine.domain.models import ParseResult, QuarantineRecord


class SecOutcomeStatus(StrEnum):
    """Typed transport outcomes used by SEC adapters."""

    SUCCESS = "success"
    RETRYABLE = "retryable"
    THROTTLED = "throttled"
    NOT_FOUND = "not-found"
    PERMANENT_INVALID = "permanent-invalid"


@dataclass(frozen=True, slots=True)
class SecRawRecord:
    """One filing envelope returned by a SEC source.

    ``payload`` is optional because listing a filing and fetching its primary
    XML are separate operations.  The content hash always describes the
    payload when present; submissions metadata is recorded in provenance.
    """

    provider: str
    provider_record_id: str
    issuer_cik: str
    accession_number: str
    form_type: str
    accepted_at: datetime
    source_url: str
    replay_locator: str
    retrieved_at: datetime
    content_type: str = "application/xml"
    content_hash: str | None = None
    payload: bytes | None = None
    primary_document: str | None = None
    filing_date: str | None = None
    report_date: str | None = None
    provenance: Mapping[str, object] = field(default_factory=dict)

    @property
    def source_time(self) -> datetime:
        """ADR name for the filing's availability/source timestamp."""

        return self.accepted_at

    @property
    def available_at(self) -> datetime:
        """Common ingestion spelling for a source availability timestamp."""

        return self.accepted_at

    @property
    def acceptance_datetime(self) -> datetime:
        return self.accepted_at


# Friendly aliases used by callers that call envelopes ``RawRecord``.
RawSECRecord = SecRawRecord
SECRecord = SecRawRecord


@dataclass(frozen=True, slots=True)
class SecPage:
    """A deterministic, at-least-once page and its checkpoint metadata."""

    records: tuple[SecRawRecord, ...] = ()
    next_cursor: str | None = None
    source_watermark: datetime | None = None
    quarantines: tuple[QuarantineRecord, ...] = ()

    @property
    def watermark(self) -> datetime | None:
        return self.source_watermark

    @property
    def quarantine(self) -> tuple[QuarantineRecord, ...]:
        return self.quarantines


@dataclass(frozen=True, slots=True)
class SecProviderHealth:
    """Operational health for an SEC adapter."""

    provider: str
    available: bool
    lag: float | None = None
    quota_state: str = "unknown"
    checked_at: datetime | None = None
    message: str = ""
    cache_hits: int = 0
    cache_misses: int = 0

    @property
    def availability(self) -> bool:
        return self.available

    @property
    def healthy(self) -> bool:
        return self.available and self.quota_state not in {"throttled", "error"}


@dataclass(frozen=True, slots=True)
class SecResult:
    """Typed result for an operation that may fail without raising."""

    status: SecOutcomeStatus
    record: SecRawRecord | None = None
    message: str = ""
    retry_after: float | None = None
    quarantines: tuple[QuarantineRecord, ...] = ()


@runtime_checkable
class SecSource(Protocol):
    """Common port for historical-quarter and incremental SEC sources."""

    name: str

    def historical_quarters(
        self, start_year: int, end_year: int | None = None
    ) -> Sequence[tuple[int, int]]: ...

    def fetch(
        self,
        cursor: str | None = None,
        through: datetime | None = None,
        *,
        since: datetime | None = None,
    ) -> SecPage: ...

    def iter_filings(
        self,
        cursor: str | None = None,
        through: datetime | None = None,
        *,
        since: datetime | None = None,
    ) -> Iterable[SecRawRecord]: ...

    def get(self, provider_record_id: str) -> SecRawRecord | SecResult: ...

    def normalize(self, raw_record: SecRawRecord) -> ParseResult: ...

    def health(self) -> SecProviderHealth: ...


@runtime_checkable
class HistoricalQuarterSource(Protocol):
    """Optional capability exposed by historical SEC implementations."""

    def historical_quarters(
        self, start_year: int, end_year: int | None = None
    ) -> Sequence[tuple[int, int]]: ...


def utc(value: datetime) -> datetime:
    """Normalize a datetime to an aware UTC instant."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "HistoricalQuarterSource",
    "RawSECRecord",
    "SECRecord",
    "SecOutcomeStatus",
    "SecPage",
    "SecProviderHealth",
    "SecRawRecord",
    "SecResult",
    "SecSource",
    "utc",
]
